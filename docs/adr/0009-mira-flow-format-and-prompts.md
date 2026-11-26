# 0009: Mira Flow v1 — the flow format, versioning and the prompt library

- Status: accepted (stage 1 of task 1.4; the engine and the builder follow)
- Date: 2026-11-26
- Task: 1.4 (BUILD_GUIDE)

## Context
Task 1.4 asks for a visual IVR builder (Mira Flow) and an engine that runs flows on live calls. The study's node list:
- menu, play, collect digits
- time and holiday conditions
- language choice (Arabic, English, French)
- queue, voicemail, transfer
- HTTP request (data dip), set variable, branch

Flows are built by tenant admins, and the HTTP node reaches into customer systems (ERPNext). So a flow must not be able to carry code, must not leak data across tenants, and a mistake must be undoable. Prompts must exist in three languages, and Asterisk ships no Arabic sounds.

The 0.4 data model had a placeholder `ivr_flows` table with one row per (name, version) and no stable identity, so an inbound route could not point at "the published version of flow X".

## Decision

### 1. JSON format `mira-flow/1` (`core/src/mira_core/flows/schema.py`)
- A flow is a graph: `{"schema": "mira-flow/1", "start": "<node>", "nodes": {"<id>": {...}}}`.
- Nodes are a tagged union on `type`, validated by Pydantic (discriminated union, `extra="forbid"`). The types:

| Type | What it does |
| --- | --- |
| `play` | Play a prompt |
| `menu` | One key: options, retries, an invalid-key prompt and fallbacks |
| `collect` | Digits into a variable: min/max, terminator, timeout |
| `time` | Weekly ranges and holidays, in the tenant's timezone or one given |
| `language` | Prompts from here on play in ar, en or fr |
| `set` / `branch` | Set a variable / test one: eq, ne, gt, lt, contains, empty, not_empty |
| `http` | Data dip: GET/POST with template headers and body, ≤ 5 s, JSON paths into variables |
| `transfer` | Ring a tenant number, through its own dialplan and outbound routes |
| `queue` | Put the caller in a queue (task 1.5) |
| `voicemail` | Record a message for an extension's mailbox |
| `hangup` | End the call |

- Up to 200 nodes per flow. `label`, `x` and `y` are for the builder only.
- **No code anywhere.** Text that reaches a caller or a web service is a template with `{{variable}}` placeholders only. Anything else in braces is rejected (no Jinja, no expressions).
- In the data dip, the URL's scheme and host are fixed: no variable, no credentials in the URL. Placeholders may appear in the path and query only. The engine (stage 2) also checks the resolved address at call time against blocked ranges.
- Built-in variables: `caller_number`, `called_number`, `language`, `call_id`. A flow cannot overwrite them.
- Keys collected by a `collect` node are kept in the call's memory only; they are never written to `call_events` (ADR 0008).

### 2. Checks, in two levels (`flows/validate.py`)
- **Structure:** links point to existing nodes, no node loops to itself, every variable used is set somewhere, nodes unreachable from the start are warnings.
- **References**, required to publish:
  - prompts exist in the tenant and have at least one recording
  - voicemail mailboxes are the tenant's extensions
  - queues exist in the tenant
  - timezones are valid
- A draft must be valid node by node to be saved. Wiring problems are reported but do not block saving work in progress. Publishing needs zero errors.

### 3. Versioning
- `ivr_flows` holds the stable identity: name, description, the editable `draft`, and `published_version`.
- `ivr_flow_versions` holds immutable published snapshots, stored normalised: exactly what the engine will run.
- Publish adds version N+1. Rollback points `published_version` at an older version, after checking it again (a prompt may have been deleted since). "Edit" copies a version back into the draft.
- Migration 0005 reshapes the never-used placeholder table. It stops if the table holds any rows, so nothing can be lost.

### 4. Prompt library (`prompts`, `prompt_audio`, `prompts.py`)
- A prompt has up to one recording per language (ar, en, fr), uploaded as the raw body of `PUT /prompts/{id}/audio/{lang}`.
- Uploads must be PCM 16-bit mono at 8 or 16 kHz, at most 5 minutes and 12 MB: what Asterisk plays without transcoding. They are re-written as a clean WAV (metadata chunks dropped) and hashed.
- Files live in the `prompts` volume at `<tenant>/<lang>/<prompt>.wav` (`.wav16` for 16 kHz), 0640 with group `mira-config`. Asterisk mounts the volume read-only as `sounds/mira`. The engine plays the exact file, `sound:mira/<tenant>/<lang>/<prompt>`, choosing the language from the recordings that exist. Asterisk 22 only searches `<lang>/<path>` and the bare path, not the older `<dir>/<lang>/<file>` layout: tested on 22.12, playback failed.
- A prompt used by a flow's published version cannot be deleted.
- System default Arabic prompts do not exist yet. Tenants upload their own, and who records the defaults (voice talent, or TTS in v1) is an open product question.

### 5. API
- `/api/v1/flows`: list, create, get, update, publish, versions, rollback, edit-from-version, delete, and `/flows/schema` (JSON Schema for the builder).
- `/api/v1/prompts`: CRUD plus audio upload, download and delete.
- Tenant admins (and platform admins naming the tenant) only. Other tenants' flows and prompts are "not found".

## Consequences
- The format is the contract between the builder, the engine and any future tools. Changes are new schema ids (`mira-flow/2`), never silent edits.
- Prompt files are on the Server's disk. Mira Cloud with several Asterisk nodes will move them to MinIO with a local cache (task 2.x).
- The queue node can be saved and published only once queues exist (task 1.5 adds their API). Voicemail storage and the engine come in stage 2.
