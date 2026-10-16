# Task C — Xero Integration Review

Answers to C1–C6 for the multi-tenant invoice-sync service (background workers; per-org tokens,
tenant IDs and sync cursors).

## Assumptions (SDK / API version)

- Targets the Xero **OAuth 2.0 API** and the **Accounting API v2.0** (`/api.xro/2.0/Invoices`).
  No vendor SDK is assumed; snippets use plain HTTP so the reasoning is transport-agnostic.
- The internal order system can attach a **stable, unique order reference** (e.g. order ID) that is
  carried into the invoice payload — this is the idempotency anchor in C5.
- Rate limits are read at the **uncertified / Starter tier**; higher tiers change the daily number,
  not the retry mechanics.

---

## C1 — Connection verification

Prove three distinct things before reading invoices: the token is accepted, the tenant is connected,
and we can actually read data *in that tenant*. Use the cheapest call that proves each.

**Step 1 — Token is valid.** Call the token endpoint only if the cached access token is past its
30-minute lifetime (decode the JWT `exp` locally rather than round-tripping). A successful
`POST /connect/token` (`grant_type=refresh_token`) returns a fresh token — this proves the refresh
token is unexpired/unrevoked and the client credentials are accepted. Failure here means the OAuth
layer is broken; refresh (or, past the 30-minute reuse grace period, re-authorise) before anything else.

**Step 2 — Tenant is connected.** `GET https://api.xero.com/connections` with the access token
returns the array of consented tenants (each has `tenantId`, `tenantType`, `tenantName`). This
proves the org we intend to sync is still connected. If our `tenantId` is absent, the connection was
disconnected/deleted — surface a "reconnect required" state; do not retry.

**Step 3 — Data access in that tenant.** One cheap, tenant-scoped read — `GET /Invoices?page=1`
with `xero-tenant-id` set — proves the token has invoice scope and the tenant ID resolves. A `200`
(empty page is fine) completes the proof; `401/403/404` route into the C2 decision tree.

This three-step sequence is minimal: it does not fetch full invoice payloads, does not page, and
never writes, so a bad configuration fails fast and cheap.

**Evidence:** OAuth 2.0 auth-flow guide (token endpoint, 30-min access / 60-day refresh lifetimes,
30-min refresh reuse grace); Connections/Tenants guide (`GET /connections`, `tenantId`). Verified 2026-10-17.

---

## C2 — Failure diagnosis (connections succeed, invoices return 401/403/404)

Root node: **`connections` returns 200, but `GET /Invoices` fails.** Decide by status code, then by
one observable check.

```
invoices request failed
├─ 401  → token problem, not tenant/scope
│   ├─ access token expired  → refresh once, retry. Still 401 → refresh token revoked/expired
│   │                           (past 60d or revoked) → re-authorise (login flow), alert owner.
│   └─ token for wrong app/env → verify client_id matches the env's stored token. Fix config.
├─ 403  → authenticated but not authorised for the *scope*
│   ├─ missing scope         → check the JWT `scope` claim contains accounting.invoices
│   │                           (and accounting.transactions for writes). Re-authorise with correct scope.
│   └─ no tenant permission  → user lost access in Xero; connection may still exist. Re-authorise.
└─ 404  → tenant/resource mismatch (auth is fine)
    ├─ wrong tenant id       → compare `xero-tenant-id` against the connections `tenantId`.
    │                           Stale ID after reconnection → re-read /connections and persist.
    └─ env configuration     → wrong base URL / wrong tenant mapping in this environment.
                                Compare config across envs; fix, don't retry.
```

Key discriminators. **401** is nearly always a token problem — the auth succeeded for `connections`
but the invoice-scoped call is being rejected. Retry once after a refresh; if it persists, the refresh
token is expired (past 60 days) or revoked, so escalate to re-authorisation and alert the org owner.
**403** means authenticated but not authorised: either the `scope` claim is missing `accounting.invoices`
(or `accounting.transactions` for writes), or the user lost access inside Xero while the connection
record still exists. Neither is fixed by retrying — re-authorise with the correct scope. **404**
means the request is well-formed but the tenant/resource does not match: a stale `xero-tenant-id`
(after a reconnect), or an environment pointed at the wrong tenant mapping. Re-read `/connections`,
persist the current ID, and diff config across environments. In every leaf the remedy is configuration
or re-authorisation — never blind retry, and the escalation boundary is "token/scope/user access
changed", which requires a human or a fresh auth flow rather than the worker retrying in place.

