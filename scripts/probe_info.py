"""Fetch raw /auto/info for one listing and save it to data/raw/. Costs 1 request.

Usage: uv run scripts/probe_info.py <auto_id>
"""
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

load_dotenv()
KEY = os.environ.get("RIA_API_KEY")
if not KEY:
    sys.exit("RIA_API_KEY is not set (see .env.example)")
if len(sys.argv) != 2:
    sys.exit(__doc__)
auto_id = sys.argv[1]

r = httpx.get("https://developers.ria.com/auto/info",
              params={"api_key": KEY, "auto_id": auto_id}, timeout=30)
print(r.status_code)
r.raise_for_status()
RAW.mkdir(parents=True, exist_ok=True)
out = RAW / f"info_{auto_id}.json"
out.write_text(json.dumps(r.json(), ensure_ascii=False, indent=2))
print(f"saved {out}")
