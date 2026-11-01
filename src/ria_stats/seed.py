"""Seed reference data. Idempotent: rows are matched by ria_id and updated in place.

Usage: uv run python -m ria_stats.seed
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ria_stats.db import SessionLocal
from ria_stats.models import Brand, Model

# (ria_id, name, name_eng). name_eng is the AUTO.RIA URL slug (markNameEng in /auto/info).
# Ids and names come from data/raw/marks.json. Only fiat and mazda slugs were seen in
# /auto/info; the others follow the same lowercase pattern and are unverified.
BRANDS = [
    (47, "Mazda", "mazda"),
    (23, "Fiat", "fiat"),
    (79, "Toyota", "toyota"),
    (29, "Hyundai", "hyundai"),
    (84, "Volkswagen", "volkswagen"),
    (70, "Skoda", "skoda"),
    (9, "BMW", "bmw"),
    (48, "Mercedes-Benz", "mercedes-benz"),
    (6, "Audi", "audi"),
    (62, "Renault", "renault"),
]

# (brand ria_id, model ria_id, name, name_eng). Only tracked models are seeded.
MODELS = [
    (47, 399, "MX-5", "mx-5"),
]


def seed(session: Session) -> None:
    brands: dict[int, Brand] = {}
    for ria_id, name, name_eng in BRANDS:
        brand = session.scalar(select(Brand).where(Brand.ria_id == ria_id))
        if brand is None:
            brand = Brand(ria_id=ria_id, name=name, name_eng=name_eng)
            session.add(brand)
        else:
            brand.name, brand.name_eng = name, name_eng
        brands[ria_id] = brand

    for brand_ria_id, ria_id, name, name_eng in MODELS:
        model = session.scalar(select(Model).where(Model.ria_id == ria_id))
        if model is None:
            session.add(Model(brand=brands[brand_ria_id], ria_id=ria_id, name=name, name_eng=name_eng))
        else:
            model.brand, model.name, model.name_eng = brands[brand_ria_id], name, name_eng


if __name__ == "__main__":
    with SessionLocal.begin() as session:
        seed(session)
