# registration-service — Requirements

**Contratto di riferimento:** `Exam/techconf-exam/contracts/openapi/registration-service.yaml`
**Standard di piattaforma:** `.kiro/steering/platform-standards.md`
**Suite di collaudo (sola lettura):** `Exam/techconf-exam/tests/integration/test_registration.py` (IT-R01..IT-R10) e `test_journey_mandatory.py` (IT-J01)
**Versione spec:** 1.0 — 2026-09-25
**Workflow:** Requirements-First (fase 1 di 3). Design e tasks NON sono ancora prodotti.

---

## Contesto e scopo

Il registration-service gestisce le iscrizioni degli utenti agli eventi della piattaforma
TechConf. È un servizio **obbligatorio** esposto su `/api/v1/registrations` (porta di
sviluppo 5003).

È il servizio più connesso tra gli obbligatori: **chiama due dipendenze** via HTTP —
user-service (per validare `user_id`) ed event-service (per validare `event_id`, leggere
`status` e copiare `price`). Applica le regole di capienza e di ciclo di vita
dell'iscrizione. È chiamato a sua volta da feedback-service e notification-service
(opzionali, fuori scope qui).

Questo documento definisce user story e acceptance criteria in notazione EARS
(`WHEN … THE SYSTEM SHALL …`, `IF … THEN …`), con ID tracciabili `REQ-REG-*`, e copre
tutti i campi, gli endpoint, le regole di business e gli errori del §5.3 di `Exam.MD` e
del contratto OpenAPI.

---

## Glossario locale

| Termine | Definizione |
|---|---|
| **Iscrizione** | Risorsa identificata da UUID v4 che lega un utente a un evento, con importo e stato |
| **Risorsa read-only** | Campo generato dal server (`id`, `amount`, `created_at`, `updated_at`) che il client non imposta né modifica |
| **`amount`** | Importo dell'iscrizione, copiato da `event.price` al momento della creazione; mai fornito dal client |
| **Iscrizione confermata** | Iscrizione con `status = confirmed`; occupa un posto nella capienza |
| **Posto liberato** | Effetto della cancellazione di un'iscrizione confermata: la capienza disponibile aumenta di uno |
| **Dipendenza** | user-service (validazione utente) ed event-service (validazione evento, prezzo, stato), interrogati via HTTP |
| **Riferimento assente** | `user_id`/`event_id` che non corrisponde ad alcuna risorsa nella rispettiva dipendenza (404 dalla dipendenza) |

---

## Mappa di tracciabilità (requisito → contratto → collaudo)

| Requisito | Contratto (operazione/schema) | Collaudo docente |
|---|---|---|
| REQ-REG-F01 | `GET /health` · `Health` | (avvio suite) |
| REQ-REG-F02 | `POST /api/v1/registrations` · `RegistrationCreate`/`Registration` | IT-R01 |
| REQ-REG-F03 | `RegistrationCreate` (vincoli campi) | IT-R01, IT-R02, IT-R03 |
| REQ-REG-F04 | `GET /api/v1/registrations/{id}` · `Registration` | IT-R01 |
| REQ-REG-F05 | `GET /api/v1/registrations` · `RegistrationPage` (paginazione + filtri) | — |
| REQ-REG-F06 | `PATCH /api/v1/registrations/{id}` · `RegistrationPatch` | IT-R07, IT-J01 |
| REQ-REG-F07 | `DELETE /api/v1/registrations/{id}` | — |
| REQ-REG-F08 | `PUT /api/v1/registrations/{id}` → 405 | IT-R09 |
| REQ-REG-F09 | metodi non previsti / path sconosciuti (405/404) | IT-R09 |
| REQ-REG-F10 | `created_at`/`updated_at` (read-only, timestamp) | — |
| REQ-REG-F11 | schema `Error` (formato uniforme) | IT-R02..R10 |
| REQ-REG-F12 | variabili d'ambiente (`PORT`, `USER_SERVICE_URL`, `EVENT_SERVICE_URL`, `STORAGE_BACKEND`, `DATA_DIR`) | (avvio suite) |
| REQ-REG-F13 | persistenza intercambiabile memory/json/sqlite | — |
| REQ-REG-B01 | esistenza utente (`GET /api/v1/users/{id}`) | IT-R02 |
| REQ-REG-B02 | esistenza evento (`GET /api/v1/events/{id}`) | IT-R03 |
| REQ-REG-B03 | evento `published` | IT-R04 |
| REQ-REG-B04 | no doppia iscrizione `confirmed` | IT-R05, IT-J01 |
| REQ-REG-B05 | capienza evento | IT-R06, IT-J01 |
| REQ-REG-B06 | `amount` = `event.price` | IT-R01 |
| REQ-REG-B07 | transizione `confirmed→cancelled`, libera il posto, no riattivazione | IT-R07, IT-J01 |
| REQ-REG-B08 | `stats` `{event_id, capacity, confirmed, available}`; evento assente → 404 | IT-R08, IT-J01 |
| REQ-REG-B09 | dipendenza non raggiungibile → 503 | IT-R10 |
| REQ-REG-T01 | test unitari, contratto, tre backend, coverage ≥ 80% | — |
| REQ-REG-T02 | test di integrazione propri (positivo, 422, 503) | — |

