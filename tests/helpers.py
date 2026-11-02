import copy
import json
from pathlib import Path

import httpx
from alembic.config import Config

from ria_stats.client import RateLimited

ROOT = Path(__file__).resolve().parents[1]
SECRET_KEY = "SECRET-KEY-VALUE"
FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def alembic_config() -> Config:
    return Config(str(ROOT / "alembic.ini"))


def json_response(body, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=body, request=httpx.Request("GET", "http://fake"))


class FakeRia:
    """Stands in for RiaClient. info() answers with the sanitized fixture of an active listing."""

    def __init__(self, ids=(), rate_limit_after: int | None = None, missing=(), bad=(), search_status: int = 200,
                 error: Exception | None = None):
        self.ids = list(ids)
        self.bad = set(bad)  # ids whose /auto/info answers 200 with an unusable body
        self.search_status = search_status
        self.error = error  # raised by every search and info call, like a network failure
        self.rate_limit_after = rate_limit_after  # requests beyond this many raise RateLimited
        self.missing = set(missing)  # ids whose /auto/info answers 404
        self.requests_used = 0

    def _count(self) -> None:
        self.requests_used += 1
        if self.rate_limit_after is not None and self.requests_used > self.rate_limit_after:
            raise RateLimited("fake")

    def search(self, brand_ria_id: int, model_ria_id: int, page: int) -> httpx.Response:
        self._count()
        if self.error:
            raise self.error
        if self.search_status != 200:  # a real error response knows the URL it came from, key included
            url = f"https://developers.ria.com/auto/search?api_key={SECRET_KEY}&category_id=1"
            return httpx.Response(self.search_status, json={}, request=httpx.Request("GET", url))
        ids = [str(i) for i in self.ids] if page == 0 else []
        return json_response({"result": {"search_result": {"count": len(self.ids), "ids": ids}}})

    def info(self, auto_id: int) -> httpx.Response:
        self._count()
        if self.error:
            raise self.error
        if auto_id in self.missing:
            return json_response({}, 404)
        data = copy.deepcopy(load_fixture("info_active"))
        data["autoData"]["autoId"] = auto_id
        data["USD"] = 10000 + auto_id
        if auto_id in self.bad:
            data["addDate"] = "not a date"
        return json_response(data)

    def close(self) -> None:
        pass
