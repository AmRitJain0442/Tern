param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$Project,
    [string]$Region = 'asia-southeast1',
    [string]$Service = 'model-router-laya-gpu',
    [Parameter(Mandatory = $true)][string]$Image
)
$ErrorActionPreference = 'Stop'
gcloud run deploy $Service --project=$Project --region=$Region --image=$Image `
    --service-account="model-router-runtime@$Project.iam.gserviceaccount.com" `
    --no-allow-unauthenticated --ingress=all --default-url `
    --cpu=4 --memory=16Gi --gpu=1 --gpu-type=nvidia-l4 --no-gpu-zonal-redundancy `
    --concurrency=1 --min=0 --max=1 --min-instances=0 --max-instances=1 `
    --timeout=60 --no-cpu-throttling --no-cpu-boost --execution-environment=gen2 `
    --set-env-vars='ROUTER_MODE=shadow,MAX_INFERENCE_MS=2000,MLX_DEVICE=gpu,MLX_DTYPE=float16' `
    --labels='app=model-router,purpose=research' `
    --startup-probe='httpGet.path=/health,httpGet.port=8080,initialDelaySeconds=0,periodSeconds=10,timeoutSeconds=5,failureThreshold=24' `
    --quiet
if ($LASTEXITCODE -ne 0) { throw 'GPU deployment failed' }
