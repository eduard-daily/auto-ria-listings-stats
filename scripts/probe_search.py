"""Probe AUTO.RIA search for Mazda MX-5 and save raw responses to data/raw/.

Costs 3 requests: marks lookup, models lookup, one search page.
"""
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

BASE = "https://developers.ria.com"
RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

load_dotenv()
KEY = os.environ.get("RIA_API_KEY")
if not KEY:
    sys.exit("RIA_API_KEY is not set (see .env.example)")


def get(client: httpx.Client, name: str, path: str, **params):
    r = client.get(BASE + path, params={"api_key": KEY, **params})
    print(f"{r.status_code} {path}  rate-limit headers: "
          f"{ {k: v for k, v in r.headers.items() if 'limit' in k.lower() or 'remaining' in k.lower()} }")
    r.raise_for_status()
    data = r.json()
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return data


def find(items: list[dict], name: str) -> dict:
    # Category endpoints return [{"name": ..., "value": id}, ...]
    return next(i for i in items if i["name"].lower() == name.lower())


with httpx.Client(timeout=30) as c:
    marks = get(c, "marks", "/auto/categories/1/marks")
    mazda = find(marks, "Mazda")["value"]
    models = get(c, "mazda_models", f"/auto/categories/1/marks/{mazda}/models")
    mx5 = find(models, "MX-5")["value"]
    print(f"Mazda marka_id={mazda}, MX-5 model_id={mx5}")

    result = get(
        c, "search_mx5", "/auto/search",
        category_id=1, **{"marka_id[0]": mazda, "model_id[0]": mx5},
        countpage=100, page=0,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2)[:3000])
