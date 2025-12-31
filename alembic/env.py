from logging.config import fileConfig
import os
import sys
from pathlib import Path

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Import database Base and all models
# Note: This will create an engine, so DATABASE_URL must be set
# For autogenerate to work, we need to import all models
try:
    from database.database import Base
    # Import all models so Alembic can detect them for autogenerate
    import schemas.user_model
    import schemas.subscription_model
    import schemas.packages_model
    import schemas.packages_permission_model
    import schemas.permission_model
    import schemas.chat_model
    import schemas.messages_model
    import schemas.library_model
    import schemas.usage_log_model
except (ImportError, ModuleNotFoundError, ValueError) as e:
    # If import fails (e.g., missing DATABASE_URL, psycopg2, or invalid URL), 
    # we can still run manual migrations
    Base = None
    import warnings
    warnings.warn(
        f"Could not import models: {e}. "
        "Manual migrations will still work, but autogenerate requires all dependencies."
    )

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Get database URL from environment
database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata if Base is not None else None

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url") or database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Use database URL from environment if available
    configuration = config.get_section(config.config_ini_section, {})
    if database_url:
        configuration["sqlalchemy.url"] = database_url
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
