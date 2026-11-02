import pytest

from ria_stats import backfill, collector


def test_a_test_without_the_db_fixture_cannot_reach_the_real_database():
    for module in (collector, backfill):
        with pytest.raises(RuntimeError, match="real database"):
            module.SessionLocal()
