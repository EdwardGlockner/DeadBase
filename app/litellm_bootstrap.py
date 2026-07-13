from __future__ import annotations

import os

from dotenv import load_dotenv


load_dotenv()

_BOOTSTRAPPED = False


def resolve_proxy_url() -> str | None:
    return os.environ.get("LITELLM_PROXY_URL")


def resolve_proxy_key() -> str:
    return os.environ.get("LITELLM_PROXY_API_KEY") or os.environ.get("OPENAI_API_KEY", "")


def bootstrap_litellm_proxy() -> bool:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return bool(resolve_proxy_url())

    proxy_url = resolve_proxy_url()
    if not proxy_url:
        _BOOTSTRAPPED = True
        return False

    os.environ["OPENAI_API_BASE"] = proxy_url
    proxy_key = resolve_proxy_key()

    if ".run.app" in proxy_url:
        if not proxy_key:
            raise RuntimeError(
                "LiteLLM proxy auth is missing. Set `LITELLM_PROXY_API_KEY` or `OPENAI_API_KEY`."
            )
        from app.cloud_run_auth import patch_litellm_for_cloud_run

        os.environ["OPENAI_API_KEY"] = "cloud-run-oidc"
        patch_litellm_for_cloud_run(proxy_url, proxy_key)
    elif proxy_key:
        os.environ["OPENAI_API_KEY"] = proxy_key

    _BOOTSTRAPPED = True
    return True
