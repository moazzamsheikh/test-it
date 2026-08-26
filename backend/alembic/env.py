"""Alembic environment. Uses a sync engine from app settings and the ORM metadata."""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

# Import models so they register on Base.metadata.
import app.models  # noqa: F401
from alembic import context
from app.core.config import settings
from app.core.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(
    obj: object, name: str | None, type_: str, reflected: bool, compare_to: object | None
) -> bool:
    """Only manage objects defined in our ORM metadata.

    PostGIS and its tiger-geocoder / topology extensions create many tables in
    this database. They are reflected but have no counterpart in our metadata
    (compare_to is None); skipping them stops autogenerate emitting DROP for
    extension-managed objects.
    """
    return not (reflected and compare_to is None)


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
