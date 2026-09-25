# event-service — Requirements

**Contratto di riferimento:** `Exam/techconf-exam/contracts/openapi/event-service.yaml`
**Standard di piattaforma:** `.kiro/steering/platform-standards.md`
**Suite di collaudo (sola lettura):** `Exam/techconf-exam/tests/integration/test_event.py` (IT-E01..IT-E08)
**Versione spec:** 1.0 — 2026-09-25
**Workflow:** Requirements-First (fase 1 di 3). Design e tasks NON sono ancora prodotti.

---

## Contesto e scopo

L'event-service gestisce le conferenze della piattaforma TechConf: risorse con un
ciclo di vita (`draft` → `published` → `cancelled`) e una capienza. È un servizio
**obbligatorio** esposto su `/api/v1/events` (porta di sviluppo 5002).

A differenza del user-service, l'event-service **chiama un altro microservizio**: per
creare o aggiornare un evento deve verificare che l'organizzatore (`organizer_id`)
esista nel user-service e abbia il ruolo `organizer`. È chiamato a sua volta da
registration-service e feedback-service, che leggono gli eventi tramite le sue API.

Questo documento definisce le user story e gli acceptance criteria in notazione EARS
(`WHEN … THE SYSTEM SHALL …`, `IF … THEN …`), con ID tracciabili `REQ-EVT-*`, e copre
tutti i campi, gli endpoint, le regole di business e gli errori del §5.2 di `Exam.MD`
e del contratto OpenAPI.

---

## Glossario locale

| Termine | Definizione |
|---|---|
| **Evento** | Risorsa conferenza identificata da UUID v4, con anagrafica, capienza, prezzo e stato |
| **Organizzatore** | Utente del user-service il cui `id` è referenziato da `organizer_id` e il cui `role` è `organizer` |
| **Risorsa read-only** | Campo generato dal server (`id`, `created_at`, `updated_at`) che il client non può impostare né modificare |
| **PUT sostitutivo** | Sostituisce tutti i campi modificabili con i valori forniti nel body, mantenendo `id` e `created_at` invariati; i campi opzionali assenti tornano ai default (POST-style) |
| **PATCH parziale** | Aggiorna solo i campi presenti nel body; i campi assenti restano invariati |
| **Stato invariato** | Un aggiornamento (PUT/PATCH) in cui il valore di `status` inviato coincide con quello già memorizzato, oppure `status` è assente dal body |
| **Dipendenza** | Il user-service, interrogato via HTTP per validare l'organizzatore |
| **Riferimento assente** | `organizer_id` che non corrisponde ad alcun utente nel user-service (risposta 404 dalla dipendenza) |

---

## Mappa di tracciabilità (requisito → contratto → collaudo)

| Requisito | Contratto (operazione/schema) | Collaudo docente |
|---|---|---|
| REQ-EVT-F01 | `GET /health` · schema `Health` | (avvio suite) |
| REQ-EVT-F02 | `POST /api/v1/events` · `EventCreate`/`Event` | IT-E01 |
| REQ-EVT-F03 | `EventCreate` (vincoli campi) | IT-E01, IT-E04 |
| REQ-EVT-F04 | `EventUpdate` (vincoli campi PATCH) | IT-E05, IT-E07 |
| REQ-EVT-F05 | `GET /api/v1/events/{id}` · `Event` | IT-E07 |
| REQ-EVT-F06 | `GET /api/v1/events` · `EventPage` (paginazione + filtri) | IT-E06 |
| REQ-EVT-F07 | `PUT /api/v1/events/{id}` · `EventCreate`/`Event` | IT-E07 |
| REQ-EVT-F08 | `PATCH /api/v1/events/{id}` · `EventUpdate`/`Event` | IT-E05, IT-E07 |
| REQ-EVT-F09 | `DELETE /api/v1/events/{id}` | IT-E07 |
| REQ-EVT-F10 | metodi non previsti / path sconosciuti (405/404) | — |
| REQ-EVT-F11 | `created_at`/`updated_at` (read-only, timestamp) | IT-E07 |
| REQ-EVT-F12 | schema `Error` (formato uniforme) | IT-E02, IT-E03, IT-E04, IT-E05, IT-E08 |
| REQ-EVT-F13 | variabili d'ambiente (`PORT`, `USER_SERVICE_URL`, `STORAGE_BACKEND`, `DATA_DIR`) | (avvio suite) |
| REQ-EVT-F14 | persistenza intercambiabile memory/json/sqlite | — |
| REQ-EVT-B01 | verifica esistenza organizzatore (`GET /api/v1/users/{id}`) | IT-E02 |
| REQ-EVT-B02 | ruolo organizzatore = `organizer` | IT-E03 |
| REQ-EVT-B03 | `end_date` ≥ `start_date` | IT-E04 |
| REQ-EVT-B04 | transizioni di stato ammesse | IT-E05 |
| REQ-EVT-B05 | dipendenza (user-service) non raggiungibile → 503 | IT-E08 |
| REQ-EVT-B06 | filtri lista per `status` e `city` | IT-E06 |
| REQ-EVT-T01 | test unitari, di contratto, tre backend, coverage ≥ 80% | — |
| REQ-EVT-T02 | test di integrazione propri (positivo, 422, 503) | — |

