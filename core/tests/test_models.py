"""The database itself enforces the rules, so a bug in the API cannot store bad data."""

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

HA1 = "0" * 32


def run(engine: sa.Engine, sql: str, **params: object) -> None:
    with engine.begin() as conn:
        conn.execute(sa.text(sql), params)


def test_platform_admin_must_not_have_tenant(sync_engine, make_tenant, make_user) -> None:
    with pytest.raises(IntegrityError, match="ck_users_platform_admin_has_no_tenant"):
        make_user("p@example.com", "platform_admin", make_tenant())


def test_tenant_roles_need_a_tenant(sync_engine, make_user) -> None:
    with pytest.raises(IntegrityError, match="ck_users_platform_admin_has_no_tenant"):
        make_user("a@example.com", "agent", None)


def test_email_stored_lowercase_only(sync_engine, make_tenant, make_user) -> None:
    with pytest.raises(IntegrityError, match="ck_users_email_lowercase"):
        make_user("Agent@Example.com", "agent", make_tenant())


def test_unknown_role_rejected(sync_engine, make_tenant, make_user) -> None:
    with pytest.raises(IntegrityError, match="ck_users_user_role"):
        make_user("a@example.com", "superuser", make_tenant())


def test_tenant_with_users_cannot_be_deleted(sync_engine, make_tenant, make_user) -> None:
    t = make_tenant()
    make_user("a@example.com", "agent", t)
    with pytest.raises(IntegrityError, match="fk_users_tenant_id_tenants"):
        run(sync_engine, "DELETE FROM tenants WHERE id = :id", id=t)


def _extension(engine: sa.Engine, tenant: object, number: str, sip_user: str) -> None:
    run(
        engine,
        "INSERT INTO extensions (tenant_id, number, display_name, sip_username, sip_ha1, sip_realm, webrtc, enabled) "
        "VALUES (:t, :n, 'Ext', :u, :h, 'mira', true, true)",
        t=tenant,
        n=number,
        u=sip_user,
        h=HA1,
    )


def test_extension_numbers_unique_per_tenant_only(sync_engine, make_tenant) -> None:
    a, b = make_tenant("a"), make_tenant("b")
    _extension(sync_engine, a, "1001", "a-1001")
    _extension(sync_engine, b, "1001", "b-1001")  # same number in another tenant is fine
    with pytest.raises(IntegrityError, match="uq_extensions_tenant_id_number"):
        _extension(sync_engine, a, "1001", "a-1001-dup")


def test_sip_usernames_unique_across_tenants(sync_engine, make_tenant) -> None:
    _extension(sync_engine, make_tenant("a"), "1001", "shared")
    with pytest.raises(IntegrityError, match="uq_extensions_sip_username"):
        _extension(sync_engine, make_tenant("b"), "1002", "shared")


def test_extension_number_digits_only(sync_engine, make_tenant) -> None:
    with pytest.raises(IntegrityError, match="ck_extensions_number_digits"):
        _extension(sync_engine, make_tenant(), "10a1", "x")


def test_call_times_must_be_ordered(sync_engine, make_tenant) -> None:
    with pytest.raises(IntegrityError, match="ck_calls_end_after_start"):
        run(
            sync_engine,
            "INSERT INTO calls (tenant_id, asterisk_linkedid, direction, caller_number, called_number, started_at, ended_at) "
            "VALUES (:t, 'L1', 'inbound', '0100', '1001', now(), now() - interval '1 minute')",
            t=make_tenant(),
        )
