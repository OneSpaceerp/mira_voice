"""The views Asterisk reads (migrations 0002, 0003): right rows, right options, nothing more."""

import subprocess
import sys
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import ProgrammingError

HA1 = "a" * 32


def run(engine: sa.Engine, sql: str, **params: object) -> list[sa.Row[object]]:
    with engine.begin() as conn:
        result = conn.execute(sa.text(sql), params)
        return list(result) if result.returns_rows else []


def add_extension(
    engine: sa.Engine,
    tenant: uuid.UUID,
    number: str,
    user: uuid.UUID | None = None,
    enabled: bool = True,
) -> str:
    username = f"x{uuid.uuid4().hex[:6]}-{number}"
    run(
        engine,
        "INSERT INTO extensions (tenant_id, number, user_id, display_name, sip_username, sip_ha1, sip_realm, webrtc, enabled) "
        "VALUES (:t, :n, :u, :d, :s, :h, 'mira', true, :e)",
        t=tenant,
        n=number,
        u=user,
        d=f'Desk "{number}"',
        s=username,
        h=HA1,
        e=enabled,
    )
    return username


def endpoints(engine: sa.Engine) -> dict[str, sa.Row[object]]:
    return {r.id: r for r in run(engine, "SELECT * FROM asterisk.ps_endpoints")}


def test_extension_appears_with_the_options_asterisk_needs(sync_engine, make_tenant) -> None:
    t = make_tenant()
    sip = add_extension(sync_engine, t, "1001")
    ep = endpoints(sync_engine)[sip]
    assert ep.aors == sip and ep.auth == sip
    assert ep.context == "t_" + t.hex  # one dialplan context per tenant
    assert ep.tenantid == str(t)
    assert ep.transport == "transport-kamailio"
    assert (ep.direct_media, ep.rewrite_contact, ep.media_address) == ("no", "no", "127.0.0.1")
    assert ep.callerid == '"Desk 1001" <1001>'  # quotes from the name cannot break the header
    aor = run(sync_engine, "SELECT * FROM asterisk.ps_aors WHERE id = :i", i=sip)[0]
    assert (aor.max_contacts, aor.support_path, aor.contact) == ("1", "yes", None)
    auth = run(sync_engine, "SELECT * FROM asterisk.ps_auths WHERE id = :i", i=sip)[0]
    assert (auth.auth_type, auth.username, auth.realm) == ("digest", sip, "mira")
    assert auth.password_digest == "MD5:" + HA1


def test_disabled_suspended_or_inactive_disappear(sync_engine, make_tenant, make_user) -> None:
    active, suspended = make_tenant("active"), make_tenant("gone", status="suspended")
    agent_off = make_user("off@example.com", "agent", active, active=False)
    keep = add_extension(sync_engine, active, "1001")
    disabled = add_extension(sync_engine, active, "1002", enabled=False)
    user_off = add_extension(sync_engine, active, "1003", user=agent_off)
    tenant_off = add_extension(sync_engine, suspended, "1001")
    ids = set(endpoints(sync_engine))
    assert keep in ids
    assert not ids & {disabled, user_off, tenant_off}
    for view in ("ps_aors", "ps_auths"):
        rows = {r.id for r in run(sync_engine, f"SELECT id FROM asterisk.{view}")}  # noqa: S608
        assert keep in rows and not rows & {disabled, user_off, tenant_off}


def test_trunks_are_not_in_the_views(sync_engine, make_tenant) -> None:
    # Since migration 0003 trunks live in the generated pjsip_mira.conf (they need identify,
    # outbound auth and registration objects the views cannot express).
    t = make_tenant()
    run(
        sync_engine,
        "INSERT INTO trunks (tenant_id, name, kind, host, port, transport, max_channels, enabled) "
        "VALUES (:t, 'WE', 'sip_ip_auth', 'sip.example.net', 5061, 'tls', 30, true)",
        t=t,
    )
    assert not [r for r in endpoints(sync_engine) if str(r).startswith("trunk_")]
    assert not run(sync_engine, "SELECT id FROM asterisk.ps_aors WHERE id LIKE 'trunk_%'")


def test_endpoints_have_no_mailboxes(sync_engine, make_tenant) -> None:
    add_extension(sync_engine, make_tenant(), "1001")
    rows = run(sync_engine, "SELECT mailboxes FROM asterisk.ps_endpoints")
    assert rows and all(r.mailboxes is None for r in rows)


def test_asterisk_role_reads_views_only(database_url, sync_engine, make_tenant) -> None:
    import os

    sip = add_extension(sync_engine, make_tenant(), "1001")
    code = subprocess.run(  # same command core-migrate runs
        [sys.executable, "-m", "mira_core.cli", "ensure-db-roles"], capture_output=True, text=True
    )
    assert code.returncode == 0, code.stderr
    url = sa.make_url(database_url.replace("postgresql://", "postgresql+psycopg://", 1)).set(
        username="asterisk", password=os.environ["ASTERISK_DB_PASSWORD"]
    )
    ro = sa.create_engine(url)
    try:
        with ro.connect() as conn:
            # unqualified, like Asterisk's realtime queries (search_path = asterisk)
            assert sip in {r.id for r in conn.execute(sa.text("SELECT id FROM ps_endpoints"))}
        for forbidden in ("SELECT * FROM public.users", "SELECT * FROM public.extensions"):
            with ro.connect() as conn, pytest.raises(ProgrammingError, match="permission denied"):
                conn.execute(sa.text(forbidden))
        # computed views are not writable anyway; still, the role must hold no write privilege
        with sync_engine.connect() as conn:
            for view in ("ps_endpoints", "ps_aors", "ps_auths"):
                for priv in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                    granted = conn.execute(
                        sa.text("SELECT has_table_privilege('asterisk', :v, :p)"),
                        {"v": f"asterisk.{view}", "p": priv},
                    ).scalar_one()
                    assert granted is False, f"asterisk may {priv} {view}"
    finally:
        ro.dispose()
