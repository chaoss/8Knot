"""Alembic environment for the cache schema.

Connects with cx_common's CACHE_* settings, so migrations target the app's
cache database. Migrations are hand-written until SQLAlchemy Core metadata
is introduced for autogeneration.
"""

from alembic import context
from alembic.script import ScriptDirectory
from sqlalchemy import URL, create_engine, pool

from cache_manager.cx_common import env_dbname, env_host, env_password, env_port, env_user

# Pass the URL object directly; setting it in Alembic's config breaks on '%' in passwords.
database_url = URL.create(
    "postgresql+psycopg2",
    username=env_user,
    password=env_password,
    host=env_host,
    port=int(env_port),
    database=env_dbname,
)

# Autogenerate needs Table/MetaData definitions; it does not require ORM models.
target_metadata = None


def process_revision_directives(migration_context, revision, directives):
    """Assign sequential numeric revision IDs unless the CLI supplies --rev-id."""
    config = migration_context.config
    if not directives or getattr(config.cmd_opts, "rev_id", None):
        return
    scripts = ScriptDirectory.from_config(config)
    revisions = (int(script.revision) for script in scripts.walk_revisions() if script.revision.isdigit())
    directives[0].rev_id = str(max(revisions, default=0) + 1)


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        process_revision_directives=process_revision_directives,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            process_revision_directives=process_revision_directives,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
