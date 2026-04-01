# noisebins

Storage at Noisebridge is a challenge: we always have more things we want in the space than space for the things.

Bins stack vertically in shelving to use space efficiently. We use stacks of translucent bins and track them with **noisecodes** so there is a database of bin contents and where they live.

## Definitions

- **Noisecode** — Stable public identifier for a bin (or resolvable token); resolves to a canonical URL for that bin.
- **QR on labels** — Encodes that URL (or a short code that redirects). Same bin, same Noisecode for life of the label.
- **Noisebin** — A labeled translucent bin we track.
- **Noisething** — An item we track that is not itself a bin (may live inside a bin).
- **Noiseplace** — A storage region larger than a bin (e.g. rolling shelf, room area) that contains one or more Noisebins.
- **Auto-Limbolandia** — Policy for abandoned binned material: disposal or giveaway after rules below.

---

## Features

- **Search** — Find bins and things by text; optional facets: location (Noiseplace), maintainer, date range, tags, “has photo.” Full-text on title, description, details; optional semantic search over OCR + LLM summaries (PydanticAI).
- **Register / claim** — Register bins with printed QR+URL labels via desktop or mobile web. **Claim flow:** scan QR → if unclaimed, attach to logged-in user or anonymous session; support **transfer** with an audit trail.
- **Contents** — List contents as free text and/or **structured items** (name, quantity, photo, optional barcode). **Version history** per bin (what changed, when, who).
- **Photos** — Update bin contents by photographing bins (phone-friendly UI). Vision output is **suggestive**: OCR + detection (OpenCV / MediaPipe / optional Google AI) with **human confirm** before persisting as canonical contents.
- **Labels** — Printable label PDFs: QR + short human-readable code; optional multi-up sheet and PNG/SVG for Bluetooth label makers.
- **Places** — Browse and assign bins to **Noiseplaces** (hierarchical: building → area → shelf).
- **Anonymous use** — Read public bin pages; limited write paths as configured (see Threat model).
- **Moderation (stretch)** — Report incorrect or spam content; moderator role (Noiseport group or local admin).

---

## Database ontology

### Entity relationships

- A **Noisebin** belongs to one **Noiseplace** (optional free-text “shelf hint” in addition).
- A **Noisebin** holds zero or more **Noisethings** (references or embedded lightweight rows).
- **Noiseplaces** may nest (`parent_place_id`) for hierarchy.
- **Audit log** — `actor`, `action`, `timestamp`, `target` (bin/place/thing id), optional before/after diff or snapshot.

### Noisebin fields

| Field | Notes |
| --- | --- |
| `id` | Noisecode / UUID — stable public id |
| `title` | Short label |
| `description`, `details` | Longer text |
| `photos[]` | Contents photos; multiple angles allowed |
| `contents_text` | Free-text summary of contents |
| `group_maintainer` | Group ownership if the bin belongs to one or more guilds |
| `maintainer` | Primary contact model (pick one style in impl): **either** structured **or** a single “contact note” + optional verified Noiseport user — avoid duplicating the same person without a “primary” channel |
| `maintainer_name` | Cleaner, collector, owner, or maintainer display name |
| `maintainer_discord`, `maintainer_email`, `maintainer_phone` | Optional; respect privacy (see Threat model) |
| `created_at`, `updated_at` | Timestamps |
| `intent` | Tags or enum, e.g. personal, shared, hackathon stash, limbo |
| `noisethings` | List of tracked Noisethings in this bin |
| `location` | FK to Noiseplace + optional shelf hint string |
| `limbo_after` | Optional date for Auto-Limbolandia |
| `status` | e.g. active, archived, disposed |

### Noisething fields

- `id`, `name`, `description`, optional `photo`, optional `barcode`, optional `parent_bin_id`, `tags[]`

### Noiseplace fields

Mirror Noisebin where useful:

- `id`, `name`, `description`, optional `photo`
- `parent_place_id` (nullable, for hierarchy)
- Optional **maintainer** / guild fields consistent with bins
- Implied relation: **child bins** (Noisebins at this place)

### Auto-Limbolandia

- **Rule:** Material may be given away or disposed after expiration from last meaningful update, if marked abandoned or past `limbo_after`.
- **Clarify in ops:** Who may set `limbo_after` or “abandoned”; default suggested TTL; **notifications** (e.g. Discord/webhook) before disposal; **soft-delete vs archive** vs hard delete; whether photos and contents are retained when a bin is disposed.

