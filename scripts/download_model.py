"""Fetch only the pinned runtime files; never execute model repository code."""

import os

from huggingface_hub import snapshot_download

from model_router.backend import MODEL_ID, MODEL_REVISION

snapshot_download(
    MODEL_ID,
    revision=MODEL_REVISION,
    local_dir=os.environ.get("MODEL_PATH", "models/laya-mlx"),
    allow_patterns=[
        "model.safetensors",
        "rl_agent_config.json",
        "encoder/config.json",
        "tokenizer/*",
        "mlx_config.json",
        "LICENSE",
        "NOTICE",
        "manifest.json",
    ],
)
