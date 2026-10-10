from logging.config import fileConfig

from sqlalchemy import Connection

from alembic import context
from app.core.config import get_settings
from app.db import models  # noqa: F401 - register models
from app.db.base import Base
from app.db.session import make_engine

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    return url or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        do_run(connection)
        return
    engine = make_engine(database_url())
    with engine.connect() as conn:
        do_run(conn)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