---

## REQ-REG-F01 — Health check

**User story:** As an infrastructure operator, I want to check the health of the
registration-service, so that the acceptance suite can verify the service is up.

**Acceptance criteria**

1. WHEN a client sends `GET /health` THE registration-service SHALL respond 200 with
   body `{"status": "ok", "service": "registration-service"}`.
2. THE response body SHALL conform to the `Health` schema (`additionalProperties: false`,
   `status` enum `[ok]`).
3. WHEN any other HTTP method is sent to `/health` THE registration-service SHALL
   respond 405.
4. THE health endpoint SHALL respond regardless of storage backend state or the
   availability of the user-service and event-service dependencies; no persistence or
   outbound HTTP call is allowed in this handler.

---

## REQ-REG-F02 — Creazione iscrizione (POST)

**User story:** As an attendee, I want to register for a published event, so that my
seat is reserved at the event's price.

**Acceptance criteria**

1. WHEN a client sends `POST /api/v1/registrations` with a valid body containing
   `user_id` and `event_id`, the user exists (REQ-REG-B01), the event exists
   (REQ-REG-B02) and is `published` (REQ-REG-B03), no duplicate confirmed registration
   exists (REQ-REG-B04) and the event is not full (REQ-REG-B05) THE
   registration-service SHALL create the registration and respond 201 with the
   `Registration` object and a `Location` header set to `/api/v1/registrations/<id>`.
2. THE server SHALL generate a UUID v4 `id`; the client MUST NOT supply `id`.
3. WHEN a registration is created THE `status` SHALL always be `confirmed`; the client
   MUST NOT supply `status` in the create body (`RegistrationCreate` declares only
   `user_id` and `event_id`, `additionalProperties: false`).
4. THE `amount` SHALL be copied from `event.price` read from event-service
   (REQ-REG-B06); the client MUST NOT supply `amount`.
5. THE server SHALL generate `created_at` and `updated_at` as identical ISO 8601 UTC
   timestamps at creation time (REQ-REG-F10).
6. IF the request body contains any field other than `user_id` and `event_id`
   (including `id`, `amount`, `status`, `created_at`, `updated_at`, or any unknown key)
   THEN the registration-service SHALL respond 422 `VALIDATION_ERROR`
   (`additionalProperties: false` on `RegistrationCreate`).
7. THE response body SHALL conform to the `Registration` schema.

---

## REQ-REG-F03 — Validazione dei campi (POST)

**User story:** As a platform, I want registration input validated before any
dependency call, so that malformed requests fail fast.

**Acceptance criteria**

1. IF `user_id` is absent, not a string, or not a syntactically valid UUID THEN the
   registration-service SHALL respond 422 `VALIDATION_ERROR`.
