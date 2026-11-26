"""Mira Flow v1 storage and the prompt library (task 1.4, ADR 0009)

- ivr_flows becomes the stable flow identity: name, description, the draft being edited and
  the published version in use. Its 0.4 placeholder columns (one row per version) go away.
  The table was never written to; the migration stops if it holds rows rather than lose them.
- ivr_flow_versions: immutable published snapshots (rollback = point at an older one).
- prompts + prompt_audio: recorded messages per tenant, one recording per language.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk() -> sa.Column[object]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _tenant(table: str) -> sa.Column[object]:
    return sa.Column(
        "tenant_id",
        sa.Uuid(),
        sa.ForeignKey(
            "tenants.id", ondelete="RESTRICT", name=op.f(f"fk_{table}_tenant_id_tenants")
        ),
        nullable=False,
    )


def _now(name: str) -> sa.Column[object]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM ivr_flows) THEN "
        "RAISE EXCEPTION 'ivr_flows has rows: migrate them by hand before 0005'; END IF; END $$"
    )
    for column in ("version", "status", "definition", "published_at"):
        op.drop_column("ivr_flows", column)  # their constraints go with them
    op.add_column(
        "ivr_flows", sa.Column("description", sa.String(500), server_default="", nullable=False)
    )
    op.add_column(
        "ivr_flows",
        sa.Column(
            "draft", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
    )
    op.add_column("ivr_flows", sa.Column("published_version", sa.Integer(), nullable=True))
    op.create_unique_constraint(
        op.f("uq_ivr_flows_tenant_id_name"), "ivr_flows", ["tenant_id", "name"]
    )
    op.create_check_constraint(
        op.f("ck_ivr_flows_published_positive"),
        "ivr_flows",
        "published_version IS NULL OR published_version > 0",
    )

    op.create_table(
        "ivr_flow_versions",
        _uuid_pk(),
        _tenant("ivr_flow_versions"),
        sa.Column(
            "flow_id",
            sa.Uuid(),
            sa.ForeignKey(
                "ivr_flows.id",
                ondelete="CASCADE",
                name=op.f("fk_ivr_flow_versions_flow_id_ivr_flows"),
            ),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        _now("published_at"),
        sa.Column(
            "published_by",
            sa.Uuid(),
            sa.ForeignKey(
                "users.id",
                ondelete="SET NULL",
                name=op.f("fk_ivr_flow_versions_published_by_users"),
            ),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ivr_flow_versions")),
        sa.UniqueConstraint(
            "flow_id", "version", name=op.f("uq_ivr_flow_versions_flow_id_version")
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_ivr_flow_versions_version_positive")),
    )
    for col in ("tenant_id", "flow_id"):
        op.create_index(op.f(f"ix_ivr_flow_versions_{col}"), "ivr_flow_versions", [col])

    op.create_table(
        "prompts",
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        _uuid_pk(),
        _now("created_at"),
        _now("updated_at"),
        _tenant("prompts"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prompts")),
        sa.UniqueConstraint("tenant_id", "name", name=op.f("uq_prompts_tenant_id_name")),
    )
    op.create_index(op.f("ix_prompts_tenant_id"), "prompts", ["tenant_id"])

    op.create_table(
        "prompt_audio",
        _uuid_pk(),
        _tenant("prompt_audio"),
        sa.Column(
            "prompt_id",
            sa.Uuid(),
            sa.ForeignKey(
                "prompts.id", ondelete="CASCADE", name=op.f("fk_prompt_audio_prompt_id_prompts")
            ),
            nullable=False,
        ),
        sa.Column(
            "language",
            sa.Enum(
                "ar",
                "en",
                "fr",
                name="prompt_language",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("sample_rate", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        _now("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prompt_audio")),
        sa.UniqueConstraint(
            "prompt_id", "language", name=op.f("uq_prompt_audio_prompt_id_language")
        ),
        sa.CheckConstraint(
            "sample_rate IN (8000, 16000)", name=op.f("ck_prompt_audio_sample_rate_supported")
        ),
        sa.CheckConstraint("duration_ms > 0", name=op.f("ck_prompt_audio_duration_positive")),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_prompt_audio_sha256_hex")),
    )
    for col in ("tenant_id", "prompt_id"):
        op.create_index(op.f(f"ix_prompt_audio_{col}"), "prompt_audio", [col])


def downgrade() -> None:
    op.drop_table("prompt_audio")
    op.drop_table("prompts")
    op.drop_table("ivr_flow_versions")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM ivr_flows) THEN "
        "RAISE EXCEPTION 'ivr_flows has rows: they cannot go back to the 0.4 layout'; END IF; END $$"
    )
    op.drop_constraint(op.f("ck_ivr_flows_published_positive"), "ivr_flows", type_="check")
    op.drop_constraint(op.f("uq_ivr_flows_tenant_id_name"), "ivr_flows", type_="unique")
    for column in ("published_version", "draft", "description"):
        op.drop_column("ivr_flows", column)
    op.add_column("ivr_flows", sa.Column("version", sa.Integer(), nullable=False))
    op.add_column(
        "ivr_flows",
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "published",
                "archived",
                name="flow_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
    )
    op.add_column("ivr_flows", sa.Column("definition", postgresql.JSONB(), nullable=False))
    op.add_column("ivr_flows", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(op.f("ck_ivr_flows_version_positive"), "ivr_flows", "version > 0")
    op.create_unique_constraint(
        op.f("uq_ivr_flows_tenant_id_name_version"), "ivr_flows", ["tenant_id", "name", "version"]
    )