---

## REQ-EVT-F01 — Health check

**User story:** As an infrastructure operator, I want to check the health of the
event-service with a simple HTTP call, so that the acceptance suite and orchestration
can verify the service is up before routing traffic.

**Acceptance criteria**

1. WHEN a client sends `GET /health` THE event-service SHALL respond 200 with body
   `{"status": "ok", "service": "event-service"}`.
2. THE response body SHALL conform to the `Health` schema in the contract
   (`additionalProperties: false`, required fields `status` and `service`,
   `status` enum `[ok]`).
3. WHEN any other HTTP method is sent to `/health` THE event-service SHALL respond 405.
4. THE health endpoint SHALL respond regardless of storage backend state or the
   availability of the user-service dependency; no persistence or outbound HTTP call
   is allowed in this handler.

---

## REQ-EVT-F02 — Creazione evento (POST)

**User story:** As an organizer, I want to create a new event by submitting its
details, so that it can later be published and opened to registrations.

**Acceptance criteria**

1. WHEN a client sends `POST /api/v1/events` with a valid JSON body that passes field
   validation (REQ-EVT-F03) and whose `organizer_id` references a valid organizer
   (REQ-EVT-B01, REQ-EVT-B02) THE event-service SHALL create the event and respond 201
   with the created `Event` object and a `Location` header set to
   `/api/v1/events/<id>`.
2. THE server SHALL generate a UUID v4 `id` for every new event; the client MUST NOT
   supply `id` in the request body.
3. THE server SHALL generate `created_at` and `updated_at` as identical ISO 8601 UTC
   timestamps at creation time; both fields are read-only and MUST NOT be accepted
   from the client (REQ-EVT-F11).
4. IF the request body contains any field not defined in the `EventCreate` schema
   (`id`, `created_at`, `updated_at`, or any unknown key) THEN the event-service
   SHALL respond 422 `VALIDATION_ERROR`.
   *(Rationale: the contract declares `additionalProperties: false` on `EventCreate`.)*
5. WHEN `status` is omitted from the request body THE event-service SHALL default it
   to `"draft"`.
6. WHEN `description` is omitted from the request body THE event-service SHALL set it
   to `null` in the stored record and in the response; WHEN `description` is explicitly
   `null` THE event-service SHALL store and return `null`.
7. THE order of validation SHALL be: (a) body is a JSON object; (b) field-level
   validation (REQ-EVT-F03) including `end_date` ≥ `start_date` (REQ-EVT-B03);
   (c) organizer verification via user-service (REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B05).
   Field-level `VALIDATION_ERROR` SHALL be reported before any outbound HTTP call is made.
8. THE response body SHALL conform to the `Event` schema in the contract (all required
   fields present, `additionalProperties: false`).

---

## REQ-EVT-F03 — Validazione dei campi (POST e PUT)

**User story:** As a platform, I want event input validated before persistence, so
that stored events are always consistent with the contract and business rules.

