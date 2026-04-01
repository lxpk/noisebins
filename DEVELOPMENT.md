# Noisebins development plan

Phased work intended for incremental implementation (e.g. in Cursor): each phase has a **goal**, **deliverables**, a **definition of done**, and **notes** on ordering. Later phases assume earlier ones are merged and stable.

Authority for product scope: [README.md](./README.md). If this plan and the README diverge, update the README first, then this file.

---

## Conventions (set once, phase 0)

- **Noisecode:** Pick and document one scheme (URL-safe 8–12 characters with retry on collision, or UUID in paths). Record the choice in README § Noisecode format.
- **API:** REST JSON under a versioned prefix (e.g. `/api/v1/...`). Expose OpenAPI at `/docs` in non-production or behind auth as policy dictates.
- **IDs:** Stable public bin URLs: `/b/{noisecode}` (HTML) mirroring README; API may use same id or internal UUID—if both exist, document the mapping.
- **Frontend strategy:** API-first. MVP UI can be server-rendered forms (Jinja2) plus minimal JavaScript for QR/file upload, or a small SPA—**choose in phase 0** and keep Playwright tests targeting whichever you pick.
- **Secrets:** Never commit; use `.env.example` with dummy values only.

---

## Phase 0 — Repository and runtime baseline

**Goal:** Anyone can run the API and database locally in one command.

**Deliverables:**

- Python project layout (`pyproject.toml` or `requirements.txt`), pinned runtime (e.g. 3.12+).
- `docker compose` with **Postgres**; optional **local object storage** (e.g. MinIO) or documented “dev mode” storing files on disk with the same abstraction used for S3/R2 later.
- Application package (e.g. `noisebins/` or `src/noisebins/`) with a stub FastAPI app and `/health`.
- `.env.example` listing `DATABASE_URL`, blob storage settings, `SECRET_KEY`, auth-related placeholders.
- Basic CI: install deps, **ruff** (or ruff-equivalent) + **pytest** run (even if tests are smoke-only).

**Definition of done:** `docker compose up` → Postgres healthy; `uvicorn` (or chosen entrypoint) serves `/health` and `/docs`.

**Cursor hint:** Generate one small PR: compose + skeleton app + CI; no business routes yet.

---

## Phase 1 — Schema and migrations

**Goal:** Persistence matches README ontology for places and bins (initial slice).

**Deliverables:**

- **Noiseplace** model: `id`, `name`, `description`, optional `photo` reference, `parent_place_id`, timestamps; optional maintainer/guild fields as nullable columns.
- **Noisebin** model: fields per README table: title, description, details, `contents_text`, photos as separate table or JSON strategy (prefer **normalized `bin_photos`** with ordering + blob key), maintainer fields, `group_maintainer`, `intent`, `limbo_after`, `status`, `shelf_hint`, FK to `noiseplace_id`, **noisecode** unique, `created_at` / `updated_at`.
- **Claim fields** (nullable until phase 8): e.g. `claimed_by_user_id`, `claimed_at` if you use FastAPI Users’ user table.
- **Alembic** (or equivalent) migrations from empty DB to this schema.
- Seed script (optional): one place + one bin for local dev.

**Definition of done:** Migrations apply cleanly on fresh DB; noisecode uniqueness enforced; FK from bin → place valid.

**Cursor hint:** One PR for models + migrations only; avoid auth routes until phase 3.

---

## Phase 2 — Read-only public API and bin page

**Goal:** Anonymous read path for discovery (per README threat model: limit PII on public responses).

**Deliverables:**

- `GET /api/v1/places`, `GET /api/v1/places/{id}` (tree or flat list + client assembles tree—document which).
- `GET /api/v1/bins/{noisecode}` — public-safe JSON: omit or mask `maintainer_email`, `maintainer_phone`, `maintainer_discord` unless configured otherwise.
- HTML **`GET /b/{noisecode}`** (or SPA route) showing title, place, status, intent, last updated, and public-safe maintainer display.

**Definition of done:** Curl/browser can load a bin by noisecode without credentials; OpenAPI lists these routes.

