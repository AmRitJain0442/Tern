# Operations

The service returns routing decisions; it does not invoke downstream LLMs. Default shadow mode always selects the eligible strong tier while reporting Laya's proposal. A null selection means there is no configured acceptable route.

## Reproduce locally

For the complete local installation, use `docker compose up --build --wait`. This builds the runtime, downloads the pinned checkpoint into a reusable volume, and starts CPU inference without cloud credentials. The [quickstart](quickstart.md) covers native Apple Metal, an optional NVIDIA Compose override, and local CLI usage. The deployment commands below are for optional cloud hosting.

```powershell
uv sync --extra dev --python 3.12
uv run --no-sync pytest -q
```

For Linux CPU inference (Python 3.11+):

```sh
uv sync --extra mlx-cpu --extra dev
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 uv run --no-sync python scripts/benchmark_local.py
uv run --no-sync uvicorn model_router.app:app --host 127.0.0.1 --port 8080
```

Cloud Run IAM protects the deployed service. Local uvicorn has no application authentication; bind it to loopback.

## Build and deploy

Run from the repository root. Container images use the Git commit as a tag; record the resolved digest after deployment. Model and Laya source are pinned; OS package resolution and the base image tag can change between builds.

```powershell
$revision = git rev-parse --short HEAD
$image = "asia-south1-docker.pkg.dev/tribe-v2-host/model-router/laya:$revision"
gcloud builds submit . --project=tribe-v2-host --tag=$image --timeout=1200s
./scripts/deploy.ps1 -Image $image
```

Artifact Registry repository `model-router` must already exist in `asia-south1`. The dedicated runtime service account has no application-specific project roles. No keys are embedded in the image.

Invocation uses a short-lived identity token. Never save tokens in the repository or benchmark artifacts.

```powershell
$endpoint = gcloud run services describe model-router-laya --project=tribe-v2-host --region=asia-south1 --format='value(status.url)'
$identityToken = gcloud auth print-identity-token
$headers = @{ Authorization = "Bearer $identityToken" }
$body = @{ prompt = 'Rewrite this politely: send the invoice.'; language = 'en' } | ConvertTo-Json
Invoke-RestMethod "$endpoint/v1/route" -Method Post -Headers $headers -ContentType 'application/json' -Body $body
```

Weights are baked into the image, with offline runtime loading. Readiness waits for a forward pass. Concurrency is one per instance; a process lock also protects MLX from concurrent calls. The inference budget is checked **after** completion; it is not a cancellation deadline. Clients need their own HTTP timeout and conservative fallback. Cloud Run may queue requests and cold starts may dominate latency.

## Cost and cleanup

Minimum zero, maximum one, private IAM, and CPU-only request billing limit exposure; these are not a dollar spending cap. Image storage, builds, startup time, logs, networking, and requests can all incur charges. No paid downstream generation is enabled. Budget numbers in research are estimates, not a bill.

Remove this experiment's service when finished:

```powershell
gcloud run services delete model-router-laya --project=tribe-v2-host --region=asia-south1
```

This leaves images and build artifacts. Inspect the dedicated `model-router` Artifact Registry repository and the specific Cloud Build source objects before deleting them. Do not delete the shared project's buckets or other services. To roll back, move service traffic to the previously verified revision using `gcloud run services update-traffic`.

## GPU experiment

The user explicitly authorized GPU use. The L4 configuration uses Singapore, 4 vCPU, 16 GiB, one GPU, one instance maximum, minimum zero, and instance-based billing. Its runtime is MLX CUDA 12, float16. Run:

```powershell
$revision = git rev-parse --short HEAD
$image = "asia-south1-docker.pkg.dev/tribe-v2-host/model-router/laya-gpu:$revision"
gcloud builds submit . --project=tribe-v2-host --config=cloudbuild-gpu.yaml --substitutions="_IMAGE=$image"
./scripts/deploy-gpu.ps1 -Image $image
```

Resolve the image tag to its digest for the recorded deployment. The runtime service account must already exist (the CPU deployment script creates it). The active deployer may invoke if it has the relevant project role; grant `roles/run.invoker` on this service to additional approved callers individually. Do not grant `allUsers`.

Readiness is `/health`. `/healthz` was intercepted by the Cloud Run frontend in the CPU experiment and should not be used for an external reachability check.

```powershell
uv run --no-sync python scripts/benchmark_cloud.py --endpoint <service-url> --repeats 10 --output artifacts/cloud-mlx-gpu.json
```

The GPU service can scale to zero but bills while an instance remains allocated. Idle scale-down is not immediate. Delete this experiment's GPU service with `gcloud run services delete model-router-laya-gpu --project=tribe-v2-host --region=asia-southeast1` when no longer needed.

The image registry used by this first experiment is in Mumbai; for sustained Singapore hosting, place the registry in Singapore too and measure cold starts again.
