"""Command-line tasks for operators.

    mira-core bootstrap --email it@example.com --company "Example Co"   # first install only
    mira-core create-admin --email it@example.com --name "IT Admin"
    mira-core ensure-db-roles     # login + password of the read-only "asterisk" role (core-migrate)
    mira-core render-config       # regenerate the Asterisk dialplan and reload it

bootstrap and create-admin print the generated password once.
"""

import argparse
import asyncio
import secrets
import sys

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select, text

from mira_core.asterisk_config import apply_config
from mira_core.config import get_settings
from mira_core.db import get_engine, get_sessionmaker
from mira_core.models import Locale, Role, Tenant, User
from mira_core.schemas import Email
from mira_core.security import hash_password


async def _create_admin(email: str, name: str) -> int:
    email = email.strip().lower()
    async with get_sessionmaker()() as session:
        if await session.scalar(select(User).where(User.email == email)) is not None:
            print(f"A user with e-mail {email} already exists.", file=sys.stderr)
            return 1
        password = secrets.token_urlsafe(18)
        session.add(
            User(
                tenant_id=None,
                email=email,
                full_name=name,
                password_hash=hash_password(password),
                role=Role.PLATFORM_ADMIN,
            )
        )
        await session.commit()
    await get_engine().dispose()
    print(f"Platform admin created: {email}")
    print(f"Password (shown once, store it in your password manager): {password}")
    return 0


async def _bootstrap(email: str, company: str, language: str) -> int:
    """First install (deploy/install.sh): the first tenant and a platform admin who can sign in
    to Mira Desk straight away. Does nothing once a platform admin exists, so re-running the
    installer never creates a second admin or prints a new password."""
    try:
        email = TypeAdapter(Email).validate_python(email)
    except ValidationError:
        print(f"Not a valid e-mail address: {email}", file=sys.stderr)
        return 2
    company = company.strip()
    if not 1 <= len(company) <= 200:
        print("The company name must be 1 to 200 characters.", file=sys.stderr)
        return 2
    locale = Locale(language)
    async with get_sessionmaker()() as session:
        admins = await session.scalar(
            select(func.count()).select_from(User).where(User.role == Role.PLATFORM_ADMIN)
        )
        if admins:
            print("Already set up (a platform admin exists): nothing changed.")
            await get_engine().dispose()
            return 0
        if await session.scalar(select(User).where(User.email == email)) is not None:
            print(f"A user with e-mail {email} already exists.", file=sys.stderr)
            await get_engine().dispose()
            return 1
        if not await session.scalar(select(func.count()).select_from(Tenant)):
            session.add(Tenant(name=company, slug="main", default_locale=locale))
            print(f"Tenant created: {company} (slug main)")
        password = secrets.token_urlsafe(18)
        session.add(
            User(
                tenant_id=None,
                email=email,
                full_name="Administrator",
                password_hash=hash_password(password),
                role=Role.PLATFORM_ADMIN,
                locale=locale,
            )
        )
        await session.commit()
    await get_engine().dispose()
    print(f"Platform admin created: {email}")
    print(f"Password (shown once, store it in your password manager): {password}")
    return 0


async def _ensure_db_roles() -> int:
    """Give the read-only role "asterisk" (created by migration 0002) login and its password from
    ASTERISK_DB_PASSWORD. Idempotent; runs in core-migrate after `alembic upgrade head`."""
    password = get_settings().asterisk_db_password.get_secret_value()
    if len(password) < 24:
        print(
            "ASTERISK_DB_PASSWORD is missing or too short (install.sh generates it).",
            file=sys.stderr,
        )
        return 1
    async with get_sessionmaker()() as session:
        exists = await session.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = 'asterisk'"))
        if not exists:
            print(
                "Role 'asterisk' does not exist: run `alembic upgrade head` first.", file=sys.stderr
            )
            return 1
        # ALTER ROLE does not take bind parameters; quote_literal makes the value safe.
        quoted = await session.scalar(text("SELECT quote_literal(:p)"), {"p": password})
        await session.execute(text(f"ALTER ROLE asterisk LOGIN PASSWORD {quoted}"))  # noqa: S608
        await session.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA asterisk TO asterisk"))
        await session.commit()
    await get_engine().dispose()
    print("Role 'asterisk' can log in (read-only realtime views).")
    return 0


async def _render_config() -> int:
    async with get_sessionmaker()() as session:
        result = await apply_config(session, get_settings())
    await get_engine().dispose()
    print(f"Changed: {result.changed or 'nothing'}; reloaded: {result.reloaded or 'nothing'}")
    for error in result.errors:
        # Not fatal: the files are right; Asterisk/Kamailio read them when they (re)start.
        print(f"  reload not done: {error}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mira-core", description="Mira Core operator commands")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser(
        "bootstrap", help="first install: the first tenant and a platform admin (once only)"
    )
    b.add_argument("--email", required=True)
    b.add_argument("--company", default="Mira")
    b.add_argument("--language", choices=[x.value for x in Locale], default=Locale.AR.value)
    p = sub.add_parser("create-admin", help="create a platform admin with a generated password")
    p.add_argument("--email", required=True)
    p.add_argument("--name", default="Platform admin")
    sub.add_parser("ensure-db-roles", help="set up the read-only database role used by Asterisk")
    sub.add_parser("render-config", help="regenerate the Asterisk dialplan and reload it")
    sub.add_parser(
        "call-events", help="run the ARI event worker: call records, call events, live state"
    )
    sub.add_parser("ivr", help="run the Mira Flow engine (IVR) for calls Asterisk sends to it")
    args = parser.parse_args(argv)
    if args.command == "ivr":
        from mira_core.flows import worker

        return worker.main(get_settings())
    if args.command == "call-events":
        from mira_core import ari_events  # imports websockets/redis only for this command

        return ari_events.main(get_settings())
    if args.command == "bootstrap":
        return asyncio.run(_bootstrap(args.email, args.company, args.language))
    if args.command == "create-admin":
        return asyncio.run(_create_admin(args.email, args.name))
    if args.command == "ensure-db-roles":
        return asyncio.run(_ensure_db_roles())
    if args.command == "render-config":
        return asyncio.run(_render_config())
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
