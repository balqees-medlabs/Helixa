"""Alembic environment: reads DATABASE_URL from the environment.

No credentials are hardcoded; migrations run against the admin connection
pointed at by DATABASE_URL (see infra/.env.example).
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Autogenerate compares against this. Import model modules before diffing so
# every table is visible (see app/db/base.py). Migrations here are hand-written.
target_metadata = Base.metadata


def _database_url() -> str:
    """Return DATABASE_URL with the psycopg (v3) driver forced.

    DATABASE_URL is kept as a plain libpq URL (``postgresql://``) so the same
    value works with psql/pg_dump/pg_restore in the infra scripts. SQLAlchemy
    needs an explicit driver, so we set it here rather than in the env file.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Export it (admin connection, e.g. "
            "postgresql://user:pass@127.0.0.1:5432/helixa) before running migrations."
        )
    return make_url(url).set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    config.set_main_option("sqlalchemy.url", _database_url())
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