**Assumption:** 404 for a non-existent invoice vs. wrong tenant is indistinguishable without
checking the tenant header; the check "compare tenant ID against `/connections`" is the disambiguator.

**Evidence:** OAuth scopes guide (`accounting.invoices`, `accounting.transactions`); Tenants guide
(tenantId source of truth); Accounting API response codes. Verified 2026-10-17.

---

## C3 — Incremental synchronisation (resumable, large org)

**Pagination.** Use `page`/`pageSize` (cap `pageSize` at the documented 100; read `pagination.pageCount`
from the response). Advance the page cursor by requesting `page = N + 1` until `page == pageCount`.

**Change window.** Request only invoices changed since the last run using the `If-Modified-Since`
header (server-evaluated; use the org's last-synced time). Do **not** rely on a worker's local clock —
capture `UpdatedDateUTC` from the highest changed invoice and persist that as the next window's
lower bound.

**Cursor persistence (ordering matters).** Persist the cursor **only after the whole page is durably
written**, never before. If we advance the cursor first and then fail to write, invoices in that page
are permanently skipped.

**Dedup.** Key rows on `InvoiceID` (server primary key) with upsert semantics: a row is overwritten
only when the incoming `UpdatedDateUTC` is newer than the stored one — this also resolves late/out-of-order
arrivals.

**Partial failure.** Treat a page as the commit unit. If a page fails, retry the whole page (writes
are idempotent, so re-applying is safe). If a single invoice fails validation, record it in a
`failed_records` list keyed by `InvoiceID` and continue the page; drain that list on the next run.

**Safe replay.** Replay is safe precisely because every write is an idempotent upsert keyed on
`InvoiceID`. Replay scope = re-running a page from its persisted cursor; it cannot double-count.

**Clock skew / out-of-order.** Because upserts are gated on `UpdatedDateUTC`, an older update arriving
after a newer one is discarded rather than overwriting newer state. Keep the cursor at the persisted
high-water mark, not per-message arrival time.

**Assumption:** `If-Modified-Since` and the `where`/date filter semantics on Invoices are taken from
the Accounting API docs; the exact `UpdatedDateUTC` field name is per the Invoice model.

**Evidence:** Invoices GET (pagination `page`/`pageSize`, `pagination` response, `If-Modified-Since`);
Invoice model (`InvoiceID`, `UpdatedDateUTC`). Verified 2026-10-17.

---

## C4 — Rate limits (HTTP 429)

**Read the headers — do not guess.** On `429`, inspect `X-Rate-Limit-Problem` to learn *which* limit
was hit, and honour `Retry-After` (present when the minute/daily limit is exceeded) as the minimum
wait. Track `X-DayLimit-Remaining`, `X-MinLimit-Remaining`, `X-AppMinLimit-Remaining` to shed load
before hard failure.

**Backoff with full jitter.** When `Retry-After` is absent (e.g. the 5-call concurrency limit),
use exponential backoff with full jitter:

```
sleep = min(cap, base * 2^attempt) * random(0, 1)
```

Jitter spreads workers across the window so a fleet doesn't thundering-herd the same reset instant.

**Concurrency cap.** The per-tenant limit is 5 concurrent / 60 per minute. Gate each worker with a
semaphore (≤ a few concurrent) and a per-tenant token bucket, leaving headroom below the documented
cap so bursts from other code paths don't trip it.

**Retry budget.** Bound retries by both count and wall-clock time (e.g. 5 attempts or 15 minutes).
On exhaustion, move the job to a **dead-letter queue** and raise an alert — never silently drop.

**Scheduling / fairness.** Feed rate-limit signals back into the queue: when a tenant is throttled,
demote its jobs (or pause that tenant's lane) while other tenants continue — per-tenant isolation
prevents one noisy org from starving the rest.

**Do NOT retry:** `401`/`403`/`404` and other non-`429` 4xx — these are authorisation/configuration
or validation errors; retrying repeats the same failure. Also do not retry business validation 4xx
(e.g. invoice-limit errors) blindly. `5xx` get a **small, bounded** retry count only, since they may
be transient, but respect the same budget.

**Assumption:** concurrency/minute/daily figures are the uncertified/Starter tier values; higher
tiers change the daily cap only.

**Evidence:** OAuth 2.0 limits guide (5 concurrent / 60 min / 1000–5000 daily; `429`,
`X-Rate-Limit-Problem`, `Retry-After`, `X-*-Remaining` headers). Verified 2026-10-17.

---

## C5 — Data integrity (timeout-retried invoice creation)

**Prevent duplicates at the source.** Derive a deterministic invoice reference from the internal
order — set `InvoiceNumber` (unique per org for sales invoices; Xero rejects a duplicate with a
validation error) and additionally send an `Idempotency-Key` header on the create. Xero caches the
response for that key and returns the cached result on replay (key TTL ~6 minutes), so a retried
create within the window cannot mint a second invoice.

**Retry-after-timeout path.** Before re-issuing a create for a timed-out order, first **query by
reference**: `GET /Invoices?where=InvoiceNumber=="<ref>"`. If found, *adopt* the existing invoice
(persist its `InvoiceID` against the order) and do not create again. Only create when the lookup
returns empty.

**When the request succeeded but the response was lost.** The Idempotency-Key covers the immediate
replay; beyond its TTL, a reconciliation job closes the gap: it re-queries by `InvoiceNumber` for any
order stuck in `pending`, and advances the order through `pending → confirmed → reconciled` once a
matching `InvoiceID` is found. State transitions are recorded in an audit log.

**Boundary / conflict.** If the reference lookup returns a *different* invoice than expected (number
collision), or the order state is inconsistent, stop and route to a human-review queue with the full
audit trail — do not auto-resolve.

**Do not assume create is natively idempotent.** The discipline rests on the client-supplied
`InvoiceNumber` (deterministic) plus the `Idempotency-Key`, both documented mechanisms — not on
undocumented API behaviour.

**Assumption:** `InvoiceNumber` uniqueness applies to sales (ACCREC) invoices per org; `Idempotency-Key`
applies to POST/PUT/PATCH and is cached ~6 minutes.

**Evidence:** Idempotent requests guide (`Idempotency-Key`, 6-min TTL, key generation); Invoices
model (`InvoiceNumber` unique, duplicate → validation error). Verified 2026-10-17.

---

## C6 — Observability and security

**Logs (structured JSON).** Emit one log per outbound Xero call with: `correlation_id`,
`tenant_id`, `endpoint`, `method`, `status_code`, `duration_ms`, `attempt`, and `xero_request_id`
if returned. Keep tenant data out of log bodies.

**Metrics.** Track: rate-limit hits (by `X-Rate-Limit-Problem`), sync lag (now − last persisted
cursor time), error rate per status class, token-refresh failures, and queue/dead-letter depth.

**Alerts.** Fire on: sync lag exceeding a threshold, a spike in auth failures (possible mass token
revocation), non-empty dead-letter queue, and quota water-mark (e.g. remaining daily calls below 10%).

**Correlation IDs.** Generate a `sync_run_id` per run and propagate it to every downstream call;
pair it with `tenant_id` so a single tenant's failure can be traced across logs and services.
Xero requests carry it in the `Idempotency-Key` or a stable `InvoiceNumber` prefix where possible.

**Never log:** access tokens, refresh tokens, authorization codes, `Idempotency-Key` values, and
personally identifiable invoice content (customer names, emails, addresses). Redact headers by an
allow-list, not a block-list.

**Secrets / tokens.** Store `client_id`/`client_secret` and per-org refresh tokens in a secrets
manager with encryption at rest; never in code, env committed to git, or logs. Rotate on a schedule
and on any suspected leak: revoke via the revocation endpoint, then re-authorise. Refresh tokens
rotate on each refresh — persist the newest value and treat the 30-minute reuse grace as a
recovery window, not normal operation.

**Evidence:** OAuth token security (refresh-token rotation, 30-min reuse, revocation endpoint);
limits guide (headers to monitor). Verified 2026-10-17.