2. IF `event_id` is absent, not a string, or not a syntactically valid UUID THEN the
   registration-service SHALL respond 422 `VALIDATION_ERROR`.
3. THE request body MUST be a JSON object; IF the body is a JSON array, `null`, or a
   scalar THEN the registration-service SHALL respond 422 `VALIDATION_ERROR`.
4. IF the request body is syntactically invalid JSON THEN the registration-service SHALL
   respond 400 (not 422); the error body SHALL conform to the `Error` schema.
   *(400 = JSON syntax broken; 422 = JSON valid but structure/values wrong.)*
5. Field-level validation SHALL run **before** any outbound HTTP call to user-service or
   event-service, so a malformed request never triggers a dependency call.
6. No implicit type coercion SHALL be performed (e.g. a non-string `user_id` is 422, not
   coerced).

---

## REQ-REG-F04 — Lettura iscrizione per ID (GET /{id})

**User story:** As a client, I want to fetch a single registration by id, so that I can
see its status and amount.

**Acceptance criteria**

1. WHEN a client sends `GET /api/v1/registrations/{id}` and the registration exists THE
   registration-service SHALL respond 200 with the `Registration` object.
2. IF the `id` does not correspond to an existing registration THEN the
   registration-service SHALL respond 404 `NOT_FOUND`.
3. THE response body SHALL conform to the `Registration` schema.
4. THE GET-by-id handler SHALL NOT call any dependency.

---

## REQ-REG-F05 — Lista paginata e filtri (GET)

**User story:** As a client, I want a paginated, filterable list of registrations, so
that I can see all registrations for a user, an event, or a status.

**Acceptance criteria**

1. WHEN a client sends `GET /api/v1/registrations` without query parameters THE
   registration-service SHALL respond 200 with
   `{"items": [...], "page": 1, "page_size": 20, "total": <n>}` conforming to the
   `RegistrationPage` schema.
2. WHEN `page` and `page_size` are provided as valid integers (page ≥ 1,
   1 ≤ page_size ≤ 100) THE registration-service SHALL return the corresponding slice
   and echo `page` and `page_size`.
3. IF `page` or `page_size` is empty, non-numeric, non-integer, `page < 1`,
   `page_size < 1`, or `page_size > 100` THEN the registration-service SHALL respond 422
   `VALIDATION_ERROR`.
4. WHEN filters `user_id`, `event_id` and/or `status` are provided THE
   registration-service SHALL apply them with AND logic.
5. IF `status` is provided but not one of `confirmed`, `cancelled` THEN the
   registration-service SHALL respond 422 `VALIDATION_ERROR`.
6. THE `total` field SHALL reflect the filtered count before pagination.
7. THE GET-list handler SHALL NOT call any dependency.

---

## REQ-REG-F06 — Aggiornamento stato (PATCH)

**User story:** As an attendee, I want to cancel my registration, so that I free my seat.

**Acceptance criteria**

1. WHEN a client sends `PATCH /api/v1/registrations/{id}` with body `{"status": "..."}`
   and the registration exists THE registration-service SHALL apply the transition
   subject to REQ-REG-B07 and respond 200 with the updated `Registration`.
2. THE PATCH body MUST contain `status` and no other field (`RegistrationPatch` declares
   `required: [status]`, `additionalProperties: false`); IF `status` is absent, or an
   unknown field is present, THEN the registration-service SHALL respond 422
   `VALIDATION_ERROR`.
3. IF `status` is present but not one of `confirmed`, `cancelled` THEN the
   registration-service SHALL respond 422 `VALIDATION_ERROR`.
4. THE PATCH handler SHALL locate the resource first: IF the `id` does not exist THEN the
   registration-service SHALL respond 404 `NOT_FOUND`.
5. WHEN a non-empty PATCH changes the status THE registration-service SHALL refresh
   `updated_at` (REQ-REG-F10).
6. THE PATCH handler SHALL NOT change `user_id`, `event_id` or `amount`.