**Acceptance criteria**

1. IF `title` is absent, not a string, shorter than 3 characters, or longer than 120
   characters THEN the event-service SHALL respond 422 `VALIDATION_ERROR`.
2. IF `organizer_id` is absent, not a string, or not a syntactically valid UUID THEN
   the event-service SHALL respond 422 `VALIDATION_ERROR` (before any outbound call).
3. IF `venue` is absent, not a string, or longer than 100 characters THEN the
   event-service SHALL respond 422 `VALIDATION_ERROR`.
4. IF `city` is absent, not a string, or longer than 60 characters THEN the
   event-service SHALL respond 422 `VALIDATION_ERROR`.
5. IF `start_date` or `end_date` is absent or not a valid `YYYY-MM-DD` date THEN the
   event-service SHALL respond 422 `VALIDATION_ERROR`.
6. IF `capacity` is absent, not an integer, lower than 1, or greater than 10000 THEN
   the event-service SHALL respond 422 `VALIDATION_ERROR`.
7. IF `price` is absent, not a number, or lower than 0 THEN the event-service SHALL
   respond 422 `VALIDATION_ERROR`.
8. IF `description` is present, not `null`, and longer than 2000 characters THEN the
   event-service SHALL respond 422 `VALIDATION_ERROR`.
9. IF `status` is present and not one of `draft`, `published`, `cancelled` THEN the
   event-service SHALL respond 422 `VALIDATION_ERROR`.
10. THE request body MUST be a JSON object (`{...}`); IF the body is a JSON array,
    `null`, or a scalar value THEN the event-service SHALL respond 422
    `VALIDATION_ERROR`.
11. Each field MUST match the type declared in the `EventCreate` schema; implicit type
    coercions (e.g. the string `"100"` for the integer `capacity`) SHALL NOT be
    performed. IF a field is present with the wrong type THEN the event-service SHALL
    respond 422 `VALIDATION_ERROR`. The only field that accepts `null` as a value is
    `description`.
12. IF the request body is syntactically invalid JSON (not parseable) THEN the
    event-service SHALL respond 400 (not 422); the error body SHALL conform to the
    `Error` schema.
    *(Distinction: 400 = JSON syntax broken; 422 = JSON valid but structure/values wrong.)*

---

## REQ-EVT-F04 — Validazione dei campi (PATCH)

**User story:** As a client, I want to send partial updates with only the fields I
want to change, so that I do not have to resend the whole event.

**Acceptance criteria**

1. WHEN a client sends `PATCH /api/v1/events/{id}` THE event-service SHALL accept a
   body containing any subset of the fields defined in the `EventUpdate` schema.
2. IF the body contains any field not defined in the `EventUpdate` schema THEN the
   event-service SHALL respond 422 `VALIDATION_ERROR`
   (`EventUpdate` declares `additionalProperties: false`).
3. WHEN a field is present in the PATCH body THE event-service SHALL apply to it the
   same value and type constraints declared in REQ-EVT-F03 (length, range, enum, type).
4. WHEN a field is absent from the PATCH body THE event-service SHALL leave the stored
   value unchanged.
5. THE PATCH handler SHALL locate the resource first: IF the `id` does not exist THEN
   the event-service SHALL respond 404 `NOT_FOUND`, even when the body is `{}`.
6. WHEN the PATCH body is `{}` (no fields) THE event-service SHALL return the stored
   record unchanged and SHALL NOT modify `updated_at`.
7. WHEN a PATCH changes `start_date` and/or `end_date` THE event-service SHALL
   re-validate the invariant `end_date` ≥ `start_date` against the resulting effective
   values (REQ-EVT-B03).
8. WHEN a PATCH changes `organizer_id` THE event-service SHALL re-verify the new
   organizer against user-service (REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B05).
9. WHEN a PATCH changes `status` THE event-service SHALL enforce the allowed
   transitions (REQ-EVT-B04); the handling of an unchanged `status` is defined in
   REQ-EVT-B04.

---

## REQ-EVT-F05 — Lettura evento per ID (GET /{id})

