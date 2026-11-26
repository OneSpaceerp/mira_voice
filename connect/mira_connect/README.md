# connect/mira_connect/ — Mira Connect

Frappe app for **ERPNext v16+ and Frappe CRM v16+**: settings, agent mapping, Call Log custom fields, screen pop, click-to-call, recordings, dispositions, dialer campaigns, signed webhooks (HMAC-SHA256).

Runs inside a Frappe bench, not in Mira's Docker stack. Frappe v16 needs **Python 3.14, Node 24, MariaDB 11.8** (see docs/stack-versions.md). Follows Frappe style (tabs) with its own `pyproject.toml`; `bench run-tests --app mira_connect` must pass.

Scaffolded with `bench new-app mira_connect` in BUILD_GUIDE task **2.2**, following the `erpnext-app-builder` skill.