---

## REQ-REG-F07 — Cancellazione iscrizione (DELETE)

**User story:** As an administrator, I want to delete a registration record, so that it
is removed from listings.

**Acceptance criteria**

1. WHEN a client sends `DELETE /api/v1/registrations/{id}` and the registration exists
   THE registration-service SHALL delete it and respond 204 with no body and without a
   JSON `Content-Type`.
2. IF the `id` does not exist THEN the registration-service SHALL respond 404
   `NOT_FOUND`.
3. THE DELETE handler SHALL NOT call any dependency.

*(Note on ambiguity: the contract and the track distinguish DELETE — physical removal —
from cancellation via PATCH status `cancelled`. Both exist. DELETE removes the record;
PATCH `cancelled` keeps the record and frees the seat, REQ-REG-B07. The seat-freeing
capacity rule (REQ-REG-B05/B07) counts only records with `status = confirmed`, so a
deleted record also does not count.)*

---

## REQ-REG-F08 — PUT non consentito (405)

**User story:** As an API consumer, I want PUT on a registration to be rejected, so that
the resource is only mutated through the allowed operations.

**Acceptance criteria**

1. WHEN a client sends `PUT /api/v1/registrations/{id}` THE registration-service SHALL
   respond 405 with a JSON error body conforming to the `Error` schema.
2. THE 405 response SHALL be returned regardless of whether the `id` exists (the method
   is not supported for this resource).

*(Trace: IT-R09 — `PUT` → 405. The contract explicitly declares `putRegistrationNotAllowed`
returning 405.)*

---

## REQ-REG-F09 — Metodi non consentiti e percorsi sconosciuti

**User story:** As an API consumer, I want predictable responses for wrong methods and
unknown paths.

**Acceptance criteria**

1. WHEN a client sends a method not defined for a path THE registration-service SHALL
   respond 405 with a JSON `Error` body.
2. WHEN a client requests an unknown path THE registration-service SHALL respond 404
   `NOT_FOUND` with a JSON `Error` body.
3. THE distinction SHALL be: unknown path → 404; known path with unsupported method →
   405.

---

## REQ-REG-F10 — Timestamp e immutabilità

**User story:** As an auditor, I want reliable timestamps, so that I can tell when a
registration was created and last changed.

**Acceptance criteria**

1. THE registration-service SHALL store `created_at` and `updated_at` as ISO 8601 UTC
   timestamps conforming to the contract `date-time` format.
2. WHEN a registration is created THE `created_at` and `updated_at` SHALL be identical.
3. THE `created_at` field SHALL never change after creation.
4. WHEN a PATCH changes the status THE `updated_at` SHALL be refreshed and SHALL be
   greater than or equal to `created_at`.
5. THE fields `id`, `user_id`, `event_id`, `amount`, `status`, `created_at`,
   `updated_at` SHALL be read-only from the client's perspective except `status` via
   the PATCH transition; supplying any read-only field in a create/patch body SHALL
   yield 422 `VALIDATION_ERROR` (`additionalProperties: false`).

---

## REQ-REG-F11 — Formato uniforme degli errori

**User story:** As an API consumer, I want a consistent error shape.

**Acceptance criteria**

1. Every error response SHALL have the body
   `{"error": {"code": "UPPER_SNAKE", "message": "...", "details": {...}}}` conforming to
   the `Error` schema.
