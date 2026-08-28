from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from scripts.config import load_config, load_env
from scripts.database import db_url
from scripts.models import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    load_env()
    url = db_url(load_config().database_url)
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    load_env()
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = db_url(load_config().database_url)
    engine = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