**User story:** As a consumer service (registration, feedback), I want to fetch a
single event by id, so that I can validate references and read its price, status and
capacity.

**Acceptance criteria**

1. WHEN a client sends `GET /api/v1/events/{id}` and the event exists THE event-service
   SHALL respond 200 with the `Event` object.
2. IF the `id` does not correspond to an existing event THEN the event-service SHALL
   respond 404 `NOT_FOUND`.
3. THE response body SHALL conform to the `Event` schema in the contract.
4. THE GET-by-id handler SHALL NOT call the user-service dependency.

---

## REQ-EVT-F06 — Lista paginata e filtri (GET)

**User story:** As a client, I want a paginated, filterable list of events, so that I
can browse published conferences in a given city without loading everything at once.

**Acceptance criteria**

1. WHEN a client sends `GET /api/v1/events` without query parameters THE event-service
   SHALL respond 200 with `{"items": [...], "page": 1, "page_size": 20, "total": <n>}`
   conforming to the `EventPage` schema.
2. WHEN `page` and `page_size` are provided as valid integers (page ≥ 1,
   1 ≤ page_size ≤ 100) THE event-service SHALL return the corresponding slice and echo
   the applied `page` and `page_size` in the response.
3. IF `page` or `page_size` is empty, non-numeric, non-integer, `page < 1`,
   `page_size < 1`, or `page_size > 100` THEN the event-service SHALL respond 422
   `VALIDATION_ERROR`.
4. WHEN filters `status` and/or `city` are provided THE event-service SHALL apply them
   with AND logic (REQ-EVT-B06).
5. THE `total` field SHALL reflect the count of items after filtering and before
   pagination.
6. WHEN a page beyond the last is requested THE event-service SHALL respond 200 with an
   empty `items` array and the correct `total`.
7. THE GET-list handler SHALL NOT call the user-service dependency.

---

## REQ-EVT-F07 — Sostituzione evento (PUT)

**User story:** As an organizer, I want to replace an event's data in a single call,
so that I can correct all its mutable fields at once.

**Acceptance criteria**

1. WHEN a client sends `PUT /api/v1/events/{id}` with a body valid against the
   `EventCreate` schema and the event exists THE event-service SHALL replace all
   mutable fields and respond 200 with the updated `Event`.
2. IF the `id` does not exist THEN the event-service SHALL respond 404 `NOT_FOUND`.
3. THE PUT body SHALL be validated with the same rules as POST (REQ-EVT-F03); all
   required fields of `EventCreate` MUST be present.
4. WHEN the PUT body omits an optional field (`description`, `status`) THE
   event-service SHALL apply POST-style defaults (`description` → `null`;
   `status` → see REQ-EVT-B04 for transition handling on replace).
5. THE PUT handler SHALL preserve `id` and `created_at` and SHALL refresh `updated_at`
   (REQ-EVT-F11).
6. WHEN the PUT body sets `organizer_id` THE event-service SHALL verify the organizer
   against user-service (REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B05).
7. WHEN the PUT body implies a `status` change relative to the stored value THE
   event-service SHALL enforce the allowed transitions (REQ-EVT-B04).

---

## REQ-EVT-F08 — Aggiornamento parziale (PATCH)

**User story:** As an organizer, I want to update selected fields of an event, so that
I can, for example, change its venue or publish it without resending everything.

**Acceptance criteria**

1. WHEN a client sends `PATCH /api/v1/events/{id}` with a valid partial body and the
   event exists THE event-service SHALL apply only the present fields and respond 200
   with the updated `Event`.
2. THE validation, resource-lookup-first, empty-body, re-validation and transition
   rules of REQ-EVT-F04 SHALL apply.
3. WHEN at least one field is changed THE event-service SHALL refresh `updated_at`
   (REQ-EVT-F11).
4. THE response body SHALL conform to the `Event` schema.

---

## REQ-EVT-F09 — Cancellazione evento (DELETE)

**User story:** As an organizer, I want to delete an event, so that it no longer
appears in listings.

**Acceptance criteria**