2. THE `code` SHALL be one of: `VALIDATION_ERROR`, `REFERENCE_NOT_FOUND`,
   `EVENT_NOT_OPEN`, `ALREADY_REGISTERED`, `EVENT_FULL`, `INVALID_STATUS_TRANSITION`,
   `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `MALFORMED_JSON`, `DEPENDENCY_UNAVAILABLE`.
3. THE HTTP status SHALL match: 400 malformed JSON, 404 not found, 405 method not
   allowed, 409 conflict (`ALREADY_REGISTERED`, `EVENT_FULL`), 422
   validation/reference/business rule (`VALIDATION_ERROR`, `REFERENCE_NOT_FOUND`,
   `EVENT_NOT_OPEN`, `INVALID_STATUS_TRANSITION`), 503 dependency unavailable.
4. THE `error.code` and `error.message` SHALL always be present; `details` MAY be omitted
   or an empty object.

---

## REQ-REG-F12 — Configurazione e variabili d'ambiente

**User story:** As an operator, I want all configuration from environment variables read
in one place.

**Acceptance criteria**

1. THE registration-service SHALL read `PORT` and SHALL listen on it; IF absent or not
   an integer THEN startup SHALL fail with an explicit error.
2. THE registration-service SHALL read `USER_SERVICE_URL` (default
   `http://localhost:5001`) and `EVENT_SERVICE_URL` (default `http://localhost:5002`)
   for its two dependencies.
3. THE registration-service SHALL read `STORAGE_BACKEND` (default `memory`) and
   `DATA_DIR` (default `./data`).
4. ALL environment variables SHALL be read in `app/config.py`; no other module SHALL
   read `os.environ`, and no dependency URL SHALL be hard-coded.
5. Importing the `app` package SHALL NOT require `PORT` to be set.

---

## REQ-REG-F13 — Persistenza intercambiabile (memory / json / sqlite)

**User story:** As a platform, I want to switch storage backend without touching
business logic.

**Acceptance criteria**

1. THE registration-service SHALL support `memory` (default), `json`, `sqlite` selected
   by `STORAGE_BACKEND`, using only the standard library (`json`, `sqlite3`); no
   external DBMS.
2. WHEN `STORAGE_BACKEND=json` THE data SHALL persist to a file under `DATA_DIR` and
   survive a restart.
3. WHEN `STORAGE_BACKEND=sqlite` THE data SHALL persist to a SQLite DB under `DATA_DIR`
   and survive a restart.
4. THE business logic and HTTP layer SHALL be identical across the three backends.
5. THE files produced SHALL live under `DATA_DIR`, excluded from git.

---

## REQ-REG-B01 — Esistenza dell'utente

**User story:** As the platform, I want every registration to reference an existing
user, so that registrations cannot be attributed to non-existent accounts.

**Acceptance criteria**

1. WHEN a registration is created THE registration-service SHALL verify the user by
   calling user-service `GET /api/v1/users/{user_id}`.
2. THE base URL SHALL come from `USER_SERVICE_URL` (default `http://localhost:5001`) and
   the request SHALL use a **2-second** timeout.
3. IF user-service responds 404 for `user_id` THEN the registration-service SHALL
   respond 422 with error code `REFERENCE_NOT_FOUND`.
4. THE user verification SHALL run only after field-level validation has passed
   (REQ-REG-F03-AC5).

*(Trace: IT-R02 — unknown user → 422 `REFERENCE_NOT_FOUND`.)*

---

## REQ-REG-B02 — Esistenza dell'evento

**User story:** As the platform, I want every registration to reference an existing
event, so that registrations always point to a real event.

**Acceptance criteria**

1. WHEN a registration is created THE registration-service SHALL verify the event by
   calling event-service `GET /api/v1/events/{event_id}`.
2. THE base URL SHALL come from `EVENT_SERVICE_URL` (default `http://localhost:5002`)
   with a **2-second** timeout.
3. IF event-service responds 404 for `event_id` THEN the registration-service SHALL
   respond 422 with error code `REFERENCE_NOT_FOUND`.
4. THE event lookup SHALL also provide `event.status` (REQ-REG-B03), `event.price`
   (REQ-REG-B06) and `event.capacity` (REQ-REG-B05) from the same response.

*(Trace: IT-R03 — unknown event → 422 `REFERENCE_NOT_FOUND`.)*

---

## REQ-REG-B03 — Evento pubblicato

**User story:** As the platform, I want registrations only for published events, so that
draft or cancelled events do not accept attendees.

**Acceptance criteria**

