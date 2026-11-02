# ria-stats

Tracks AUTO.RIA listings of one car model (Mazda MX-5) over time, so price changes and sales can be looked at afterwards. It collects each listing's price, status and attributes every two days through the official [developers.ria.com](https://developers.ria.com) API, keeps every observation, and saves the listing photos. A web UI and a JSON API sit on top of the SQLite database.

## Run it

You need Docker with Compose and an AUTO.RIA API key.

```bash
cp .env.example .env        # then put your key in RIA_API_KEY
mkdir -p data logs          # the containers write here; Docker would create them owned by root
docker compose up -d --build
```

| What | Address |
| --- | --- |
| Web UI | http://localhost:3000 |
| API (interactive docs at `/docs`) | http://localhost:8000 |
| Read-only database browser | http://localhost:8080 |

Everything listens on localhost only and has no login. Data lives in `data/` (the SQLite file `data/ria.db` and the photos in `data/photos/`), logs in `logs/`.

On the first start the database is empty: open the UI and click **Update**. An update finds the listings and fetches their details, at most 28 API requests at a time (the free plan allows 30 per hour). Fetching about 35 listings therefore takes two updates, best an hour apart, and the photos fill in over a few more. After that the app updates itself on a schedule (between 12:00 and 14:00 Kyiv time) and every listing is refreshed every two days. Photos download alongside, up to 100 per update.

## The web UI

- **Listings.** Toggle Active / Sold / Removed, filter by model, gearbox, price (in USD) and year, and click a column header to sort. A green or red chip shows how a price has changed since the listing was first seen. The dot next to "Last synced" fades as the data ages.
- **A listing.** Click one for its photos, the price history chart, all attributes, every observation, and a **Refresh** button that fetches just that listing now.
- **Stats.** The **Update** button (the same one as in the header), **Force re-discovery** (starts a new refresh cycle and refetches every listing, so it asks first), counts, and the history of every run.
- The sun/moon button in the header switches between light and dark.

## The API

Open http://localhost:8000/docs to try every endpoint. A few examples:

```bash
curl localhost:8000/api/listings                         # all listings
curl 'localhost:8000/api/listings?status=sold'           # status: pending, active, sold, removed (repeatable)
curl localhost:8000/api/listings/40061474                # one listing with its full price history and photos
curl localhost:8000/api/stats                            # counts, pending work, recent runs

curl -X POST localhost:8000/api/update                   # discovery if due, then details and photos
curl -X POST localhost:8000/api/discovery/force          # new cycle: every listing becomes pending again
curl -X POST localhost:8000/api/listings/40061474/refresh  # fetch one listing now
```

Only one update runs at a time; the `POST` endpoints answer `409` while another is running. Photos are served at `/api/photos/<listing id>/<photo id>.jpg`.

## Development

Needs [uv](https://docs.astral.sh/uv/) and Node 22.

```bash
uv sync
uv run alembic upgrade head          # create or update data/ria.db
uv run python -m ria_stats.seed      # brands and the tracked model
uv run uvicorn ria_stats.api:app     # the API, with the scheduler inside
uv run pytest                        # tests

cd frontend && npm install && npm run dev    # UI with hot reload on :5173, proxies /api to :8000
```

The same work from the command line, and one extra: adding an old listing that is already gone from AUTO.RIA (a plain id or a pasted link; it needs the `MX-5` to be a tracked model and the listing to be inactive):

```bash
uv run python -m ria_stats.discovery [--force]                          # search for listings
uv run python -m ria_stats.collector [--max-requests N] [--auto-id N]   # fetch details
uv run python -m ria_stats.backfill <id or link> [...]                  # add listings that are already gone
```

Settings (which model is tracked, the request cap, the refresh interval, photo limits) are in `src/ria_stats/config.py`; the schedule is in `src/ria_stats/scheduler.py`.

## Notes

- Listing data comes from [AUTO.RIA](https://auto.ria.com), which the UI links to as the API terms require.
- The containers run as user 1000 (see `user:` in `docker-compose.yml`); change it if your user id differs.
- The database holds VINs and number plates, and the photos belong to the sellers. Keep it all private.
