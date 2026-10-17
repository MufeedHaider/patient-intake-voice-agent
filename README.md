# Voice AI Patient Registration Agent

Call a real U.S. phone number, talk naturally to **Riley**, an AI intake coordinator, and get registered as a new patient. Riley collects the standard U.S. demographic fields, reads everything back for confirmation, saves the record to PostgreSQL through the same service layer as the REST API, and recognizes you by phone number when you call back.

## Live demo

|What|Where|
|-|-|
|Phone number|`+1 (732) 813-8152`|
|API base URL|`https://patient-intake-api-7v87.onrender.com`|
|Interactive API docs|`https://patient-intake-api-7v87.onrender.com/docs`|
|Dashboard|`https://patient-intake-api-7v87.onrender.com/dashboard`|

No credentials are needed to call the number or use the API. Two demo patients are seeded (Jane Doe, 212-555-0147, and Carlos Rivera, 732-555-0123). Call and give **212-555-0147** as your phone number to try the returning-caller flow.

> The API runs on Render's free tier. If it has been idle, the first request can take up to a minute while it wakes up; an uptime pinger keeps it warm during the review window.

## Architecture

```
 Caller ──phone──▶ Vapi (telephony + speech-to-text + LLM + text-to-speech)
                        │  tool calls: find\_patient\_by\_phone / register\_patient / update\_patient
                        │  end-of-call report: transcript + summary
                        ▼
                 FastAPI app  ── POST /vapi/webhook ──┐
                 │                                    ▼
                 ├── REST API  /patients ──▶  Service layer (validation + persistence)
                 └── Dashboard /dashboard ─┘          │
                                                      ▼
                                              PostgreSQL (patients, call\_logs)
```

Separation of concerns:

|Layer|Code|Responsibility|
|-|-|-|
|Telephony, STT, TTS, LLM|Vapi (configured by `scripts/setup\_vapi.py`)|The phone call and the conversation|
|Agent behaviour|`prompts/system\_prompt.md`, `vapi/tools.json`|What Riley says, when tools are called|
|Webhook adapter|`app/api/vapi.py`|Translates Vapi tool calls into service calls; always answers, never silent|
|REST API|`app/api/patients.py`|HTTP endpoints, status codes, `{data, error}` envelope|
|Service layer|`app/services/patients.py`|The only code that reads or writes records|
|Validation|`app/validation.py`, `app/schemas.py`|One set of rules for both the API and the voice agent|
|Data|`app/models.py`|Schema, types and constraints|

The voice agent never talks to the database directly: it goes through the same service layer and validation as `POST /patients`, so a record created by phone and one created through the API follow identical rules.

## Tech stack and why

|Choice|Why|
|-|-|
|**Vapi**|Handles phone numbers, speech-to-text, text-to-speech, barge-in and turn-taking, so the 3 hours go into prompt design, tools and the backend. It also offers a free U.S. number.|
|**OpenAI GPT-4o via Vapi**|Reliable tool calling and good at handling corrections and out-of-order answers. Configurable with `VAPI\_MODEL`.|
|**FastAPI + Pydantic**|Fast to build, automatic OpenAPI docs at `/docs`, strong request validation.|
|**SQLAlchemy 2 + PostgreSQL**|A real relational schema with types and constraints; data survives restarts. SQLite is used for local runs and tests.|
|**Render (free web service + free PostgreSQL)**|One `render.yaml` blueprint deploys both, with no credit card.|

## Data model

`patients` stores every field from the brief with proper types (`UUID` primary key, `DATE` date of birth, `TIMESTAMPTZ` timestamps), `NOT NULL` on required fields, length limits, and `CHECK` constraints (sex values, phone length, state length, name and city lengths). Indexes cover the three search filters. `deleted\_at` supports soft delete.

`call\_logs` stores one row per call: Vapi call ID, linked `patient\_id`, caller number, end reason, summary and full transcript.

Validation rules (shared by API and agent, in `app/validation.py`):

|Field|Rule|
|-|-|
|first\_name, last\_name|1–50 characters; letters, hyphens, apostrophes (single spaces allowed for names like "Mary Ann")|
|date\_of\_birth|Real date, not in the future, after 1900. Accepts MM/DD/YYYY (returned in this format) or YYYY-MM-DD|
|sex|Male, Female, Other, Decline to Answer (common phrasings like "prefer not to say" are mapped)|
|phone\_number, emergency\_contact\_phone|10-digit U.S. number; punctuation and a leading +1 are stripped; area code cannot start with 0 or 1|
|email|Valid format; spoken "at" and "dot" are converted|
|state|Valid 2-letter code; full names such as "New Jersey" are converted to NJ|
|zip\_code|5 digits or ZIP+4|
|insurance\_member\_id|Letters, digits and hyphens|
|preferred\_language|Defaults to English|