**Cursor hint:** Implement serializers/policies in one module so privacy rules remain consistent when fields grow.

---

## Phase 3 — Authentication (first provider only)

**Goal:** Align with README **MVP cut #2**: exactly **one** of FastAPI Users (email + optional Gmail OAuth) **or** Noiseport OAuth2/OIDC—**not both** until phase 13.

**Deliverables:**

- User model integration (FastAPI Users pattern).
- Registration/login/logout flows required for **all writes** (README: writes require auth).
- Protected dependency for routes; public read routes unchanged.
- Document in README which provider ships first (update README when the choice is made).

**Definition of done:** Unauthenticated `POST` to any mutating endpoint returns **401**; authenticated user receives **200** on a smoke mutating test (e.g. placeholder route).

**Cursor hint:** Keep OAuth client config in env; add a short `AUTH.md` or README subsection for obtaining dev credentials.

---

## Phase 4 — Noiseplace writes

**Goal:** Authenticated users can maintain the place hierarchy.

**Deliverables:**

- `POST/PATCH/DELETE` places (policy: all authenticated users vs admin-only—**choose one** for MVP and document).
- Validation: no self-referential `parent_place_id` cycles.

**Definition of done:** Playwright or pytest can create a child place under a parent via API or UI.

---

## Phase 5 — Noisebin CRUD and assignment

**Goal:** Fulfill user story: register bin and assign to Noiseplace.

**Deliverables:**

- `POST /api/v1/bins` — generates noisecode, returns it and public URL.
- `PATCH /api/v1/bins/{noisecode}` — edit text fields, place, intent, limbo_after, status, maintainer fields.
- `DELETE` or soft-delete per chosen policy (prefer **status = archived** over hard delete for MVP).
- UI: create/edit bin form; link from bin page when logged in.

**Definition of done:** README user story (1) works end-to-end with phase-3 auth and phase-4 places.

---

## Phase 6 — Blob storage and photos

**Goal:** Multiple content photos per bin, stored in object storage or dev equivalent.

**Deliverables:**

- Upload path: presigned PUT, or `multipart` upload to API then server writes to blob store—pick one; document max size and allowed MIME types.
- `bin_photos` records link blob keys to bins; public bin page/API returns URLs (signed or public-read bucket—document security).

**Definition of done:** README user story (3) partially satisfied: user can attach photos; **suggested text from vision is still out of scope** until phase 11.

**Cursor hint:** Abstract storage behind an interface to swap MinIO ↔ R2 without touching handlers.

---

## Phase 7 — Search and filter

**Goal:** User story (2): keyword search + filter by Noiseplace.

**Deliverables:**

- Implement **one** search backend per README: Postgres **`tsvector`** **or** Meilisearch—do not wire both in MVP.
- `GET /api/v1/bins/search?q=...&place_id=...` (+ optional `has_photo`, date range as stubs returning 501 or implemented if quick).
- UI: search box + place filter.

**Definition of done:** Integration test: known string in `contents_text` or `title` finds the bin; filter restricts to place.

---

## Phase 8 — Labels (QR + PDF)

**Goal:** Printable label with QR and human-readable noisecode.

**Deliverables:**

- `GET /api/v1/bins/{noisecode}/label.pdf` (auth: owner/maintainer or **global authenticated**—document).
- QR encodes the same URL as `/b/{noisecode}`.
- Optional: multi-up PDF or SVG export (README stretch for label makers).

**Definition of done:** Printed PDF scans to the public bin page (manual QA acceptable for phase exit).

---

## Phase 9 — Audit log and claim / transfer

**Goal:** Claim flow and transfers with audit trail (README register/claim).

**Deliverables:**

- **Audit table:** actor id, action enum, target type/id, timestamp, optional JSON diff.
- Claim: first authenticated user to claim an **unclaimed** bin sets `claimed_by`; record audit.
- **Transfer:** explicit action from current owner to another user; audit mandatory.
- UI: claim button on unclaimed bin; transfer for owner.

**Definition of done:** Two test users can demonstrate claim then transfer with two audit rows inspectable via API or admin view.

