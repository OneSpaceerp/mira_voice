"""Asterisk realtime: read-only views over Mira tables (schema "asterisk")

Asterisk reads PJSIP endpoints, AORs and auths from these views through ODBC
(telephony/asterisk/config/sorcery.conf + extconfig.conf). Mira's own tables stay the only
source of truth: nothing is copied, nothing can drift. A view row exists only for an enabled
extension of an active tenant whose user (if any) is active — disabling a user, an extension
or a tenant takes the phone off the system on its next request.

The role "asterisk" (password set by `mira-core ensure-db-roles`) may read these views and
nothing else.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Dialplan context of a tenant: also used by Mira Core's dialplan generator (asterisk_config.py).
TENANT_CONTEXT = "'t_' || replace(t.id::text, '-', '')"
TRUNK_ID = "'trunk_' || replace(k.id::text, '-', '')"

ACTIVE_EXTENSIONS = """
    FROM public.extensions e
    JOIN public.tenants t ON t.id = e.tenant_id
    LEFT JOIN public.users u ON u.id = e.user_id
    WHERE e.enabled AND t.status = 'active' AND (u.id IS NULL OR u.is_active)
"""

ACTIVE_TRUNKS = """
    FROM public.trunks k
    JOIN public.tenants t ON t.id = k.tenant_id
    WHERE k.enabled AND t.status = 'active'
"""

# Same media / NAT settings as the mira-endpoint template in pjsip.conf: Kamailio and RTPengine
# sit in front, Asterisk only talks to 127.0.0.1.
COMMON_ENDPOINT = """
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
        -- Asterisk prompts: English and French are installed; Arabic prompts come with the
        -- IVR prompt sets, until then Arabic tenants hear English.
        CASE t.default_locale WHEN 'fr' THEN 'fr' ELSE 'en' END::text AS language,
        t.id::text AS tenantid
"""

# SQL assembled from the constants above only (no input).  ruff: S608 is ignored for migrations.
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
        {COMMON_ENDPOINT}
    {ACTIVE_EXTENSIONS}
    UNION ALL
    SELECT
        {TRUNK_ID}::text AS id,
        {TRUNK_ID}::text AS aors,
        NULL::text AS auth,
        ({TENANT_CONTEXT} || '_in')::text AS context,
        NULL::text AS callerid,
        'yes'::text AS send_pai,
        'yes'::text AS trust_id_inbound,
        -- out through the SIP edge, never straight from Asterisk
        'sip:127.0.0.1:5060;lr'::text AS outbound_proxy,
        k.from_domain::text AS from_domain,
        {COMMON_ENDPOINT}
    {ACTIVE_TRUNKS}
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
    UNION ALL
    SELECT
        {TRUNK_ID}::text AS id,
        ('sip:' || k.host || ':' || k.port::text
            || CASE k.transport WHEN 'udp' THEN '' ELSE ';transport=' || k.transport END)::text AS contact,
        '0'::text AS max_contacts,
        'no'::text AS remove_existing,
        'no'::text AS remove_unavailable,
        '60'::text AS qualify_frequency,
        'no'::text AS support_path
    {ACTIVE_TRUNKS}
"""

# Only the digest hash is stored (Asterisk 22: auth_type=digest + password_digest; md5_cred is
# deprecated). Trunk credentials (outbound auth) come encrypted in task 1.2.
PS_AUTHS = f"""
CREATE VIEW asterisk.ps_auths AS
    SELECT
        e.sip_username::text AS id,
        'digest'::text AS auth_type,
        e.sip_username::text AS username,
        e.sip_realm::text AS realm,
        ('MD5:' || e.sip_ha1)::text AS password_digest
    {ACTIVE_EXTENSIONS}
"""


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS asterisk")
    op.execute(PS_ENDPOINTS)
    op.execute(PS_AORS)
    op.execute(PS_AUTHS)
    # Role without password and without login until ensure-db-roles sets them.
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'asterisk') THEN "
        "CREATE ROLE asterisk NOLOGIN; END IF; END $$"
    )
    op.execute("ALTER ROLE asterisk SET search_path = asterisk")
    op.execute("REVOKE ALL ON SCHEMA public FROM asterisk")
    op.execute("GRANT USAGE ON SCHEMA asterisk TO asterisk")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA asterisk TO asterisk")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS asterisk CASCADE")
    # The role may own nothing now; keep it if other objects reference it.
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'asterisk') THEN "
        "REVOKE ALL ON SCHEMA public FROM asterisk; DROP ROLE asterisk; END IF; END $$"
    )
