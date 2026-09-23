"""Cloud Run audience-bound ID tokens; no tokens are logged or serialized."""

import asyncio
import shutil
import subprocess
import time


class GoogleIDTokenProvider:
    """For service-account credentials or GCP metadata identity. One instance per event loop."""

    def __init__(self, audience: str):
        self.audience = audience
        self._credentials = None
        self._pending = None

    def _refresh(self):
        from google.auth.transport.requests import Request
        from google.oauth2.id_token import fetch_id_token_credentials

        transport = Request()

        def bounded_request(*args, **kwargs):
            kwargs["timeout"] = 5
            return transport(*args, **kwargs)

        if self._credentials is None:
            self._credentials = fetch_id_token_credentials(self.audience, request=bounded_request)
        if not self._credentials.valid:
            self._credentials.refresh(bounded_request)
        return self._credentials.token

    async def __call__(self) -> str:
        if self._credentials is not None and self._credentials.valid:
            return self._credentials.token
        if self._pending is None or self._pending.done():
            self._pending = asyncio.create_task(asyncio.to_thread(self._refresh))
            # Retrieve exceptions even if every waiting request times out.
            self._pending.add_done_callback(
                lambda task: task.exception() if not task.cancelled() else None
            )
        return await asyncio.shield(self._pending)


class GcloudIDTokenProvider:
    """Explicit developer-only auth. Production should use GoogleIDTokenProvider."""

    def __init__(self):
        self._token = None
        self._expires = 0
        self._pending = None

    def _refresh(self):
        executable = shutil.which("gcloud.cmd") or shutil.which("gcloud")
        if not executable:
            raise RuntimeError("gcloud not installed")
        result = subprocess.run(
            [executable, "auth", "print-identity-token"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode or not result.stdout.strip():
            raise RuntimeError("gcloud ID token acquisition failed")
        self._token = result.stdout.strip()
        self._expires = time.monotonic() + 300
        return self._token

    async def __call__(self) -> str:
        if self._token and time.monotonic() < self._expires:
            return self._token
        if self._pending is None or self._pending.done():
            self._pending = asyncio.create_task(asyncio.to_thread(self._refresh))
            self._pending.add_done_callback(
                lambda task: task.exception() if not task.cancelled() else None
            )
        return await asyncio.shield(self._pending)