---

## Phase 10 — Noisethings and content history

**Goal:** Structured items and version history for bin contents.

**Deliverables:**

- **Noisething** CRUD linked to `parent_bin_id`; optional barcode.
- **Content history** table or event sourcing light: append-only rows for “contents_text / thing list changed” with who/when; optional diff payload.
- UI to add/remove things and view history.

**Definition of done:** Edit bin contents twice; history shows two entries with correct ordering.

---

## Phase 11 — Vision assist (feature-flagged)

**Goal:** OCR / detection suggests text; **no auto-write** to canonical fields without user confirm (README).

**Deliverables:**

- Behind **env flag** (e.g. `VISION_ASSIST_ENABLED`): pipeline from uploaded image → suggested string (Tesseract and/or OpenCV/MediaPipe; Google AI only if keys present).
- API: `POST .../suggest-contents` returning suggestions; client must **confirm** before `PATCH` bin.
- Rate limits and error handling for missing dependencies.

**Definition of done:** With flag off, no new behavior; with flag on, suggestion appears and is not persisted until explicit user action.

---

## Phase 12 — Limbolandia (manual)

**Goal:** README MVP cut #4: `limbo_after` + list view for maintainers.

**Deliverables:**

- Filter/list bins where `limbo_after <= today` or status limbo; **no** automated Discord yet unless trivial webhook behind flag.
- UI for maintainers to set/clear `limbo_after` and status transitions (`active` → `archived` / `disposed`).

**Definition of done:** User story (4) satisfied: last updated visible; intent and limbo date editable.

---

## Phase 13 — PWA polish and in-browser QR

**Goal:** README mobile: responsive UI, installable PWA, QR from camera where browsers allow.

**Deliverables:**

- `manifest.json`, icons, basic service worker (cache shell only—avoid stale API responses).
- Client QR scan (e.g. ZXing) integrated into “open bin” or “claim” flow.
- Manual pass on small-screen layouts for create/search/bin page.

**Definition of done:** “Add to Home Screen” opens app; scan flow works on at least one reference mobile browser (document which).

---

## Phase 14 — Second auth provider

**Goal:** README: add the provider **not** shipped in phase 3 (Noiseport **or** Gmail/email stack).

**Deliverables:**

- Shared abstraction already used in phase 3 extended with second strategy; same user merge/linking rules documented to avoid duplicate accounts surprises.
- Update README auth section to “both available.”

**Definition of done:** Either login path yields a user capable of identical authorized API calls.

---

## Phase 15 — Stretch backlog (optional)

**Goal:** README non-MVP items, prioritized after production hardening.

**Deliverables (pick order by ops need):**

- Moderation: report flag, moderator role.
- Discord (or other) webhook on bin update.
- Semantic search via PydanticAI + embeddings (only if full-text is insufficient).
- Automated Limbolandia notifications and documented disposal workflow.
- Anonymous **suggested** edits queue (if policy allows), still requiring moderator or auth to publish.

**Definition of done:** Each item has tests and is documented in README feature list as shipped.

---

## Quality gates (continuous, not a single phase)

- **pytest:** Model and API tests per phase; increase coverage as surface grows.
- **Playwright:** After phase 5 UI exists, automate README flows: register bin, assign place, search, upload photo (phase 6+), print label smoke (phase 8).
- **Security:** Dependency audit in CI; review signed URL TTLs and public blob policy before any public deploy.

---

## Phase dependency graph (summary)

```text
0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → (15)
          ↑                   ↑
          └─ public read      └─ audit supports claim/transfer (9)
```

Phases 10–12 can overlap in development **after** 9 only if you avoid schema conflicts; lowest risk is strict sequential merge.

---

## Checklist before first production deploy

- [ ] README Noisecode scheme matches implementation.
- [ ] Maintainer PII policy matches serializers for anonymous `GET /b/...`.
- [ ] Backups configured for Postgres and object storage.
- [ ] Object storage buckets are not writable anonymously.
- [ ] Auth secrets rotated from dev values; HTTPS termination documented.
