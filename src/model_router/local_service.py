"""Container startup: download a pinned checkpoint once, then serve actual inference."""

import os
from pathlib import Path

from model_router.backend import MODEL_ID, MODEL_REVISION


def prepare_model():
    from huggingface_hub import snapshot_download

    path = Path(os.environ.get("MODEL_PATH", "/models/laya-mlx")) / MODEL_REVISION
    # local_files_only avoids network on subsequent starts, but require all runtime files.
    required = (
        "model.safetensors",
        "rl_agent_config.json",
        "encoder/config.json",
        "tokenizer/tokenizer.json",
        "mlx_config.json",
    )
    marker = path / ".tern-download-complete"
    if not marker.exists() or not all((path / name).is_file() for name in required):
        print("Downloading pinned Laya weights (first run; cached for later starts)...", flush=True)
        snapshot_download(
            MODEL_ID,
            revision=MODEL_REVISION,
            local_dir=path,
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
        if not all((path / name).is_file() for name in required):
            raise RuntimeError("Model download incomplete; restart setup to resume")
        marker.touch()
    os.environ["MODEL_PATH"] = str(path)
    os.environ["HF_HUB_OFFLINE"] = "1"


def main():
    prepare_model()
    print("Loading Laya and verifying real inference before accepting requests...", flush=True)
    import uvicorn

    uvicorn.run("model_router.app:app", host="0.0.0.0", port=8080, access_log=False)


if __name__ == "__main__":
    main()
