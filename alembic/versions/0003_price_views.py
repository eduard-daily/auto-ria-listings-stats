"""price views

Revision ID: 0003_price_views
Revises: 0002_discovery_runs
Create Date: 2026-11-01 12:20:44.417857

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003_price_views'
down_revision: Union[str, Sequence[str], None] = '0002_discovery_runs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # The price a seller set is the one in main_currency; the other two are converted at the
    # day's rate and drift with the exchange rate. Compare listed_price, never price_usd/eur/uah.
    # listed_price is NULL for a main_currency other than USD/EUR/UAH, so odd values stay visible.
    op.execute("""
        CREATE VIEW snapshot_prices AS
        SELECT s.id AS snapshot_id, s.listing_id, l.ria_auto_id, s.run_id, s.observed_at,
               s.main_currency AS listed_currency,
               CASE s.main_currency
                   WHEN 'USD' THEN s.price_usd
                   WHEN 'EUR' THEN s.price_eur
                   WHEN 'UAH' THEN s.price_uah
               END AS listed_price,
               s.price_usd, s.price_eur, s.price_uah
        FROM listing_snapshots s
        JOIN listings l ON l.id = s.listing_id
        WHERE s.fetch_ok = 1
    """)
    # One row per change of listed_price between a listing's consecutive successful snapshots.
    # A currency switch by the seller is not comparable and is left out.
    op.execute("""
        CREATE VIEW price_changes AS
        WITH ordered AS (
            SELECT *,
                   LAG(listed_price) OVER w AS was_price,
                   LAG(listed_currency) OVER w AS was_currency,
                   LAG(observed_at) OVER w AS was_at
            FROM snapshot_prices
            WINDOW w AS (PARTITION BY listing_id ORDER BY snapshot_id)
        )
        SELECT listing_id, ria_auto_id, was_at, observed_at AS now_at,
               listed_currency AS currency, was_price, listed_price AS now_price,
               listed_price - was_price AS diff,
               ROUND(100.0 * (listed_price - was_price) / was_price, 1) AS diff_pct
        FROM ordered
        WHERE was_price IS NOT NULL AND listed_price IS NOT NULL
          AND was_currency = listed_currency AND listed_price <> was_price
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP VIEW price_changes")
    op.execute("DROP VIEW snapshot_prices")