1. WHEN a client sends `DELETE /api/v1/events/{id}` and the event exists THE
   event-service SHALL delete it and respond 204 with no body and without a JSON
   `Content-Type`.
2. IF the `id` does not exist THEN the event-service SHALL respond 404 `NOT_FOUND`.
3. WHEN a deleted event is requested again with `GET /api/v1/events/{id}` THE
   event-service SHALL respond 404.
4. THE DELETE handler SHALL NOT call the user-service dependency.

---

## REQ-EVT-F10 — Metodi non consentiti e percorsi sconosciuti

**User story:** As an API consumer, I want predictable responses for wrong methods and
unknown paths, so that clients can distinguish "not found" from "method not allowed".

**Acceptance criteria**

1. WHEN a client sends a method not defined for a path (e.g. `POST /api/v1/events/{id}`)
   THE event-service SHALL respond 405 with a JSON error body conforming to the `Error`
   schema.
2. WHEN a client requests an unknown path THE event-service SHALL respond 404
   `NOT_FOUND` with a JSON error body.
3. THE distinction SHALL be: unknown path → 404; known path with unsupported method →
   405.

---

## REQ-EVT-F11 — Timestamp e immutabilità

**User story:** As an auditor, I want reliable creation and modification timestamps, so
that I can tell when an event was created and last changed.

**Acceptance criteria**

1. THE event-service SHALL store `created_at` and `updated_at` as ISO 8601 UTC
   timestamps (e.g. `2026-10-15T09:30:00Z`) conforming to the contract `date-time`
   format.
2. WHEN an event is created THE `created_at` and `updated_at` SHALL be identical.
3. THE `created_at` field SHALL never change after creation, including across PUT and
   PATCH.
4. WHEN a PUT or a non-empty PATCH modifies an event THE `updated_at` SHALL be refreshed
   to the current time and SHALL be greater than or equal to `created_at`.
5. WHEN a PATCH with an empty body (`{}`) is applied THE `updated_at` SHALL NOT change
   (REQ-EVT-F04-AC6).
6. THE fields `id`, `created_at`, `updated_at` SHALL be read-only; IF supplied in a
   POST/PUT/PATCH body THEN the event-service SHALL respond 422 `VALIDATION_ERROR`
   (`additionalProperties: false`).

---

## REQ-EVT-F12 — Formato uniforme degli errori

**User story:** As an API consumer, I want a consistent error shape, so that I can
parse failures uniformly.

**Acceptance criteria**

1. Every error response SHALL have the body
   `{"error": {"code": "UPPER_SNAKE", "message": "...", "details": {...}}}` conforming
   to the `Error` schema (`additionalProperties: false` on both `error` and its parent).
2. THE `code` SHALL be one of the codes used by this service: `VALIDATION_ERROR`,
   `REFERENCE_NOT_FOUND`, `INVALID_ORGANIZER`, `INVALID_STATUS_TRANSITION`,
   `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `MALFORMED_JSON`, `DEPENDENCY_UNAVAILABLE`.
3. THE HTTP status SHALL match the semantics: 400 malformed JSON, 404 not found,
   405 method not allowed, 422 validation/reference/business rule, 503 dependency
   unavailable.
4. WHEN `details` is not needed THE service MAY omit it or set it to an empty object;
   THE `error.code` and `error.message` SHALL always be present.

---

## REQ-EVT-F13 — Configurazione e variabili d'ambiente

**User story:** As an operator, I want all configuration to come from environment
variables read in one place, so that the service is portable and testable.

**Acceptance criteria**

1. THE event-service SHALL read `PORT` from the environment and SHALL listen on it;
   IF `PORT` is absent or not an integer THEN startup SHALL fail with an explicit error.
2. THE event-service SHALL read the user-service base URL from `USER_SERVICE_URL`,
   defaulting to `http://localhost:5001` when unset (REQ-EVT-B01).
3. THE event-service SHALL read `STORAGE_BACKEND` (default `memory`) and `DATA_DIR`
   (default `./data`) for persistence (REQ-EVT-F14).