## REST API

All responses use the envelope `{"data": ..., "error": null}` or `{"data": null, "error": {"code", "message", "details"}}`.

|Method|Endpoint|Notes|Status codes|
|-|-|-|-|
|GET|`/patients`|Filters: `?last\_name=` (case-insensitive), `?date\_of\_birth=`, `?phone\_number=` (any format)|200, 400|
|GET|`/patients/{id}`||200, 400 (bad UUID), 404|
|POST|`/patients`|Returns the created record with `patient\_id`|201, 422|
|PUT|`/patients/{id}`|Partial update: only fields sent are changed|200, 400, 404, 422|
|DELETE|`/patients/{id}`|Soft delete: sets `deleted\_at`; the row stays in the database|200, 400, 404|
|GET|`/health`|Liveness check|200|
|GET|`/dashboard`|Web UI of registered patients and call transcripts|200|
|POST|`/vapi/webhook`|Vapi tool calls and end-of-call reports|200|

Examples:

```bash
curl https://patient-intake-api-7v87.onrender.com/patients?last\_name=doe
curl -X POST https://patient-intake-api-7v87.onrender.com/patients -H "Content-Type: application/json" -d '{
  "first\_name":"Ann","last\_name":"Lee","date\_of\_birth":"02/14/1992","sex":"Female",
  "phone\_number":"646-555-0188","address\_line\_1":"10 Main St","city":"Boston","state":"MA","zip\_code":"02108"}'
curl -X PUT https://patient-intake-api-7v87.onrender.com/patients/<id> -H "Content-Type: application/json" -d '{"city":"Cambridge"}'
curl -X DELETE https://patient-intake-api-7v87.onrender.com/patients/<id>
```

Unknown fields are rejected, invalid values return 422 with one entry per bad field, and unexpected errors return 500 with the same envelope (details are logged, not returned).

## Voice agent design

The full prompt is in [`prompts/system\_prompt.md`](prompts/system_prompt.md), with `## NOTE:` comments explaining each section (they are stripped before the prompt is sent to the model). Key decisions:

* **Sounds human, not like an IVR.** Short spoken sentences, one question at a time, no lists or markdown, digits read in groups, and the caller can answer in any order or give several fields at once.
* **Required first, optional by invitation.** After the required fields, Riley offers insurance, emergency contact and preferred language once, exactly as the brief suggests.
* **Read-back before any write.** Riley reads all fields back in two or three short turns and only calls `register\_patient` after a clear yes. Corrections change only the corrected field.
* **The server is the final judge.** The agent validates conversationally, but `register\_patient` re-validates everything. Invalid fields come back as `NOT\_SAVED: date\_of\_birth: cannot be in the future; ...`, and the prompt tells Riley to re-ask only those fields.
* **Status-word tool results.** Every result starts with `SAVED`, `NOT\_SAVED`, `MATCH\_FOUND`, `NO\_MATCH`, `DUPLICATE\_PHONE`, `UPDATED` or `SYSTEM\_ERROR`, so the model branches reliably.
* **Returning callers.** As soon as a phone number is given, Riley calls `find\_patient\_by\_phone`. On a match she asks, "It looks like we already have a record for Jane Doe. Would you like to update your information instead?" and uses `update\_patient`. A server-side check also stops accidental duplicates unless the caller confirms they are a different person (`force\_new`).
* **Ending.** After `SAVED`, Riley says "You're all set, \[First Name]" and uses Vapi's built-in `endCall` tool.

## Edge cases and resilience

|Situation|What happens|
|-|-|
|Invalid date of birth (future, impossible like 02/30)|Riley re-asks; if it slips through, the server returns `NOT\_SAVED` naming the field and Riley re-asks only that field|
|3-digit or 11-digit phone number|Same: field-specific re-prompt|
|Caller corrects a spelling ("D-A-V-I-S, not D-A-V-I-E-S")|Prompt handles letter-by-letter spelling and updates only that field before read-back|
|Caller wants to start over|Riley says "No problem, let's start fresh" and restarts collection|
|Database write fails|Webhook catches the error, rolls back, logs it and returns `SYSTEM\_ERROR`; Riley apologises and says the information was not saved. Never silence, never a false "you're all set"|
|Unexpected exception in a tool|Same as above (caught, logged, spoken)|
|Call drops mid-conversation|Nothing unconfirmed is saved, by design. Vapi still sends the end-of-call report, so the partial transcript is stored in `call\_logs` for follow-up|
|Server restart|Data is in PostgreSQL, so it survives restarts and redeploys|
|Medical question or emergency|Riley explains she only handles registration; for emergencies she tells the caller to call 911|
|Spanish speaker|Riley switches to Spanish and stores preferred\_language = Spanish (see Known limitations)|

