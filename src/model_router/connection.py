"""Shared CLI/live-demo connection settings. Local inference needs no Google credentials."""

import os

from model_router.adapters.auth import GcloudIDTokenProvider
from model_router.adapters.laya import LOCAL_ENDPOINT, endpoint_is_local, validate_endpoint


def connection_settings(auth="auto", *, endpoint=None):
    endpoint = endpoint or os.environ.get("LAYA_ENDPOINT", LOCAL_ENDPOINT)
    if auth == "auto":
        auth = os.environ.get("LAYA_AUTH", "auto")
    if auth == "auto":
        auth = "local" if endpoint_is_local(endpoint) else "gcloud"
    if auth not in {"local", "gcloud", "google"}:
        raise ValueError("LAYA_AUTH must be auto, local, gcloud or google")
    local = auth == "local"
    validate_endpoint(endpoint, local=local)
    return (
        endpoint,
        auth,
        {
            "local": local,
            # CPU inference can take longer than the cloud GPU's 750 ms deadline.
            "timeout": float(os.environ.get("LAYA_TIMEOUT", "30" if local else "0.75")),
            "token_provider": GcloudIDTokenProvider() if auth == "gcloud" else None,
        },
    )
