# Operations

Tern serves routing decisions and a configurable Chat Completions API. The cloud setup below starts private classification in shadow mode and supplies no downstream credentials. The recorded deployment artifact describes an earlier classification-only revision; it is historical evidence, not a public hosted API.

## Reproduce locally

For the complete local installation, use `docker compose up --build --wait`. This builds the runtime, downloads the pinned checkpoint into a reusable volume, and starts CPU inference without cloud credentials. The [quickstart](quickstart.md) covers native Apple Metal, an optional NVIDIA Compose override, and local CLI usage. The deployment commands below are for optional cloud hosting.

```powershell
uv sync --extra dev --extra cli --python 3.12
uv run --no-sync pytest -q
```

For Linux CPU inference (Python 3.11+):

```sh
uv sync --extra mlx-cpu --extra dev
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 uv run --no-sync python scripts/benchmark_local.py
uv run --no-sync uvicorn model_router.app:app --host 127.0.0.1 --port 8080
```

Cloud Run IAM protects the entire private cloud service. Bind a native local server to loopback. `TERN_API_KEY` optionally protects generation and model discovery; it does not protect `/v1/route`. See the [provider guide](providers.md).

## Build and deploy

Use your own billing-enabled GCP project. Install and authenticate gcloud, enable Cloud Run, Cloud Build and Artifact Registry, and grant the deployer the necessary build/deploy/service-account permissions. GPU deployment additionally requires GPU quota. Run from the repository root in PowerShell. Container images use the Git commit as a tag; record the resolved digest after deployment. Model and Laya source are pinned; OS package resolution and the base image tag can change between builds.

```powershell
$releaseProject = 'your-gcp-project-id'
$releaseRegion = 'asia-south1'
$revision = git rev-parse --short HEAD
$image = "$releaseRegion-docker.pkg.dev/$releaseProject/model-router/laya:$revision"
gcloud builds submit . --project=$releaseProject --tag=$image --timeout=1200s
./scripts/deploy.ps1 -Project $releaseProject -Region $releaseRegion -Image $image
```

Before building, create the `model-router` image repository once in the chosen region if it is absent: `gcloud artifacts repositories create model-router --project=$releaseProject --location=$releaseRegion --repository-format=docker`. The deployment scripts require an explicit project and never default to the maintainer's account. The dedicated runtime service account has no application-specific project roles. No keys are embedded in the image.

Invocation uses a short-lived identity token. Never save tokens in the repository or benchmark artifacts.

```powershell
$endpoint = gcloud run services describe model-router-laya --project=$releaseProject --region=$releaseRegion --format='value(status.url)'
$identityToken = gcloud auth print-identity-token
$headers = @{ Authorization = "Bearer $identityToken" }
$body = @{ prompt = 'Rewrite this politely: send the invoice.'; language = 'en' } | ConvertTo-Json
Invoke-RestMethod "$endpoint/v1/route" -Method Post -Headers $headers -ContentType 'application/json' -Body $body
```

Weights are baked into the image, with offline runtime loading. Readiness waits for a forward pass. Concurrency is one per instance; a process lock also protects MLX from concurrent calls. The inference budget is checked **after** completion; it is not a cancellation deadline. Clients need their own HTTP timeout and conservative fallback. Cloud Run may queue requests and cold starts may dominate latency.

## Cost and cleanup

Minimum zero, maximum one, private IAM, and CPU-only request billing limit exposure; these are not a dollar spending cap. Image storage, builds, startup time, logs, networking, and requests can all incur charges. No downstream generation is enabled unless you separately configure a provider and credentials; generation charges are additional. Budget numbers in research are estimates, not a bill.

Remove this experiment's service when finished:

```powershell
gcloud run services delete model-router-laya --project=$releaseProject --region=$releaseRegion
```

This leaves images and build artifacts. Inspect the dedicated `model-router` Artifact Registry repository and the specific Cloud Build source objects before deleting them. Do not delete the shared project's buckets or other services. To roll back, move service traffic to the previously verified revision using `gcloud run services update-traffic`.

## GPU experiment

The recorded experiment used Singapore. The L4 configuration uses 4 vCPU, 16 GiB, one GPU, one instance maximum, minimum zero, and instance-based billing. Its runtime is MLX CUDA 12, float16. Run:

```powershell
# Set $releaseProject to your project as above.
$releaseRegion = 'asia-southeast1'
$revision = git rev-parse --short HEAD
$image = "$releaseRegion-docker.pkg.dev/$releaseProject/model-router/laya-gpu:$revision"
gcloud builds submit . --project=$releaseProject --config=cloudbuild-gpu.yaml --substitutions="_IMAGE=$image"
./scripts/deploy-gpu.ps1 -Project $releaseProject -Region $releaseRegion -Image $image
```

Before building, create the image repository in `$releaseRegion` if absent, as in the CPU instructions. Resolve the image tag to its digest for your deployment record. The runtime service account must already exist: the CPU script creates it, or create it once with `gcloud iam service-accounts create model-router-runtime --project=$releaseProject --display-name='Tern runtime'`. The active deployer may invoke if it has the relevant project role; grant `roles/run.invoker` on this service to additional approved callers individually. Do not grant `allUsers`.

Readiness is `/health`. `/healthz` was intercepted by the Cloud Run frontend in the CPU experiment and should not be used for an external reachability check.

```powershell
$endpoint = gcloud run services describe model-router-laya-gpu --project=$releaseProject --region=$releaseRegion --format='value(status.url)'
uv run --no-sync python scripts/benchmark_cloud.py --endpoint $endpoint --repeats 10 --output artifacts/private/my-gpu-run.json
```

The GPU service can scale to zero but bills while an instance remains allocated. Idle scale-down is not immediate. Delete this experiment's GPU service with `gcloud run services delete model-router-laya-gpu --project=$releaseProject --region=$releaseRegion` when no longer needed.

The recorded experiment used a Mumbai registry and Singapore service. The commands above colocate new images and services in Singapore; measure cold starts again before comparing. Public artifacts redact private infrastructure identifiers while retaining timings, model revisions and image digests.
