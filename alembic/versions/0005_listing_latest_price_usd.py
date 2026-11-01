"""listing latest price usd

Revision ID: 0005_listing_latest_price_usd
Revises: 0004_trigger_and_listing_latest
Create Date: 2026-11-01 13:28:56.093988

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005_listing_latest_price_usd'
down_revision: Union[str, Sequence[str], None] = '0004_trigger_and_listing_latest'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # price is in the seller's currency; price_usd (as converted on the last fetch) lets callers
    # sort and compare listings priced in different currencies.
    op.execute("DROP VIEW listing_latest")
    op.execute("""
        CREATE VIEW listing_latest AS
        WITH ordered AS (
            SELECT snapshot_id, listing_id, listed_currency, listed_price, observed_at,
                   ROW_NUMBER() OVER (PARTITION BY listing_id ORDER BY snapshot_id DESC) AS rn_last,
                   ROW_NUMBER() OVER (PARTITION BY listing_id ORDER BY snapshot_id) AS rn_first
            FROM snapshot_prices
        ), newest AS (
            SELECT listing_id, in_search FROM (
                SELECT listing_id, in_search,
                       ROW_NUMBER() OVER (PARTITION BY listing_id ORDER BY id DESC) AS rn
                FROM listing_snapshots
            ) WHERE rn = 1
        ), changes AS (
            SELECT listing_id, COUNT(*) AS price_changes FROM price_changes GROUP BY listing_id
        )
        SELECT l.id AS listing_id, l.ria_auto_id,
               b.id AS brand_id, b.name AS brand, m.id AS model_id, m.name AS model,
               l.title, l.year, l.link, l.vin,
               loc.city_name AS city, loc.region_name AS region,
               l.posted_at, l.first_seen_at,
               cur.observed_at AS last_observed_at,
               cur.listed_currency AS currency, cur.listed_price AS price,
               ini.listed_price AS first_price,
               s.price_usd, s.mileage_k_km, s.is_sold, s.active, s.status_id,
               COALESCE(c.price_changes, 0) AS price_changes,
               CASE WHEN cur.snapshot_id IS NULL THEN 'pending'
                    WHEN n.in_search = 1 THEN 'active'
                    WHEN s.is_sold = 1 THEN 'sold'
                    ELSE 'removed' END AS status
        FROM listings l
        JOIN models m ON m.id = l.model_id
        JOIN brands b ON b.id = m.brand_id
        LEFT JOIN locations loc ON loc.id = l.location_id
        LEFT JOIN ordered cur ON cur.listing_id = l.id AND cur.rn_last = 1
        LEFT JOIN ordered ini ON ini.listing_id = l.id AND ini.rn_first = 1
        LEFT JOIN listing_snapshots s ON s.id = cur.snapshot_id
        LEFT JOIN newest n ON n.listing_id = l.id
        LEFT JOIN changes c ON c.listing_id = l.id
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP VIEW listing_latest")
    op.execute("""
        CREATE VIEW listing_latest AS
        WITH ordered AS (
            SELECT snapshot_id, listing_id, listed_currency, listed_price, observed_at,
                   ROW_NUMBER() OVER (PARTITION BY listing_id ORDER BY snapshot_id DESC) AS rn_last,
                   ROW_NUMBER() OVER (PARTITION BY listing_id ORDER BY snapshot_id) AS rn_first
            FROM snapshot_prices
        ), newest AS (
            SELECT listing_id, in_search FROM (
                SELECT listing_id, in_search,
                       ROW_NUMBER() OVER (PARTITION BY listing_id ORDER BY id DESC) AS rn
                FROM listing_snapshots
            ) WHERE rn = 1
        ), changes AS (
            SELECT listing_id, COUNT(*) AS price_changes FROM price_changes GROUP BY listing_id
        )
        SELECT l.id AS listing_id, l.ria_auto_id,
               b.id AS brand_id, b.name AS brand, m.id AS model_id, m.name AS model,
               l.title, l.year, l.link, l.vin,
               loc.city_name AS city, loc.region_name AS region,
               l.posted_at, l.first_seen_at,
               cur.observed_at AS last_observed_at,
               cur.listed_currency AS currency, cur.listed_price AS price,
               ini.listed_price AS first_price,
               s.mileage_k_km, s.is_sold, s.active, s.status_id,
               COALESCE(c.price_changes, 0) AS price_changes,
               CASE WHEN cur.snapshot_id IS NULL THEN 'pending'
                    WHEN n.in_search = 1 THEN 'active'
                    WHEN s.is_sold = 1 THEN 'sold'
                    ELSE 'removed' END AS status
        FROM listings l
        JOIN models m ON m.id = l.model_id
        JOIN brands b ON b.id = m.brand_id
        LEFT JOIN locations loc ON loc.id = l.location_id
        LEFT JOIN ordered cur ON cur.listing_id = l.id AND cur.rn_last = 1
        LEFT JOIN ordered ini ON ini.listing_id = l.id AND ini.rn_first = 1
        LEFT JOIN listing_snapshots s ON s.id = cur.snapshot_id
        LEFT JOIN newest n ON n.listing_id = l.id
        LEFT JOIN changes c ON c.listing_id = l.id
    """)
