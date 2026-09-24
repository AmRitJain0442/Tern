FROM python:3.14-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends git libopenblas0 liblapack3 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.7.13 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE THIRD_PARTY_NOTICES.md ./
COPY src ./src
ARG MLX_EXTRA=mlx-cpu
RUN uv sync --frozen --extra ${MLX_EXTRA} --no-dev --no-editable
COPY scripts/download_model.py ./scripts/download_model.py
ENV MODEL_PATH=/opt/laya-mlx
RUN .venv/bin/python scripts/download_model.py
ENV HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false MLX_DEVICE=cpu MLX_DTYPE=float32 \
    OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 ROUTER_MODE=shadow PYTHONUNBUFFERED=1
RUN useradd --uid 10001 --create-home router
USER router
EXPOSE 8080
CMD ["/app/.venv/bin/uvicorn", "model_router.app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log"]