## Observability

Logs go to stdout (visible in the Render dashboard): every tool call and result, the final registration payload, updates, call end reasons and full call transcripts. Transcripts and summaries are also stored in `call\_logs` and shown per patient on the dashboard.

## Security

* No keys in source code: everything comes from environment variables (`.env.example` lists them).
* Server-side validation on every API input; control characters are stripped and whitespace normalised; unknown fields are rejected; SQL goes through SQLAlchemy parameters.
* Optional webhook secret: set `VAPI\_SECRET` on the server, then in Vapi create a Bearer Token credential with header name `X-Vapi-Secret` (Bearer prefix off) and attach it to the tools and the assistant's server URL. Requests without it get 401.
* Soft delete keeps an audit trail.

## Setup

### Run locally

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\\Scripts\\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload      # http://localhost:8000/dashboard and /docs
python -m pytest                   # 27 tests
```

### Deploy

1. Push this repo to GitHub.
2. Render: **New → Blueprint**, select the repo. `render.yaml` creates the free web service and free PostgreSQL database and wires `DATABASE\_URL`.
3. Vapi: copy your private API key, then on your machine run:

```bash
   VAPI\_API\_KEY=... SERVER\_URL=https://patient-intake-api-7v87.onrender.com python scripts/setup\_vapi.py
   ```

   This creates the three tools and the assistant, pointed at `<SERVER\_URL>/vapi/webhook`.

4. Vapi dashboard: **Phone Numbers → Create Phone Number → Free Vapi Number**, then select the "Riley - Patient Intake" assistant under Inbound Settings.
5. Optional: point a free uptime monitor at `/health` every 5–10 minutes so the free web service does not sleep.

### Environment variables

|Variable|Where|Purpose|
|-|-|-|
|`DATABASE\_URL`|Server|PostgreSQL connection string (set by Render); defaults to local SQLite|
|`SEED\_DATA`|Server|`true` inserts two demo patients into an empty table|
|`VAPI\_SECRET`|Server|Optional webhook shared secret|
|`LOG\_LEVEL`|Server|Defaults to INFO|
|`VAPI\_API\_KEY`|Setup script only|Vapi private API key|
|`SERVER\_URL`|Setup script only|Public base URL of the deployed API|
|`VAPI\_MODEL`|Setup script only|LLM used by the assistant (default `gpt-4o`)|

## Tests

`python -m pytest` runs 27 tests:

* **API:** create, field normalisation, 422 with per-field details, 400 for bad UUIDs and filters, 404, filters, partial update, blanking required fields, soft delete keeping the row, unknown fields, dashboard.
* **Voice webhook (simulated Vapi payloads):** full registration then returning-caller lookup, field-specific re-prompt messages, duplicate-phone protection, update flow, arguments as JSON strings, empty optional fields, database failure producing a spoken error, end-of-call transcript storage, webhook secret.
* **Validation:** phones, names, dates, states, ZIPs, sex mapping and spoken emails.

The app was also run end to end against PostgreSQL 16.

## Known limitations and trade-offs

* **Free hosting cold starts.** Render's free tier sleeps after 15 minutes idle; the first tool call after a long idle period may time out. An uptime pinger avoids this; a paid instance removes it.
* **Free Render PostgreSQL expires after 30 days.** Fine for this assessment; production would use a paid or managed database.
* **Spanish.** The prompt switches language, but speech-to-text accuracy in Spanish depends on the transcriber configured in Vapi; for full support, set a multilingual transcriber.
* **No authentication on the REST API**, so reviewers can test it freely. Production would add API keys or OAuth and role-based access, plus HIPAA controls (encryption at rest, audit logs, BAAs), which the brief excludes.
* **Partial calls are not saved as patients**, by design; only their transcripts are kept.
* **Phone validation** checks length and area code, not whether the number is in service.

## Next steps

* Appointment scheduling after registration (mock availability table and a `book\_appointment` tool).
* Per-field confirmation for high-risk fields (spelling back names letter by letter).
* Rate limiting and API keys on the REST API.
* Automated end-to-end voice tests using Vapi's test suites.
* Alembic migrations instead of `create\_all`.