1. WHEN the event referenced by `event_id` exists THE registration-service SHALL check
   that its `status` equals `published`.
2. IF the event exists but its `status` is not `published` (e.g. `draft` or `cancelled`)
   THEN the registration-service SHALL respond 422 with error code `EVENT_NOT_OPEN`.

*(Trace: IT-R04 — event in `draft` → 422 `EVENT_NOT_OPEN`.)*

---

## REQ-REG-B04 — Nessuna doppia iscrizione confermata

**User story:** As the platform, I want to prevent a user from being confirmed twice for
the same event, so that seats are not double-counted.

**Acceptance criteria**

1. IF a `confirmed` registration already exists for the same `(user_id, event_id)` THEN
   the registration-service SHALL respond 409 with error code `ALREADY_REGISTERED`.
2. A `cancelled` registration for the same `(user_id, event_id)` SHALL NOT block a new
   registration: WHEN the previous registration is `cancelled` THE registration-service
   SHALL allow a new `confirmed` registration for that pair (subject to capacity).
3. THE duplicate check SHALL be performed atomically together with the capacity check
   and the record creation (see design; concurrency).

*(Trace: IT-R05 — double registration → 409 `ALREADY_REGISTERED`; IT-J01.)*

---

## REQ-REG-B05 — Capienza evento

**User story:** As an organizer, I want registrations to stop when the event is full, so
that we never exceed the venue capacity.

**Acceptance criteria**

1. WHEN a registration is requested AND the confirmed registrations for the event are
   fewer than `event.capacity` THE registration-service SHALL create it with status
   `confirmed`.
2. IF the confirmed registrations for the event are equal to (or greater than)
   `event.capacity` THEN the registration-service SHALL respond 409 with error code
   `EVENT_FULL`.
3. WHEN a confirmed registration is cancelled THE registration-service SHALL free one
   seat (REQ-REG-B07), so a subsequent registration can succeed.
4. THE capacity count SHALL consider only registrations with `status = confirmed` for
   the event.
5. THE capacity check, the duplicate check (REQ-REG-B04) and the record creation SHALL
   be performed atomically to avoid overselling under concurrency.

*(Trace: IT-R06 — capacity 2, third registration → 409 `EVENT_FULL`; IT-J01.)*

---

## REQ-REG-B06 — Importo copiato dall'evento

**User story:** As the platform, I want the registration amount to reflect the event
price at registration time, so that the amount cannot be manipulated by the client.

**Acceptance criteria**

1. WHEN a registration is created THE `amount` SHALL be set equal to `event.price` read
   from event-service.
2. THE client MUST NOT supply `amount`; it is not part of `RegistrationCreate`
   (`additionalProperties: false`), so any client-supplied `amount` yields 422.
3. THE `amount` SHALL be stored and returned as a number with the event's price value.

*(Trace: IT-R01 — `amount = event.price` (149.00).)*

---

## REQ-REG-B07 — Transizione di stato e liberazione posto

**User story:** As an attendee, I want to cancel my registration and free the seat, so
that another attendee can take it; a cancelled registration cannot be reactivated.

**Acceptance criteria**

1. THE only allowed status transition SHALL be `confirmed → cancelled`.
2. IF a PATCH requests `cancelled → confirmed` (reactivation) THEN the
   registration-service SHALL respond 422 with error code `INVALID_STATUS_TRANSITION`.
3. WHEN a PATCH sets `status` to the same value as the stored one (`confirmed →
   confirmed` or `cancelled → cancelled`) THE registration-service SHALL treat it as an
   unchanged no-op: it SHALL NOT be rejected as an invalid transition and SHALL leave
   the status as stored. *(Explicit handling of unchanged status.)*
4. WHEN a `confirmed` registration is cancelled THE registration-service SHALL free one
   seat: the confirmed count for the event decreases by one and a new registration for
   that event can succeed.
5. A cancelled registration SHALL NOT be reactivated by any operation (no path from
   `cancelled` back to `confirmed`).

