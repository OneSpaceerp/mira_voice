"""Calls into flows, and voicemail (task 1.4 stage 2)

- ivr_flows.number: optional internal number that runs the flow.
- inbound_routes: the destination is an extension *or* a flow (exactly one).
- voicemails: messages left through a flow's voicemail node.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ivr_flows", sa.Column("number", sa.String(16), nullable=True))
    op.create_unique_constraint(
        op.f("uq_ivr_flows_tenant_id_number"), "ivr_flows", ["tenant_id", "number"]
    )
    op.create_check_constraint(
        op.f("ck_ivr_flows_number_digits"),
        "ivr_flows",
        "number IS NULL OR number ~ '^[0-9]{2,16}$'",
    )

    op.alter_column(
        "inbound_routes", "destination_number", existing_type=sa.String(16), nullable=True
    )
    op.drop_constraint(
        op.f("ck_inbound_routes_destination_digits"), "inbound_routes", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_inbound_routes_destination_digits"),
        "inbound_routes",
        "destination_number IS NULL OR destination_number ~ '^[0-9]{2,16}$'",
    )
    op.add_column(
        "inbound_routes",
        sa.Column(
            "destination_flow_id",
            sa.Uuid(),
            sa.ForeignKey(
                "ivr_flows.id",
                ondelete="RESTRICT",
                name=op.f("fk_inbound_routes_destination_flow_id_ivr_flows"),
            ),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_inbound_routes_destination_flow_id"), "inbound_routes", ["destination_flow_id"]
    )
    op.create_check_constraint(
        op.f("ck_inbound_routes_one_destination"),
        "inbound_routes",
        "(destination_number IS NULL) <> (destination_flow_id IS NULL)",
    )

    op.create_table(
        "voicemails",
        sa.Column("mailbox", sa.String(16), nullable=False),
        sa.Column("caller_number", sa.String(64), nullable=False),
        sa.Column(
            "call_id",
            sa.Uuid(),
            sa.ForeignKey(
                "calls.id", ondelete="SET NULL", name=op.f("fk_voicemails_call_id_calls")
            ),
            nullable=True,
        ),
        sa.Column(
            "flow_id",
            sa.Uuid(),
            sa.ForeignKey(
                "ivr_flows.id", ondelete="SET NULL", name=op.f("fk_voicemails_flow_id_ivr_flows")
            ),
            nullable=True,
        ),
        sa.Column("recording_name", sa.String(200), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("heard", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey(
                "tenants.id", ondelete="RESTRICT", name=op.f("fk_voicemails_tenant_id_tenants")
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_voicemails")),
        sa.UniqueConstraint("recording_name", name=op.f("uq_voicemails_recording_name")),
        sa.CheckConstraint("duration_seconds >= 0", name=op.f("ck_voicemails_duration_positive")),
    )
    for col in ("tenant_id", "mailbox", "call_id"):
        op.create_index(op.f(f"ix_voicemails_{col}"), "voicemails", [col])
    op.create_index(
        "ix_voicemails_tenant_mailbox", "voicemails", ["tenant_id", "mailbox", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("voicemails")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM inbound_routes WHERE destination_flow_id IS NOT NULL) "
        "THEN RAISE EXCEPTION 'inbound routes point at flows: change them before downgrading'; "
        "END IF; END $$"
    )
    op.drop_constraint(op.f("ck_inbound_routes_one_destination"), "inbound_routes", type_="check")
    op.drop_index(op.f("ix_inbound_routes_destination_flow_id"), table_name="inbound_routes")
    op.drop_column("inbound_routes", "destination_flow_id")
    op.drop_constraint(
        op.f("ck_inbound_routes_destination_digits"), "inbound_routes", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_inbound_routes_destination_digits"),
        "inbound_routes",
        "destination_number ~ '^[0-9]{2,16}$'",
    )
    op.alter_column(
        "inbound_routes", "destination_number", existing_type=sa.String(16), nullable=False
    )
    op.drop_constraint(op.f("ck_ivr_flows_number_digits"), "ivr_flows", type_="check")
    op.drop_constraint(op.f("uq_ivr_flows_tenant_id_number"), "ivr_flows", type_="unique")
    op.drop_column("ivr_flows", "number")
