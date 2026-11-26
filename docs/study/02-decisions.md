# Mira Voice — decisions and open questions (25 Nov 2026)

Live versions: study https://claude.ai/artifact/ADy8EZmt6NXEa9LkcB8k7X · design system https://claude.ai/artifact/Mrn7jCxV4QWHZWxXe6AqE3

## Business answers
- Product sold to many companies (SaaS + licence), NSD brand only (no white-label for now).
- Pilot: 40 agents, on-premise (Server edition), WE SIP trunks. Year-1 ambition 50 customers of 10–300 agents; realistic gate: 10 paying customers by month 16.
- Markets: Egypt, KSA, UAE. No licences yet; legal step is Phase 0 but skipped while testing on-prem.
- Connectivity: GSM gateways and SIP trunks (WE for now); peak calls decided per client.
- Pricing: tiers like Ziwo — Phone System / Contact Center / Enterprise (incl. on-prem) / add-ons.

## Scope answers
- Inbound + outbound: preview/progressive dialer in MVP, predictive in v1.
- WhatsApp, SMS, web chat in v1; email in v2.
- Any SIP IP phone + softphones. Desktop = installable Mira Desk PWA (ADR 0002); mobile = Flutter.
- ERPNext v16+ and Frappe CRM v16+ only.
- AI through APIs (no GPU server) for now.
- UI and IVR in Arabic, English and French.

## Technical answers
- Target OS: Ubuntu Server 24.04 LTS; one-command installer.
- Hosting: VM on the laptop for development, then Contabo (no Middle East region: EU for Egypt tests; not for KSA data or UAE cloud).
- Team: Khaled + Claude Code; open-source SDKs only (no Siprix).
- Apple and Google store accounts: still to create.

## Brand answers
- Designer supplies the vector logo set and the Arabic lock-up; Arabic name ميرا ڤويس; domain: a subdomain of nsd-eg.com (suggested voice.nsd-eg.com).

## Architecture
Asterisk 22 LTS (PJSIP) behind Kamailio + RTPengine + coturn; Mira Core (Python/FastAPI, PostgreSQL, Redis→NATS, ClickHouse, MinIO recordings); Mira Desk (Vue 3 PWA); Mira Phone (Flutter, dart-sip-ua, self-built push); Mira Connect (Frappe app `mira_connect`).

## Roadmap
MVP month 6 (pilot live 30 days) · v1.0 month 16 (cloud on Contabo EU, mobile apps, predictive dialer + QA, WhatsApp/SMS/web chat, Arabic AI + voice bot, Odoo and CRM connectors) · v2 after (agent assist, email, ISO 27001, WFM, in-country cloud KSA/UAE).

## Competitor
Ziwo: cloud-only, 1,000+ businesses in 10 countries incl. Egypt, USD 40 / 109 per user, 20+ connectors incl. Odoo, not ERPNext. Mira wins on on-prem, ERPNext/Odoo depth and local-currency price; must close WhatsApp, voice agent, numbers, connectors and ISO 27001 gaps.

## Open questions
- [ ] WE: can its SIP trunk register from a server outside Egypt?
- [ ] Pilot: which ERPNext / Frappe CRM site, simultaneous calls, dialer use (sales or collections)?
- [ ] Which speech-to-text and LLM APIs are acceptable to the pilot for call audio?
- [ ] Legal opinion (NTRA) before carrying paying customers' calls on an NSD-hosted cloud.
