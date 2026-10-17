"""Alembic environment. Run from ``apps/api`` so ``db`` is importable."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from db.models import Base
from db.session import database_url

config = context.config
if config.config_file_name is not None:
    # disable_existing_loggers=False -- this runs in-process on every app
    # startup (db/bootstrap.py::ensure_schema()), not just the Alembic CLI;
    # the default True silently kills the app's own loggers ("guru.access",
    # "uvicorn.error") for the rest of the process, since they're not in
    # alembic.ini's [loggers] section (live-verified 2026-09-12: every
    # request/exception log after the first boot's migration went missing).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

config.set_main_option("sqlalchemy.url", database_url())
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
