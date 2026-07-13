from __future__ import annotations

import logging
import subprocess
import threading
import time
from typing import Any


logger = logging.getLogger(__name__)

_token_cache: dict[str, tuple[str, float]] = {}
_token_lock = threading.Lock()
_TOKEN_LIFETIME_SECONDS = 3000
_PATCHED_AUDIENCES: set[str] = set()


def _fetch_oidc_token(audience: str) -> str:
    now = time.monotonic()
    with _token_lock:
        cached = _token_cache.get(audience)
        if cached and cached[1] > now:
            return cached[0]

        token = _fetch_token_via_adc(audience) or _fetch_token_via_gcloud(audience)
        if not token:
            raise RuntimeError(
                "Could not fetch a Google identity token for the LiteLLM proxy. "
                "Run `gcloud auth login` or set `GOOGLE_APPLICATION_CREDENTIALS`."
            )
        _token_cache[audience] = (token, now + _TOKEN_LIFETIME_SECONDS)
        return token


def _fetch_token_via_adc(audience: str) -> str | None:
    try:
        import google.auth.exceptions
        import google.auth.transport.requests
        from google.oauth2 import id_token

        request = google.auth.transport.requests.Request()
        return id_token.fetch_id_token(request, audience)
    except (
        OSError,
        ValueError,
        google.auth.exceptions.GoogleAuthError,
    ):
        logger.debug("ADC identity-token lookup failed.", exc_info=True)
        return None


def _fetch_token_via_gcloud(audience: str) -> str | None:
    try:
        command = ["gcloud", "auth", "print-identity-token"]
        if audience:
            command.extend(["--audiences", audience])
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        logger.debug("gcloud identity-token fallback failed.", exc_info=True)
        return None


def patch_litellm_for_cloud_run(proxy_url: str, proxy_key: str) -> None:
    from google.adk.models.lite_llm import LiteLLMClient

    audience = proxy_url.rstrip("/").split("/v1")[0]
    if audience in _PATCHED_AUDIENCES:
        return

    original_acompletion = LiteLLMClient.acompletion
    original_completion = LiteLLMClient.completion

    async def _patched_acompletion(self: Any, *args: Any, **kwargs: Any) -> Any:
        _inject_auth(kwargs, audience, proxy_key)
        return await original_acompletion(self, *args, **kwargs)

    def _patched_completion(self: Any, *args: Any, **kwargs: Any) -> Any:
        _inject_auth(kwargs, audience, proxy_key)
        return original_completion(self, *args, **kwargs)

    LiteLLMClient.acompletion = _patched_acompletion  # type: ignore[assignment]
    LiteLLMClient.completion = _patched_completion  # type: ignore[assignment]
    _PATCHED_AUDIENCES.add(audience)


def _inject_auth(kwargs: dict[str, Any], audience: str, proxy_key: str) -> None:
    token = _fetch_oidc_token(audience)
    kwargs["api_key"] = token
    extra_headers = kwargs.get("extra_headers") or {}
    extra_headers["x-litellm-api-key"] = proxy_key
    kwargs["extra_headers"] = extra_headers
