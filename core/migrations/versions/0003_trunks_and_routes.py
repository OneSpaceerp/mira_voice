"""Trunks and call routing (task 1.2, ADR 0007)

- trunks: encrypted carrier password (auth_secret_enc, Fernet), HA1 for GSM gateways that
  register to Mira (sip_ha1), carrier signalling IPs (inbound_ips).
- outbound_routes + outbound_route_trunks: dialled pattern -> ordered trunks (failover).
- inbound_routes: called number (DID) on a trunk -> extension.
- Realtime views: trunks leave them. A trunk needs objects the views cannot express
  (identify by header, outbound auth with a decrypted password, registration), so Mira Core
  renders all trunk objects into generated/pjsip_mira.conf instead (asterisk_config.py).
  ps_endpoints also gains `mailboxes` (NULL): Asterisk's MWI module asks for it.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Must match asterisk_config.tenant_context().
TENANT_CONTEXT = "'t_' || replace(t.id::text, '-', '')"

ACTIVE_EXTENSIONS = """
    FROM public.extensions e
    JOIN public.tenants t ON t.id = e.tenant_id
    LEFT JOIN public.users u ON u.id = e.user_id
    WHERE e.enabled AND t.status = 'active' AND (u.id IS NULL OR u.is_active)
"""

# SQL assembled from constants only (no input).  ruff: S608 is ignored for migrations.
PS_ENDPOINTS = f"""
CREATE VIEW asterisk.ps_endpoints AS
    SELECT
        e.sip_username::text AS id,
        e.sip_username::text AS aors,
        e.sip_username::text AS auth,
        {TENANT_CONTEXT}::text AS context,
        format('"%s" <%s>', replace(e.display_name, '"', ''), e.number)::text AS callerid,
        'yes'::text AS send_pai,
        'no'::text AS trust_id_inbound,
        NULL::text AS outbound_proxy,
        NULL::text AS from_domain,
        NULL::text AS mailboxes,
        'transport-kamailio'::text AS transport,
        'all'::text AS disallow,
        'ulaw,alaw,g722'::text AS allow,
        'no'::text AS direct_media,
        'no'::text AS rtp_symmetric,
        'no'::text AS force_rport,
        'no'::text AS rewrite_contact,
        'no'::text AS ice_support,
        'no'::text AS media_encryption,
        '127.0.0.1'::text AS media_address,
        'yes'::text AS bind_rtp_to_media_address,
        'rfc4733'::text AS dtmf_mode,
        CASE t.default_locale WHEN 'fr' THEN 'fr' ELSE 'en' END::text AS language,
        t.id::text AS tenantid
    {ACTIVE_EXTENSIONS}
"""

PS_AORS = f"""
CREATE VIEW asterisk.ps_aors AS
    SELECT
        e.sip_username::text AS id,
        NULL::text AS contact,
        '1'::text AS max_contacts,
        'yes'::text AS remove_existing,
        'yes'::text AS remove_unavailable,
        '30'::text AS qualify_frequency,
        'yes'::text AS support_path
    {ACTIVE_EXTENSIONS}
