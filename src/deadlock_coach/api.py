from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from deadlock_coach.config import Settings


class DeadlockApiClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build_url(self, path: str, params: dict[str, Any] | None = None) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            base = path
        else:
            base = f"{self.settings.api_base_url.rstrip('/')}/{path.lstrip('/')}"

        query_params = {key: value for key, value in (params or {}).items() if value is not None}
        if not query_params:
            return base
        return f"{base}?{urlencode(query_params, doseq=True)}"

    def fetch_json(self, path: str, params: dict[str, Any] | None = None) -> tuple[str, Any]:
        url = self.build_url(path, params=params)
        headers = {"Accept": "application/json", "User-Agent": "deadlock-coach/0.1.0"}
        if self.settings.api_key:
            headers["X-API-KEY"] = self.settings.api_key

        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} for {url}: {message}") from exc
        except URLError as exc:
            raise RuntimeError(f"Failed to reach {url}: {exc.reason}") from exc

        try:
            return url, json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Expected JSON from {url}") from exc

