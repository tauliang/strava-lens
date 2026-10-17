"""Database configuration; schemas are managed exclusively by Alembic."""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://lens:lens@localhost:5432/lens"
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_session():
    with SessionLocal() as session:
        yield session
