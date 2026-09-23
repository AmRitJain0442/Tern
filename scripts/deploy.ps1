param(
    [string]$Project = 'tribe-v2-host',
    [string]$Region = 'asia-south1',
    [string]$Service = 'model-router-laya',
    [Parameter(Mandatory = $true)][string]$Image
)
$ErrorActionPreference = 'Stop'
$identity = "model-router-runtime@$Project.iam.gserviceaccount.com"
# Create the dedicated runtime identity once; it needs no project permissions.
$existing = gcloud iam service-accounts list --project=$Project --filter="email=$identity" --format='value(email)'
if ($LASTEXITCODE -ne 0) { throw 'Service account lookup failed' }
if (-not $existing) {
    gcloud iam service-accounts create model-router-runtime --project=$Project --display-name='Laya routing experiment'
    if ($LASTEXITCODE -ne 0) { throw 'Service account creation failed' }
}
gcloud run deploy $Service --project=$Project --region=$Region --image=$Image `
    --service-account=$identity --no-allow-unauthenticated --ingress=all `
    --cpu=2 --memory=4Gi --concurrency=1 --min=0 --max=1 --min-instances=0 --max-instances=1 `
    --timeout=60 --cpu-throttling --no-cpu-boost --execution-environment=gen2 `
    --set-env-vars='ROUTER_MODE=shadow,MAX_INFERENCE_MS=2000' `
    --labels='app=model-router,purpose=research' `
    --startup-probe='httpGet.path=/health,httpGet.port=8080,initialDelaySeconds=0,periodSeconds=10,timeoutSeconds=5,failureThreshold=24' `
    --quiet
if ($LASTEXITCODE -ne 0) { throw 'Cloud Run deployment failed' }