"""


def _recreate_views(endpoints: str, aors: str) -> None:
    op.execute("DROP VIEW asterisk.ps_endpoints")
    op.execute("DROP VIEW asterisk.ps_aors")
    op.execute(endpoints)
    op.execute(aors)
    op.execute("GRANT SELECT ON asterisk.ps_endpoints, asterisk.ps_aors TO asterisk")


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def _id_and_tenant(table: str) -> list[sa.Column[object]]:
    return [
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey(
                "tenants.id", ondelete="RESTRICT", name=op.f(f"fk_{table}_tenant_id_tenants")
            ),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.add_column("trunks", sa.Column("auth_secret_enc", sa.Text(), nullable=True))
    op.add_column("trunks", sa.Column("sip_ha1", sa.String(length=32), nullable=True))
    op.add_column(
        "trunks",
        sa.Column(
            "inbound_ips",
            postgresql.ARRAY(sa.String(length=45)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_trunks_ha1_hex"), "trunks", "sip_ha1 IS NULL OR sip_ha1 ~ '^[0-9a-f]{32}$'"
    )

    op.create_table(
        "outbound_routes",
        *_id_and_tenant("outbound_routes"),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("pattern", sa.String(length=32), nullable=False),
        sa.Column("strip_digits", sa.Integer(), nullable=False),
        sa.Column("prepend", sa.String(length=16), nullable=False),
        sa.Column("caller_id_number", sa.String(length=32), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbound_routes")),
        sa.UniqueConstraint("tenant_id", "name", name=op.f("uq_outbound_routes_tenant_id_name")),
        sa.CheckConstraint(
            r"pattern ~ '^[0-9XZN.!+*#\[\]-]{1,32}$'", name=op.f("ck_outbound_routes_pattern_chars")
        ),
        sa.CheckConstraint(
            "strip_digits BETWEEN 0 AND 20", name=op.f("ck_outbound_routes_strip_range")
        ),
        sa.CheckConstraint(
            "prepend ~ '^[+]?[0-9]{0,15}$'", name=op.f("ck_outbound_routes_prepend_digits")
        ),
        sa.CheckConstraint(
            "caller_id_number IS NULL OR caller_id_number ~ '^[+]?[0-9]{2,20}$'",
            name=op.f("ck_outbound_routes_cid_digits"),
        ),
    )
    op.create_index(op.f("ix_outbound_routes_tenant_id"), "outbound_routes", ["tenant_id"])

    op.create_table(
        "outbound_route_trunks",
        *_id_and_tenant("outbound_route_trunks"),
        sa.Column(
            "route_id",
            sa.Uuid(),
            sa.ForeignKey(
                "outbound_routes.id",
                ondelete="CASCADE",
                name=op.f("fk_outbound_route_trunks_route_id_outbound_routes"),
            ),
            nullable=False,
        ),
        sa.Column(
            "trunk_id",
            sa.Uuid(),
            sa.ForeignKey(
                "trunks.id",
                ondelete="CASCADE",
                name=op.f("fk_outbound_route_trunks_trunk_id_trunks"),
            ),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbound_route_trunks")),
        sa.UniqueConstraint(
            "route_id", "position", name=op.f("uq_outbound_route_trunks_route_id_position")
        ),
        sa.UniqueConstraint(
            "route_id", "trunk_id", name=op.f("uq_outbound_route_trunks_route_id_trunk_id")
        ),
        sa.CheckConstraint(
            "position BETWEEN 0 AND 9", name=op.f("ck_outbound_route_trunks_position_range")
        ),
    )
    for col in ("tenant_id", "route_id", "trunk_id"):
        op.create_index(op.f(f"ix_outbound_route_trunks_{col}"), "outbound_route_trunks", [col])

    op.create_table(
        "inbound_routes",
        *_id_and_tenant("inbound_routes"),
        sa.Column("did", sa.String(length=24), nullable=False),
        sa.Column(
            "trunk_id",
            sa.Uuid(),
            sa.ForeignKey(
                "trunks.id", ondelete="CASCADE", name=op.f("fk_inbound_routes_trunk_id_trunks")
            ),
            nullable=True,
        ),
        sa.Column("destination_number", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inbound_routes")),
        sa.UniqueConstraint(
            "tenant_id",
            "trunk_id",
            "did",
            name=op.f("uq_inbound_routes_tenant_id_trunk_id_did"),
            postgresql_nulls_not_distinct=True,
        ),
        sa.CheckConstraint(
            "did = '*' OR did ~ '^[+]?[0-9]{1,20}$'", name=op.f("ck_inbound_routes_did_format")
        ),
        sa.CheckConstraint(
            "destination_number ~ '^[0-9]{2,16}$'",
            name=op.f("ck_inbound_routes_destination_digits"),
        ),
    )
    for col in ("tenant_id", "trunk_id"):
        op.create_index(op.f(f"ix_inbound_routes_{col}"), "inbound_routes", [col])

    _recreate_views(PS_ENDPOINTS, PS_AORS)


def downgrade() -> None:
    # The 0002 views (with trunk rows) are restored from that migration's own SQL.
    import importlib.util
    from pathlib import Path

    path = Path(__file__).with_name("0002_asterisk_realtime_views.py")
    spec = importlib.util.spec_from_file_location("mira_migration_0002", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    v2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v2)
    _recreate_views(v2.PS_ENDPOINTS, v2.PS_AORS)
    op.drop_table("inbound_routes")
    op.drop_table("outbound_route_trunks")
    op.drop_table("outbound_routes")
    op.drop_constraint(op.f("ck_trunks_ha1_hex"), "trunks", type_="check")
    op.drop_column("trunks", "inbound_ips")
    op.drop_column("trunks", "sip_ha1")
    op.drop_column("trunks", "auth_secret_enc")
