from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import make_url


config = context.config
target_metadata = None


def _get_database_url() -> str:
    database_url = os.getenv("RAG_DATABASE_URL", "").strip()
    if database_url:
        return database_url

    ini_database_url = config.get_main_option("sqlalchemy.url", "").strip()
    if ini_database_url:
        return ini_database_url

    raise RuntimeError("RAG_DATABASE_URL must be set for Alembic migrations")


def _normalize_database_url(database_url: str) -> str:
    url = make_url(database_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return url.render_as_string(hide_password=False)


def run_migrations_offline() -> None:
    context.configure(
        url=_get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        _normalize_database_url(_get_database_url()),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