*(Trace: IT-R07 — cancellation → 200 and seat freed; `cancelled → confirmed` → 422
`INVALID_STATUS_TRANSITION`; IT-J01.)*

---

## REQ-REG-B08 — Statistiche per evento (stats)

**User story:** As an organizer, I want registration statistics for an event, so that I
can see capacity, confirmed and available seats.

**Acceptance criteria**

1. WHEN a client sends `GET /api/v1/registrations/stats?event_id=<id>` and the event
   exists THE registration-service SHALL respond 200 with
   `{"event_id": <id>, "capacity": <n>, "confirmed": <n>, "available": <n>}` conforming
   to the `RegistrationStats` schema.
2. THE `capacity` SHALL be read from event-service; `confirmed` SHALL be the count of
   `confirmed` registrations for the event; `available` SHALL equal
   `capacity - confirmed`.
3. IF the `event_id` does not exist in event-service THEN the registration-service SHALL
   respond 404 with error code `NOT_FOUND`.
4. IF `event_id` is absent from the query THEN the registration-service SHALL respond 422
   `VALIDATION_ERROR` (the contract declares `event_id` as a required query parameter).
5. IF a dependency is unreachable while computing stats THEN the registration-service
   SHALL respond 503 `DEPENDENCY_UNAVAILABLE` (REQ-REG-B09).

*(Trace: IT-R08 — stats correct; unknown event → 404 `NOT_FOUND`; IT-J01 stats
coherent.)*

---

## REQ-REG-B09 — Dipendenza non raggiungibile

**User story:** As the platform, I want a clear error when user-service or event-service
cannot be reached, so that clients can distinguish an unavailable dependency from a
validation failure.

**Acceptance criteria**

1. WHEN a call to user-service or event-service **times out** (after the 2-second
   timeout) THE registration-service SHALL respond 503 with error code
   `DEPENDENCY_UNAVAILABLE`.
2. WHEN the connection to a dependency is **refused** (dependency down / closed port)
   THE registration-service SHALL respond 503 `DEPENDENCY_UNAVAILABLE`.
3. WHEN a dependency responds with a **5xx** status THE registration-service SHALL
   respond 503 `DEPENDENCY_UNAVAILABLE`.
4. A dependency **404** SHALL map to 422 `REFERENCE_NOT_FOUND` (REQ-REG-B01/B02), not to
   503.
5. THE 503 mapping SHALL apply to POST (user and event verification) and to `stats`
   (event lookup).

*(Trace: IT-R10 — dependency unreachable → 503 `DEPENDENCY_UNAVAILABLE`.)*

---

## REQ-REG-T01 — Test unitari, di contratto e tre backend

**User story:** As a maintainer, I want a thorough automated test suite, so that
regressions are caught before the acceptance suite runs.

**Acceptance criteria**

1. THE service SHALL have unit tests run with pytest achieving coverage ≥ 80% on the
   `app` package (`py -3.12 -m pytest tests/unit --cov=app --cov-report=term-missing
   --cov-fail-under=80`).
2. ALL outbound HTTP calls to user-service and event-service SHALL be mocked at the
   library level with `responses` in unit tests; no real network call SHALL leave the
   test process.
3. THE repository SHALL be tested against **all three** backends (`memory`, `json`,
   `sqlite`), using `tmp_path` for `json`/`sqlite`.
4. THE unit suite SHALL include at least **one contract test per operation** defined in
   the contract (`health`, `createRegistration`, `listRegistrations`,
   `registrationStats`, `getRegistration`, `updateRegistration`, `deleteRegistration`;
   the 405 `putRegistrationNotAllowed` is verified by status/body without the validator)
   using `assert_matches_contract`.
5. THE unit suite SHALL cover the business outcomes with mocked responses:
   REFERENCE_NOT_FOUND (user 404, event 404), EVENT_NOT_OPEN, ALREADY_REGISTERED,
   EVENT_FULL, amount copied from price, cancellation freeing a seat,
   INVALID_STATUS_TRANSITION on reactivation, stats (present and missing event),
   DEPENDENCY_UNAVAILABLE (timeout/connection/5xx).
