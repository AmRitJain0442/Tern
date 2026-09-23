"""Pinned MLX inference with explicit context accounting and serialized execution."""

import os
import threading
from time import perf_counter

MODEL_ID = "aac6fef/laya-mlx"
MODEL_REVISION = "20aed815fc6acde75733882e7ec0e3f28aeb9717"
QUESTIONS = {
    "tier": {
        "type": "choice",
        "instructions": "Which language model capability is needed to answer this request well?",
        "criteria": {
            "economy": "Simple extraction, rewriting, translation, or straightforward factual answer.",
            "strong": "Difficult reasoning, complex code, specialist analysis, or ambiguous requirements.",
        },
    }
}


class ContextOverflow(Exception):
    pass


class BackendBusy(Exception):
    pass


class MLXBackend:
    revision = MODEL_REVISION

    def __init__(self):
        import laya_mlx
        from laya_mlx.common import build_prefix

        self.agent = laya_mlx.load(
            os.environ.get("MODEL_PATH", MODEL_ID),
            revision=MODEL_REVISION,
            device=os.environ.get("MLX_DEVICE", "cpu"),
            dtype=os.environ.get("MLX_DTYPE", "float32"),
            batch_size=1,
        )
        internal = self.agent._to_internal(QUESTIONS["tier"])
        prefix, _ = build_prefix(self.agent.tok, internal, self.agent.cfg["head_max_len"])
        self.state_budget = self.agent.cfg["max_len"] - len(prefix) - 1
        self.lock = threading.Lock()

    def predict(self, prompt: str) -> tuple[float, float, int]:
        # The port removes mask literals before tokenization. Use exactly the same text.
        if not self.lock.acquire(blocking=False):
            raise BackendBusy()
        try:
            clean = prompt.replace(self.agent.tok.mask_token, " ")
            tokens = self.agent.tok(clean, add_special_tokens=False)["input_ids"]
            if len(tokens) > self.state_budget:
                raise ContextOverflow()
            started = perf_counter()
            result = self.agent.predict(prompt, QUESTIONS)
            elapsed = (perf_counter() - started) * 1000
            probability = result["answers"]["tier"]["probabilities"]["economy"]
            return probability, elapsed, result["usage"]["input_tokens"]
        finally:
            self.lock.release()
