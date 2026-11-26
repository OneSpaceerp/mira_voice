# 0004 — Mira Core foundations: async SQLAlchemy on psycopg 3, JWT + Argon2, tenant rules in the database

- Status: accepted
- Date: 2026-11-25

## Context
Task 0.4 starts Mira Core (FastAPI, PostgreSQL 16). Several choices the study left open shape every later task: the PostgreSQL driver, how auth works, how tenants are isolated, how the schema evolves, and how Core runs on the server.

## Decision
1. **Async FastAPI + SQLAlchemy 2.1 asyncio on psycopg 3** (not asyncpg): one driver serves the async app and the synchronous Alembic runs and tests (`postgresql+psycopg://`). ARI and WebSockets in Phase 1 need async anyway.
2. **Auth:** OAuth2 password flow → short-lived **HS256 JWT** (30 min, `MIRA_JWT_SECRET` from install.sh, minimum key length enforced) carrying user, tenant and role; **Argon2id** password hashes (pwdlib). Every request re-reads the user and tenant, so disabling a user, changing a role or suspending a tenant applies immediately. Refresh tokens / SSO come with Mira Desk (task 2.1).
3. **Roles:** `platform_admin` (installation-wide, no tenant), `tenant_admin`, `supervisor`, `agent`.
4. **Tenant isolation in two layers:** every tenant-owned table has `tenant_id` (FK RESTRICT — tenants are suspended, never cascade-deleted, because call records and recordings fall under retention rules); the API scopes every query to the caller's tenant and answers 404 for other tenants' objects. PostgreSQL row-level security is reconsidered for Mira Cloud.
5. **Rules the data must obey live in the database** as named CHECK / UNIQUE constraints (platform admin ⇔ no tenant, lowercase e-mail, digit-only extension numbers, unique SIP usernames across tenants, ordered call timestamps), so an API bug cannot store bad data. Enums are VARCHAR + CHECK, not PostgreSQL ENUM types, to keep migrations simple.
6. **Schema changes only through Alembic** (one migration per change); tests apply the real migrations to a throwaway PostgreSQL 16 and run `alembic check`.
7. **No clear secrets at rest:** SIP passwords are stored only as digest HA1 (Asterisk `auth_type=md5`); trunk credentials will be added encrypted (task 1.2).
8. **Runtime:** PostgreSQL and Core run in the same compose stack with host networking on 127.0.0.1 (5432, 8000); a one-shot `core-migrate` service runs `alembic upgrade head` before Core starts. The public HTTPS entry point (443) is a reverse proxy added with Mira Desk.

## Consequences
- Tests need Docker (testcontainers); the dev machine and CI must provide it.
- Each API request costs two primary-key lookups (user, tenant) for the immediate-revocation guarantee — negligible at pilot scale.
- A server that already runs something on 127.0.0.1:5432 or :8000 conflicts with Mira; the installer should check this (task 2.6).
- Mira Core is the only writer of telephony config: Asterisk endpoints and dialplan will be generated from these tables (task 1.1).