4. ALL environment variables SHALL be read in a single module (`app/config.py`); no
   other module SHALL read `os.environ` directly, and no service URL SHALL be
   hard-coded in the code.
5. Importing the `app` package SHALL NOT require `PORT` to be set (so unit tests can
   import the app without environment configuration).

---

## REQ-EVT-F14 — Persistenza intercambiabile (memory / json / sqlite)

**User story:** As a platform, I want to switch the storage backend without touching
business logic, so that the same service runs in memory, on JSON files, or on SQLite.

**Acceptance criteria**

1. THE event-service SHALL support three backends selected by `STORAGE_BACKEND`:
   `memory` (default), `json`, `sqlite`, using only the Python standard library
   (`json`, `sqlite3`); no external DBMS SHALL be required.
2. WHEN `STORAGE_BACKEND=json` THE service SHALL persist events to a file under
   `DATA_DIR`, and the data SHALL survive a restart (reopening the same file returns
   previously stored events).
3. WHEN `STORAGE_BACKEND=sqlite` THE service SHALL persist events to a SQLite database
   under `DATA_DIR`, and the data SHALL survive a restart.
4. THE business logic (`service.py`) and the HTTP layer (`routes.py`) SHALL be
   identical across the three backends; switching backend SHALL require no change to
   business rules.
5. THE files produced by `json`/`sqlite` SHALL live under `DATA_DIR`, which is excluded
   from git.

---

## REQ-EVT-B01 — Esistenza dell'organizzatore

**User story:** As the platform, I want every event to reference an existing user as
its organizer, so that events cannot be attributed to non-existent accounts.

**Acceptance criteria**

1. WHEN an event is created (POST) or its `organizer_id` is set/changed (PUT/PATCH)
   THE event-service SHALL verify the organizer by calling the user-service
   `GET /api/v1/users/{organizer_id}`.
2. THE base URL of that call SHALL be taken from the `USER_SERVICE_URL` environment
   variable (default `http://localhost:5001`), and the request SHALL use a timeout of
   **2 seconds** (REQ-EVT-F13, platform standards).
3. IF the user-service responds 404 for the given `organizer_id` (reference absent)
   THEN the event-service SHALL respond 422 with error code `REFERENCE_NOT_FOUND`.
4. THE organizer verification SHALL run only after field-level validation has passed
   (REQ-EVT-F02-AC7), so a malformed request never triggers an outbound call.

*(Trace: IT-E02 — unknown `organizer_id` → 422 `REFERENCE_NOT_FOUND`.)*

---

## REQ-EVT-B02 — Ruolo dell'organizzatore

**User story:** As the platform, I want only users with the `organizer` role to own
events, so that role-based responsibilities are respected.

**Acceptance criteria**

1. WHEN the user-service returns the user referenced by `organizer_id` THE
   event-service SHALL check that the user's `role` equals `organizer`.
2. IF the referenced user exists but has a `role` different from `organizer`
   (e.g. `attendee` or `speaker`) THEN the event-service SHALL respond 422 with error
   code `INVALID_ORGANIZER`.
3. THE role check SHALL apply to POST, and to PUT/PATCH whenever `organizer_id` is set
   or changed.

*(Trace: IT-E03 — organizer with `role=attendee` → 422 `INVALID_ORGANIZER`.)*

---

## REQ-EVT-B03 — Coerenza delle date

**User story:** As an organizer, I want the system to reject events whose end date
precedes their start date, so that event durations are always valid.

**Acceptance criteria**

1. WHEN an event is created or updated THE event-service SHALL require `end_date` to be
   greater than or equal to `start_date`.
2. IF `end_date` is earlier than `start_date` THEN the event-service SHALL respond 422
   with error code `VALIDATION_ERROR`.
3. WHEN a PATCH changes only one of the two dates THE event-service SHALL evaluate the
   invariant using the resulting effective pair (the changed value plus the stored
   value of the other).
4. THE date-coherence check SHALL be performed as part of field-level validation,
   before any outbound organizer call.

*(Trace: IT-E04 — `end_date` < `start_date` → 422 `VALIDATION_ERROR`.)*

---

## REQ-EVT-B04 — Transizioni di stato

