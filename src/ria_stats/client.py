import logging
import os
import re

import httpx
from dotenv import load_dotenv

BASE_URL = "https://developers.ria.com"


class _RedactApiKey(logging.Filter):
    """httpx logs every request URL at INFO, and the API key is in the query string."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = re.sub(r"(api_key=)[^&\s\"]+", r"\1***", record.getMessage())
        record.args = ()
        return True


logging.getLogger("httpx").addFilter(_RedactApiKey())


class RateLimited(Exception):
    """The API answered HTTP 429. The caller should stop, not retry."""


class RiaClient:
    """Thin API wrapper that counts every request it sends (the API reports no quota)."""

    def __init__(self) -> None:
        load_dotenv()
        key = os.environ.get("RIA_API_KEY")
        if not key:
            raise RuntimeError("RIA_API_KEY is not set (see .env.example)")
        self._key = key
        self._http = httpx.Client(base_url=BASE_URL, timeout=30)
        self.requests_used = 0

    def get(self, path: str, **params) -> httpx.Response:
        """Return the response for any status except 429, which raises RateLimited."""
        self.requests_used += 1
        response = self._http.get(path, params={"api_key": self._key, **params})
        if response.status_code == 429:
            raise RateLimited(path)
        return response

    def search(self, brand_ria_id: int, model_ria_id: int, page: int) -> httpx.Response:
        return self.get(
            "/auto/search",
            category_id=1,
            **{"marka_id[0]": brand_ria_id, "model_id[0]": model_ria_id},
            countpage=100,
            page=page,
        )

    def info(self, auto_id: int) -> httpx.Response:
        return self.get("/auto/info", auto_id=auto_id)

    def close(self) -> None:
        self._http.close()