---

## Noisecode format

- **Implementation:** 10 characters from a URL-safe reduced alphabet (no `0/O`, `1/l/I`); collision handling is **retry on insert** (see `noisebins/services/noisecode.py`).
- Public URL pattern: `https://…/b/{noisecode}` (local dev: `/b/{noisecode}`).

---

## User stories (MVP acceptance targets)

1. **As a member**, I register a new bin, print a label with QR, and assign it to a Noiseplace so others can find it.
2. **As a member**, I search by keyword and filter by place to find which bin holds a thing.
3. **As a member**, I upload a photo and optionally accept suggested text for contents without that text auto-published unchecked.
4. **As a maintainer**, I see when my bin was last updated and can set intent / limbo date.

---

## Threat model & privacy

- **Public vs member-only:** Decide whether maintainer email/phone/Discord appear on **anonymous** public pages; default toward **Noiseport-authenticated** or **obfuscated** contact (e.g. “Contact via Noiseport”) for PII.
- **Write access:** Prefer authenticated users for edits; anonymous limited to suggestions or disabled unless policy says otherwise.
- **Media:** Photos may include faces or sensitive items; allow takedown and moderator actions.

---

## Software stack

### Web app

- **Python**, **FastAPI**, **Pydantic v2**; **PydanticAI** for summaries, labeling suggestions, optional semantic search assist.
- **Auth:** **FastAPI Users** + Gmail OAuth; second provider **Noiseport** (OAuth2/OIDC) behind a small abstraction: [noiseport](https://github.com/noisebridge/noiseport).
- **QR / labels:** Server-side generation (e.g. `segno` / `qrcode`) for PDF; client scan via e.g. **ZXing** in browser where possible.
- **Vision:** **OpenCV**, **MediaPipe**; add **OCR** (e.g. Tesseract or cloud) for text on labels; **Google AI** optional behind feature flag and policy.
- **Data:** Postgres for relational data; object storage (S3-compatible or R2) for photos; search via Postgres full-text (`tsvector`) or **Meilisearch** — pick one for MVP.
- **API:** OpenAPI documented; **public read** by Noisecode where policy allows; **writes** require auth.
- **Noise integration:** Specify per integration (e.g. Discord webhook on bin update, links to other Noisebridge tools) to avoid vague “integration to Noise” scope creep.

### Mobile

- **Mobile-first responsive web / PWA** shared with the same backend: QR scan, camera upload, “Add to Home Screen.” Escalate to Capacitor/native only if camera or BLE label printers require it.

### Ops & quality

- `docker compose` for local API + DB (+ optional search); env-based config; backups for DB + blobs.
- **Tests:** API contract tests; **Playwright** (or equivalent) for critical flows: register bin, add photo, search.

---

## MVP cuts (ship order)

1. Single web app: register bin, edit fields, one or more photos, QR PDF, text search + filter by Noiseplace.
2. **One** auth path first: Noiseport **or** email/Gmail — add the second after the first is end-to-end.
3. Vision/OCR as optional **“suggest contents”** behind a feature flag.
4. Limbolandia: **manual** `limbo_after` + admin/maintainer list view; automate reminders later.

---

## Auth integrations

- **Shipped in this repo (MVP / phase 3):** **FastAPI Users** with email + password and **JWT** (`POST /auth/register`, `POST /auth/jwt/login`). Use `Authorization: Bearer <token>` for write APIs.
- **Second provider (phase 14):** **Noiseport** OAuth stub at `GET /auth/noiseport/login` (returns 501 until `NOISEPORT_OAUTH_ENABLED` and URLs are configured). Gmail OAuth can follow the same pattern behind FastAPI Users.

## Development

Phased implementation guide for incremental work (dependencies, deliverables, definition of done): [DEVELOPMENT.md](./DEVELOPMENT.md).

Use PyTest and Playwright to automate testing.

### Run locally

1. Copy `.env.example` → `.env` and start Postgres (`docker compose up -d` or your own instance).
2. `pip install -e ".[dev]"` from the repo root.
3. `alembic upgrade head` then `uvicorn noisebins.main:app --reload --host 0.0.0.0 --port 8000`.
4. Open `http://127.0.0.1:8000/docs` for OpenAPI. CI runs `ruff`, `pytest` (API tests against Postgres), and a short Playwright smoke against a live server.

**MVP policy:** any authenticated user may create, update, or delete **Noiseplaces** (no admin-only gate yet). Refine if you introduce moderation roles.