**User story:** As an organizer, I want the event lifecycle to follow allowed
transitions only, so that an event cannot move to an inconsistent state.

**Acceptance criteria**

1. THE allowed status transitions SHALL be exactly: `draft` → `published`,
   `draft` → `cancelled`, `published` → `cancelled`.
2. IF an update requests a transition not in the allowed set (e.g. `published` →
   `draft`, `cancelled` → `published`, `cancelled` → `draft`, `published` → `published`
   is treated per AC5, `draft` → `draft` per AC5) THEN the event-service SHALL respond
   422 with error code `INVALID_STATUS_TRANSITION`.
3. WHEN a new event is created THE initial `status` SHALL be `draft` unless a valid
   explicit value is supplied; a create with `status=cancelled` or `status=published`
   is a client-provided initial state, not a transition, and SHALL be accepted only if
   it is a valid initial value (`draft`, `published`, or `cancelled`) per the contract
   enum.
4. WHEN a PUT or PATCH sets `status` to a value different from the stored one THE
   event-service SHALL treat it as a transition and enforce AC1/AC2.
5. WHEN a PUT or PATCH results in `status` equal to the stored value (explicit same
   value) OR omits `status` entirely THE event-service SHALL treat the status as
   **unchanged**: this SHALL NOT be rejected as an invalid transition and SHALL leave
   `status` as stored. *(Explicit no-op handling of unchanged status.)*

*(Trace: IT-E05 — `draft` → `published` → 200; `published` → `draft` → 422
`INVALID_STATUS_TRANSITION`.)*

---

## REQ-EVT-B05 — Dipendenza non raggiungibile

**User story:** As the platform, I want a clear error when the user-service cannot be
reached, so that clients can distinguish an unavailable dependency from a validation
failure.

**Acceptance criteria**

1. WHEN the event-service calls the user-service to verify an organizer and the call
   **times out** (after the 2-second timeout) THE event-service SHALL respond 503 with
   error code `DEPENDENCY_UNAVAILABLE`.
2. WHEN the connection to the user-service is **refused** (dependency down / closed
   port) THE event-service SHALL respond 503 `DEPENDENCY_UNAVAILABLE`.
3. WHEN the user-service responds with a **5xx** status THE event-service SHALL respond
   503 `DEPENDENCY_UNAVAILABLE`.
4. THE 503 mapping SHALL apply to POST, PUT and PATCH whenever an organizer
   verification is required.
5. A user-service **404** SHALL NOT be treated as unavailability; it SHALL map to 422
   `REFERENCE_NOT_FOUND` (REQ-EVT-B01-AC3).

*(Trace: IT-E08 — user-service unreachable → 503 `DEPENDENCY_UNAVAILABLE`.)*

---

## REQ-EVT-B06 — Filtri lista per `status` e `city`

**User story:** As a client, I want to filter events by status and city, so that I can
find, for example, all published conferences in Rome.

**Acceptance criteria**

1. WHEN `status` is provided as a query parameter THE event-service SHALL return only
   events whose `status` equals the given value.
2. IF `status` is provided but is not one of `draft`, `published`, `cancelled` THEN the
   event-service SHALL respond 422 `VALIDATION_ERROR`.
3. WHEN `city` is provided as a query parameter THE event-service SHALL return only
   events whose `city` matches the given value.
4. WHEN both `status` and `city` are provided THE event-service SHALL combine them with
   AND logic.
5. THE `total` in the response SHALL reflect the filtered count before pagination
   (REQ-EVT-F06-AC5).

*(Trace: IT-E06 — filter by `status`, `city` and pagination.)*

---

## REQ-EVT-T01 — Test unitari, di contratto e tre backend

**User story:** As a maintainer, I want a thorough automated test suite, so that
regressions are caught before the acceptance suite runs.

**Acceptance criteria**

1. THE service SHALL have unit tests run with pytest that achieve coverage ≥ 80% on the
   `app` package (`py -3.12 -m pytest tests/unit --cov=app --cov-report=term-missing
   --cov-fail-under=80`).