6. THE unit suite SHALL include a **concurrency test** proving that the combined
   duplicate + capacity + create sequence does not oversell an event with capacity 1
   under concurrent requests (REQ-REG-B04/B05).
7. Each test SHALL be traceable to a requirement via `@pytest.mark.req("REQ-REG-…")` or
   the id in the name/docstring.

---

## REQ-REG-T02 — Test di integrazione propri

**User story:** As a maintainer, I want my own integration tests that start the real
services, so that inter-service HTTP behaviour is verified end-to-end without mocks.

**Acceptance criteria**

1. THE registration-service SHALL have its own integration tests that start the **real**
   user-service, event-service and registration-service as subprocesses on free ports,
   wait for `/health`, and terminate them in a `try/finally` block (with a `kill`
   fallback).
2. THE integration tests SHALL include at least **one positive case**: create a user, a
   published event (via the real event-service, which itself verifies the organizer on
   the real user-service), then register → 201 with `status="confirmed"` and
   `amount == event.price`.
3. THE integration tests SHALL include at least **one non-existent reference case**:
   register with a `user_id` (or `event_id`) unknown to its dependency → 422
   `REFERENCE_NOT_FOUND`.
4. THE integration tests SHALL include at least **one dead-dependency case**: start the
   registration-service pointing `USER_SERVICE_URL`/`EVENT_SERVICE_URL` at a closed port
   and attempt a create → 503 `DEPENDENCY_UNAVAILABLE`.
5. Each integration test SHALL be traceable to a requirement.

---

## Note di ambiguità e decisioni

- **DELETE vs cancellazione.** Il contratto espone sia `DELETE` (rimozione fisica del
  record, 204) sia `PATCH status=cancelled` (mantiene il record, libera il posto). Sono
  operazioni distinte: la capienza (REQ-REG-B05) conta solo i record `confirmed`, quindi
  sia il `cancelled` sia il record cancellato non occupano posto. DELETE non è una
  transizione di stato.
- **Ordine delle verifiche in POST.** (1) validazione campo; (2) esistenza utente
  (B01); (3) esistenza evento + stato + prezzo + capienza (B02/B03/B06/B05); (4) duplicato
  (B04) + capienza (B05) + creazione, atomici. L'ordine tra utente ed evento non è
  imposto dalla traccia; si sceglie utente prima di evento. Un 404 su una qualsiasi
  dipendenza → 422 `REFERENCE_NOT_FOUND`; un problema di disponibilità → 503.
- **Atomicità duplicato + capienza + creazione.** Per evitare overselling e doppie
  iscrizioni sotto concorrenza, il controllo duplicato, il conteggio dei `confirmed` e
  la scrittura del nuovo record avvengono in un'unica sezione critica protetta dal lock
  del repository (dettaglio nel design). Le chiamate HTTP alle dipendenze avvengono
  **prima** della sezione critica (non si tiene il lock durante l'I/O di rete).
- **`stats` e capacità.** `capacity` proviene da event-service (verità sull'evento);
  `confirmed` è conteggiato localmente; `available = capacity - confirmed`. Evento
  inesistente → 404 (non 422), come da contratto e IT-R08.
- **`amount` numerico.** Il contratto usa `type: number`; la piattaforma implica 2
  decimali (EUR). Il valore è quello di `event.price` letto dalla dipendenza; nessun
  arrotondamento arbitrario oltre a quanto restituito dall'evento.
- **Nessuna mutazione dopo errore.** Se una verifica (dipendenza, duplicato, capienza,
  transizione) fallisce, nessun record viene creato o modificato (lo stato del repository
  resta invariato).
- **`RegistrationPatch` accetta solo `status`.** `user_id`, `event_id`, `amount` non
  sono modificabili via PATCH; qualsiasi altro campo → 422 (`additionalProperties:
  false`).
