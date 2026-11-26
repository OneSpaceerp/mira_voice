"""Migrations are the only way the schema changes (one Alembic migration per change)."""

from alembic import command
from alembic.config import Config


def test_models_and_migrations_agree(alembic_cfg: Config) -> None:
    # Fails if a model changed without a migration (alembic check = autogenerate finds nothing).
    command.check(alembic_cfg)


def test_downgrade_to_base_and_back(alembic_cfg: Config) -> None:
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")
    command.check(alembic_cfg)