2. ALL outbound HTTP calls to the user-service SHALL be mocked at the library level
   with `responses` in unit tests; no real network call SHALL leave the test process.
3. THE repository SHALL be tested against **all three** backends (`memory`, `json`,
   `sqlite`), using `tmp_path` for the `json` and `sqlite` file locations.
4. THE unit suite SHALL include at least **one contract test per operation** defined in
   the contract (`health`, `createEvent`, `listEvents`, `getEvent`, `replaceEvent`,
   `updateEvent`, `deleteEvent`) using
   `Exam/techconf-exam/contracts/validator.py::assert_matches_contract`.
5. THE unit suite SHALL cover the organizer-verification outcomes with mocked
   responses: organizer found + `organizer` role (success), user-service 404
   (→ 422 `REFERENCE_NOT_FOUND`), wrong role (→ 422 `INVALID_ORGANIZER`), timeout /
   connection error / 5xx (→ 503 `DEPENDENCY_UNAVAILABLE`).
6. Each test SHALL be traceable to a requirement via `@pytest.mark.req("REQ-EVT-…")`
   or by including the `REQ-EVT-…` id in the test name or docstring.

---

## REQ-EVT-T02 — Test di integrazione propri

**User story:** As a maintainer, I want my own integration tests that start the real
services, so that inter-service HTTP behaviour is verified end-to-end without mocks.

**Acceptance criteria**

1. THE event-service SHALL have its own integration tests (separate from the teacher's
   suite) that start the **real** event-service and its **real** user-service
   dependency as subprocesses on free ports, wait for `/health`, and terminate them in
   a `try/finally` block (with a `kill` fallback).
2. THE integration tests SHALL include at least **one positive case**: create an event
   with a valid `organizer` → 201 with `status="draft"`.
3. THE integration tests SHALL include at least **one non-existent reference case**:
   create an event with an `organizer_id` unknown to user-service → 422
   `REFERENCE_NOT_FOUND`.
4. THE integration tests SHALL include at least **one dead-dependency case**: start the
   event-service pointing `USER_SERVICE_URL` at a closed port and attempt a create →
   503 `DEPENDENCY_UNAVAILABLE`.
5. Each integration test SHALL be traceable to a requirement (marker, name, or
   docstring).

---

## Note di ambiguità e decisioni

- **Verifica organizzatore per PATCH senza `organizer_id`.** La verifica verso
  user-service avviene solo quando `organizer_id` è presente/cambia (REQ-EVT-F04-AC8,
  REQ-EVT-B01-AC1). Un PATCH che non tocca `organizer_id` non genera chiamate esterne,
  quindi non può produrre 422/503 legati all'organizzatore.
- **`status` invariato negli aggiornamenti.** Gestito esplicitamente in
  REQ-EVT-B04-AC5: uno `status` assente o uguale a quello memorizzato è un no-op e non
  viene classificato come transizione invalida. Questo evita falsi 422 su PUT
  sostitutivi che ripropongono lo stato corrente.
- **Ordine di validazione.** I controlli di campo (inclusa la coerenza delle date
  REQ-EVT-B03) precedono sempre la chiamata all'organizzatore (REQ-EVT-F02-AC7,
  REQ-EVT-B03-AC4), così un input malformato non provoca traffico HTTP inutile né
  errori 503 fuorvianti.
- **Distinzione 422 vs 503.** Un 404 dalla dipendenza è un problema di *riferimento*
  (422 `REFERENCE_NOT_FOUND`); timeout, connessione rifiutata e 5xx sono problemi di
  *disponibilità* (503 `DEPENDENCY_UNAVAILABLE`) — REQ-EVT-B05-AC5.
- **Formato date.** Le date sono stringhe `YYYY-MM-DD` (contratto `format: date`); il
  confronto `end_date` ≥ `start_date` è lessicografico sulla forma ISO, equivalente al
  confronto cronologico.
- **`price`.** Il contratto usa `type: number, minimum: 0`; la piattaforma richiede 2
  decimali impliciti (EUR). La rappresentazione numerica JSON è accettata; il vincolo
  di business è `price ≥ 0.00`.
