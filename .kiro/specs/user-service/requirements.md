# user-service — Requirements

**Contratto di riferimento:** `Exam/techconf-exam/contracts/openapi/user-service.yaml`
**Standard di piattaforma:** `.kiro/steering/platform-standards.md`
**Versione spec:** 1.0 — 2026-09-25

---

## Contesto e scopo

Il user-service è l'anagrafica centrale della piattaforma TechConf. Gestisce utenti
con tre ruoli (attendee, speaker, organizer) e rappresenta la fonte di verità per
l'identità: event-service, registration-service e notification-service lo interrogano
per validare riferimenti agli utenti. Il servizio non chiama nessun altro microservizio.

---

## Glossario locale

| Termine | Definizione |
|---|---|
| **Utente** | Risorsa identificata da UUID v4, con campi anagrafici e ruolo |
| **Email normalizzata** | Email convertita in minuscolo prima della persistenza e del confronto |
| **Risorsa read-only** | Campo generato dal server (`id`, `created_at`, `updated_at`) che non può essere impostato o modificato dal client |
| **PUT sostitutivo** | Sostituisce tutti i campi modificabili con i valori forniti, mantenendo `id` e `created_at` invariati |
| **PATCH parziale** | Aggiorna solo i campi presenti nel body; i campi assenti rimangono invariati |

---

## REQ-USR-F01 — Health check

**User story:** As an infrastructure operator, I want to check the health of the
user-service with a simple HTTP call, so that load balancers and the acceptance suite
can verify the service is up before routing traffic.

**Acceptance criteria**

1. WHEN a client sends `GET /health` THE user-service SHALL respond 200 with body
   `{"status": "ok", "service": "user-service"}`.
2. THE response body SHALL conform to the `Health` schema in the contract
   (`additionalProperties: false`, required fields `status` and `service`).
3. WHEN any other HTTP method is sent to `/health` THE user-service SHALL respond 405.
4. THE health endpoint SHALL respond regardless of storage backend state or data
   volume; no dependency on persistence is allowed in this handler.

---

## REQ-USR-F02 — Creazione utente (POST)

**User story:** As a platform administrator, I want to register new users by submitting
their profile data, so that they can participate in events as attendees, speakers, or
organizers.

**Acceptance criteria**

1. WHEN a client sends `POST /api/v1/users` with a valid JSON body containing
   `first_name`, `last_name`, and `email` THE user-service SHALL create the user
   and respond 201 with the created `User` object and an `Location` header set to
   `/api/v1/users/<id>`.
2. THE server SHALL generate a UUID v4 `id` for every new user; the client MUST NOT
   supply `id` in the request body.
3. THE server SHALL generate `created_at` and `updated_at` as identical ISO 8601 UTC
   timestamps at creation time; both fields are read-only and MUST NOT be accepted
   from the client.
4. IF the request body contains any field not defined in the `UserCreate` schema
   (`id`, `created_at`, `updated_at`, or any unknown key) THEN the user-service
   SHALL respond 422 `VALIDATION_ERROR`.
   *(Rationale: the contract declares `additionalProperties: false` on `UserCreate`.)*
5. WHEN `role` is omitted from the request body THE user-service SHALL default it to
   `"attendee"`.
6. WHEN `company` is omitted from the request body THE user-service SHALL set it to
   `null` in the stored record and in the response.
7. WHEN `company` is explicitly set to `null` in the request body THE user-service
   SHALL store and return `null`.
8. THE response body SHALL conform to the `User` schema in the contract (all required
   fields present, `additionalProperties: false`).

---

## REQ-USR-F03 — Validazione dei campi (POST e PUT)

**User story:** As a platform, I want input validated before persistence, so that
stored records are always consistent with business rules.

**Acceptance criteria**

1. IF `first_name` is absent or empty or longer than 50 characters THEN the
   user-service SHALL respond 422 `VALIDATION_ERROR`.
2. IF `last_name` is absent or empty or longer than 50 characters THEN the
   user-service SHALL respond 422 `VALIDATION_ERROR`.
3. IF `email` is absent or not a syntactically valid email address (see note on
   email format in the Ambiguity section) THEN the user-service SHALL respond 422
   `VALIDATION_ERROR`.
4. IF `company` is present and not `null` and longer than 100 characters THEN the
   user-service SHALL respond 422 `VALIDATION_ERROR`.
5. IF `role` is present and not one of `attendee`, `speaker`, `organizer` THEN the
   user-service SHALL respond 422 `VALIDATION_ERROR`.
6. WHEN multiple fields fail validation THE user-service SHALL still respond 422
   `VALIDATION_ERROR` (first failure is acceptable; exhaustive reporting is not
   required but recommended).
7. IF the request body is syntactically invalid JSON (not parseable) THEN the
   user-service SHALL respond 400 (not 422); the error body SHALL conform to the
   `Error` schema.
   *(Distinction: 400 = JSON syntax broken; 422 = JSON valid but structure/values wrong.)*
8. IF the `Content-Type` header is `application/json` but the body cannot be parsed
   as JSON THEN the user-service SHALL respond 400.
9. THE request body MUST be a JSON object (`{...}`); if the body is a JSON array,
   `null`, or a scalar value (string, number, boolean) THE user-service SHALL
   respond 422 `VALIDATION_ERROR`.
10. Each field MUST match the type declared in the `UserCreate` schema; implicit type
    coercions (e.g. integer `1` for a string field) SHALL NOT be performed. The only
    field that accepts `null` as a value is `company`.
    IF a field is present with the wrong type THEN the user-service SHALL respond 422
    `VALIDATION_ERROR`.

---

## REQ-USR-F04 — Validazione dei campi (PATCH)

**User story:** As a client, I want to send partial updates with only the fields I
wish to change, so that I do not have to re-supply unchanged data.

**Acceptance criteria**

1. WHEN a client sends `PATCH /api/v1/users/{id}` with a body containing only a
   subset of valid fields THE user-service SHALL update only those fields and leave
   all other fields unchanged.
2. IF a field present in the PATCH body fails its individual validation rule
   (length, format, enum) THEN the user-service SHALL respond 422 `VALIDATION_ERROR`
   and leave the resource unchanged.
3. IF the PATCH body contains any field not defined in the `UserUpdate` schema
   (`id`, `created_at`, `updated_at`, or any unknown key) THEN the user-service
   SHALL respond 422 `VALIDATION_ERROR`.
   *(The contract declares `additionalProperties: false` on `UserUpdate`.)*
4. WHEN a client sends a PATCH body with no fields (empty object `{}`) THE
   user-service SHALL respond 200 with the resource and its timestamps unchanged.
   *(An empty PATCH is idempotent: neither the data nor `updated_at` is modified.
   The contract does not specify this case; this is an explicit design choice.)*
5. IF the PATCH body is syntactically invalid JSON THEN the user-service SHALL
   respond 400.
   *(The contract does not list 400 for PATCH, but `platform-standards.md` mandates
   400 for malformed JSON on all endpoints. Platform standard takes precedence;
   the contract is not modified.)*
6. THE PATCH body MUST be a JSON object (`{...}`); if the body is a JSON array,
   `null`, or a scalar value THE user-service SHALL respond 422 `VALIDATION_ERROR`.
7. Each field in the PATCH body MUST match the type declared in the `UserUpdate`
   schema; the only field that accepts `null` is `company`. IF a field is present
   with the wrong type THEN the user-service SHALL respond 422 `VALIDATION_ERROR`.

---

## REQ-USR-B01 — Email univoca (case-insensitive)

**User story:** As a platform administrator, I want email addresses to be unique
regardless of capitalisation, so that the same person cannot register twice with
`Alice@Example.com` and `alice@example.com`.

**Acceptance criteria**

1. WHEN a `POST /api/v1/users` request is received AND an existing user already has
   the same email (compared case-insensitively) THE user-service SHALL respond 409
   with error code `EMAIL_ALREADY_EXISTS`.
2. WHEN a `PUT /api/v1/users/{id}` or `PATCH /api/v1/users/{id}` request supplies
   an `email` that is already used by a **different** user (compared
   case-insensitively) THE user-service SHALL respond 409 `EMAIL_ALREADY_EXISTS`.
3. WHEN a `PUT` or `PATCH` request supplies the **same** email that already belongs
   to the **user being updated** (same id) THE user-service SHALL NOT raise a
   conflict; it SHALL proceed normally.
   *(Updating your own email to the same value must not produce a 409.)*
4. THE 409 error body SHALL conform to the `Error` schema in the contract.

---

## REQ-USR-B02 — Email normalizzata in minuscolo

**User story:** As a platform, I want email addresses stored in lower case, so that
downstream services receive a consistent canonical form.

**Acceptance criteria**

1. WHEN a user is created THE user-service SHALL convert the `email` value to lower
   case before storing it and SHALL return the lower-case value in the response.
2. WHEN a user is updated via PUT or PATCH and a new `email` is supplied THE
   user-service SHALL convert it to lower case before storing and returning it.
3. THE lower-case conversion SHALL apply before the uniqueness check (REQ-USR-B01),
   so that `Alice@Example.com` and `alice@example.com` are detected as duplicates.

---

## REQ-USR-B03 — Filtri lista per role e email

**User story:** As a client, I want to filter the user list by role and/or email, so
that I can find specific users without fetching all records.

**Acceptance criteria**

1. WHEN `GET /api/v1/users?role=organizer` is requested THE user-service SHALL return
   only users whose `role` equals `organizer` in the `items` array.
2. WHEN `GET /api/v1/users?email=alice@example.com` is requested THE user-service
   SHALL return only users whose stored (lower-case) `email` matches the query value
   (case-insensitive comparison).
3. WHEN both `role` and `email` filters are supplied THE user-service SHALL apply
   both simultaneously (AND logic).
4. THE `total` field in the response SHALL reflect the count of records matching the
   applied filters, **before** pagination is applied.
5. IF `role` is supplied with a value that is not one of `attendee`, `speaker`,
   `organizer` THEN the user-service SHALL respond 422 `VALIDATION_ERROR`.

---

## REQ-USR-F05 — Lettura utente per ID (GET /{id})

**User story:** As a client or a downstream service, I want to retrieve a single user
by their UUID, so that I can display their profile or validate a reference.

**Acceptance criteria**

1. WHEN `GET /api/v1/users/{id}` is requested and the user exists THE user-service
   SHALL respond 200 with the `User` object conforming to the contract schema.
2. IF the user with the given `id` does not exist THEN the user-service SHALL respond
   404 with error code `NOT_FOUND`.
3. THE `{id}` parameter is treated as a UUID string; if it is syntactically valid
   UUID but not found, the response is 404. The service SHOULD NOT return 422 for
   a syntactically invalid UUID path parameter — 404 is acceptable.
   *(Rationale: the contract only defines 404 for this operation, not 422.)*

---

## REQ-USR-F06 — Lista paginata (GET /)

**User story:** As a client, I want to retrieve users in pages, so that I can display
large datasets without loading all records at once.

**Acceptance criteria**

1. WHEN `GET /api/v1/users` is requested without pagination parameters THE
   user-service SHALL default to `page=1` and `page_size=20`.
2. WHEN `page` and `page_size` are supplied THE user-service SHALL return the
   corresponding slice of the (filtered) result set.
3. THE response SHALL always include `{"items": [...], "page": <int>, "page_size":
   <int>, "total": <int>}` conforming to the `UserPage` schema.
4. IF `page_size` exceeds 100 THEN the user-service SHALL respond 422
   `VALIDATION_ERROR`.
5. IF `page` is less than 1 or `page_size` is less than 1 THEN the user-service
   SHALL respond 422 `VALIDATION_ERROR`.
6. IF `page` or `page_size` is supplied as an empty string, a non-numeric value, or
   a non-integer (e.g. `1.5`) THEN the user-service SHALL respond 422
   `VALIDATION_ERROR`.
7. WHEN the requested page is beyond the last page THE user-service SHALL return an
   empty `items` array with the correct `total` and the requested `page`/`page_size`
   values.
7. THE `total` field SHALL count matching records after filters are applied and before
   pagination is applied (see REQ-USR-B03-AC4).

---

## REQ-USR-F07 — Sostituzione utente (PUT /{id})

**User story:** As an administrator, I want to replace a user's entire profile in a
single call, so that I can update all fields atomically.

**Acceptance criteria**

1. WHEN `PUT /api/v1/users/{id}` is requested with a valid body and the user exists
   THE user-service SHALL replace all mutable fields and respond 200 with the updated
   `User` object.
2. PUT uses the `UserCreate` schema: `first_name`, `last_name`, `email` are required;
   `company` and `role` are optional with the same defaults as POST.
3. IF the user with the given `id` does not exist THEN the user-service SHALL respond
   404 `NOT_FOUND`.
4. IF the request body contains any field not defined in the `UserCreate` schema
   (`id`, `created_at`, `updated_at`, or any unknown key) THEN the user-service
   SHALL respond 422 `VALIDATION_ERROR` (same rule as REQ-USR-F03-AC9 and AC10:
   body must be an object, extra fields rejected).
5. THE `created_at` field SHALL remain unchanged after a PUT; only `updated_at` SHALL
   be refreshed (see REQ-USR-F11).
6. Validation rules from REQ-USR-F03 and email rules from REQ-USR-B01/B02 apply to
   PUT in the same way as to POST.

---

## REQ-USR-F08 — Aggiornamento parziale (PATCH /{id})

**User story:** As an administrator, I want to update one or more fields of a user
profile without re-sending unchanged data, so that partial updates are safe and
idempotent.

**Acceptance criteria**

1. WHEN `PATCH /api/v1/users/{id}` is requested with a valid partial body and the
   user exists THE user-service SHALL update only the provided fields and respond
   200 with the full updated `User` object.
2. IF the user with the given `id` does not exist THEN the user-service SHALL respond
   404 `NOT_FOUND`.
3. Fields absent from the PATCH body SHALL retain their current values.
4. `company` may be patched to `null` explicitly; this SHALL clear the company value.
5. Validation rules from REQ-USR-F04 and email rules from REQ-USR-B01/B02 apply.
6. IF the PATCH body is `{}` (empty object) THE user-service SHALL respond 200 with
   the unchanged resource (see REQ-USR-F04-AC4).

---

## REQ-USR-F09 — Cancellazione utente (DELETE /{id})

**User story:** As an administrator, I want to remove a user from the registry, so
that their data is no longer accessible.

**Acceptance criteria**

1. WHEN `DELETE /api/v1/users/{id}` is requested and the user exists THE user-service
   SHALL delete the user and respond 204 with no body.
2. IF the user with the given `id` does not exist THEN the user-service SHALL respond
   404 `NOT_FOUND`.
3. AFTER a successful DELETE, a subsequent `GET /api/v1/users/{id}` for the same id
   SHALL return 404.
4. THE DELETE operation SHALL be idempotent in the sense that a second DELETE on the
   same id after the first succeeds SHALL return 404 (not 204 again).

---

## REQ-USR-F10 — Metodi HTTP non consentiti e percorsi sconosciuti

**User story:** As a client, I want clear feedback when I use an unsupported HTTP
method or an unknown path, so that I can distinguish between "path doesn't exist"
and "method not allowed on this path".

**Acceptance criteria**

1. WHEN an HTTP method not defined in the contract is used on a path that IS defined
   (e.g. `POST /api/v1/users/{id}`, `DELETE /api/v1/users`, `PUT /health`) THE
   user-service SHALL respond 405 with a JSON error body.
2. WHEN a request is made to a path that is NOT defined in the contract THE
   user-service SHALL respond 404 with a JSON error body.
   *(Example: `GET /api/v1/unknown` → 404; `DELETE /api/v1/users` → 405.)*
3. THE 405 and 404 error bodies SHALL conform to the `Error` schema
   (`{"error": {"code": "...", "message": "...", "details": {}}}`).
   The JSON error body is **mandatory** (SHALL), not optional.
   *(Flask emits 404/405 automatically; the requirement is met by registering
   error handlers that produce the standard `Error` format.)*

---

## REQ-USR-F11 — Immutabilità di created_at e aggiornamento di updated_at

**User story:** As a client, I want timestamps to accurately reflect when a record
was created and last modified, so that I can audit changes.

**Acceptance criteria**

1. WHEN a user is created `created_at` and `updated_at` SHALL be set to the same
   server-generated UTC timestamp.
2. WHEN a user is modified via PUT or PATCH with at least one field change
   `updated_at` SHALL be refreshed to the current UTC timestamp.
   WHEN a PATCH body is empty (`{}`) neither the resource nor `updated_at` SHALL
   be modified (see REQ-USR-F04-AC4).
3. `created_at` SHALL never change after creation, regardless of the number of
   updates.
4. WHEN a request fails validation or produces any error response THE timestamps of
   the stored record SHALL remain unchanged (no partial mutation on error).
5. Timestamps SHALL be formatted as ISO 8601 UTC strings ending in `Z`
   (e.g. `2026-10-15T09:30:00Z`).

---

## REQ-USR-F12 — Formato degli errori

**User story:** As a client, I want all error responses to have a uniform JSON
structure, so that I can handle them programmatically without inspecting the HTTP
status code alone.

**Acceptance criteria**

1. ALL error responses (400, 404, 405, 409, 422) SHALL have a JSON body conforming
   to the `Error` schema: `{"error": {"code": "UPPER_SNAKE", "message": "...",
   "details": {}}}`.
2. THE `code` field SHALL always be an UPPER_SNAKE_CASE string identifying the error
   type (e.g. `VALIDATION_ERROR`, `NOT_FOUND`, `EMAIL_ALREADY_EXISTS`).
3. THE `details` field SHALL always be present as a JSON object (`{}`); it SHALL NOT
   be `null` or omitted. When no additional context is available, return `{}`.
4. No successful (2xx) response SHALL contain an `error` key.
5. THE Content-Type of all JSON responses (success and error) SHALL be
   `application/json`. The exception is DELETE 204, which SHALL have no response
   body and no Content-Type constraint.
6. THE 204 response to DELETE SHALL have an empty body; no JSON is returned.

---

## REQ-USR-F13 — Configurazione e variabili d'ambiente

**User story:** As a platform operator, I want to configure the service with
environment variables, so that the same code can run in different environments
without modification.

**Acceptance criteria**

1. THE user-service SHALL read `PORT` from the environment; if absent it SHALL log
   an error and exit with a non-zero code.
2. THE user-service SHALL listen on `0.0.0.0:<PORT>` as declared by the `PORT`
   variable.
3. THE user-service SHALL read `STORAGE_BACKEND` from the environment; if absent it
   SHALL default to `memory`.
4. IF `STORAGE_BACKEND` is `json` or `sqlite` THE user-service SHALL read `DATA_DIR`
   (default `./data`) and store persistence files there.
5. ALL environment variables SHALL be read exclusively in `app/config.py`; no other
   module may call `os.environ` directly.
6. `__main__.py` SHALL read `PORT` via `config.PORT` (not directly from `os.environ`).

---

## REQ-USR-F14 — Persistenza intercambiabile (memory / json / sqlite)

**User story:** As a developer, I want to switch the storage backend with an
environment variable, so that I can run the service in memory for tests and on disk
for integration or production scenarios.

**Acceptance criteria**

1. WHEN `STORAGE_BACKEND=memory` the user-service SHALL store data in process memory;
   data SHALL be lost on restart.
2. WHEN `STORAGE_BACKEND=json` the user-service SHALL persist data to a JSON file in
   `DATA_DIR`; data SHALL survive a restart.
3. WHEN `STORAGE_BACKEND=sqlite` the user-service SHALL persist data to a SQLite
   database file in `DATA_DIR` using only the stdlib `sqlite3` module; data SHALL
   survive a restart.
4. THE business logic in `service.py` SHALL NOT import any backend module directly;
   it SHALL receive the repository via dependency injection.
5. A change of `STORAGE_BACKEND` SHALL NOT require any modification to `service.py`
   or `routes.py`.

---

## REQ-USR-T01 — Test coverage e qualità

**User story:** As a project maintainer, I want automated tests that cover all
requirements at 80 % or more, so that regressions are caught before merging.

**Acceptance criteria**

1. THE unit test suite SHALL achieve at least 80 % statement coverage of the `app/`
   package, measured with `pytest --cov=app`.
2. THE repository test module SHALL exercise all three backends (memory, json, sqlite)
   using `tmp_path` for file-based backends; each CRUD operation SHALL be tested
   with each backend.
3. FOR EACH HTTP operation defined in the contract (POST, GET list, GET by id, PUT,
   PATCH, DELETE, GET /health) THERE SHALL be at least one test that calls
   `assert_matches_contract("user", method, path, response)` from
   `contracts/validator.py`.
4. EACH test function or its docstring SHALL reference the requirement it verifies
   using the pattern `REQ-USR-<ID>` (e.g. `@pytest.mark.req("REQ-USR-B01")` or
   in the function name).
5. THE user-service has no external HTTP dependencies; the `responses` library is
   therefore not needed in unit tests. All HTTP interactions are tested through the
   Flask test client, which invokes the application in-process without network calls.
6. THE integration test for user-service SHALL start a real process on a free port,
   wait for `/health`, run positive and negative cases, then terminate the process.

---

## Matrice endpoint → requisiti

| Endpoint | Metodo | Requisiti |
|---|---|---|
| `/health` | GET | REQ-USR-F01 |
| `/api/v1/users` | POST | REQ-USR-F02, REQ-USR-F03, REQ-USR-B01, REQ-USR-B02, REQ-USR-F11, REQ-USR-F12 |
| `/api/v1/users` | GET | REQ-USR-F06, REQ-USR-B03, REQ-USR-F12 |
| `/api/v1/users/{id}` | GET | REQ-USR-F05, REQ-USR-F12 |
| `/api/v1/users/{id}` | PUT | REQ-USR-F07, REQ-USR-F03, REQ-USR-B01, REQ-USR-B02, REQ-USR-F11, REQ-USR-F12 |
| `/api/v1/users/{id}` | PATCH | REQ-USR-F08, REQ-USR-F04, REQ-USR-B01, REQ-USR-B02, REQ-USR-F11, REQ-USR-F12 |
| `/api/v1/users/{id}` | DELETE | REQ-USR-F09, REQ-USR-F12 |
| Qualsiasi path | Metodo non consentito | REQ-USR-F10, REQ-USR-F12 |
| Path sconosciuto | qualsiasi metodo | REQ-USR-F10, REQ-USR-F12 |
| Tutti gli endpoint | — | REQ-USR-F13, REQ-USR-F14 |

---

## Matrice test di collaudo → requisiti

| Test suite | ID test | Requisiti coperti |
|---|---|---|
| IT-U01 | POST valido → 201, Location, contratto | REQ-USR-F02, REQ-USR-B02, REQ-USR-F11 |
| IT-U02 | Campo obbligatorio mancante → 422 | REQ-USR-F03 |
| IT-U03 | Email duplicata maiuscole/minuscole → 409 | REQ-USR-B01, REQ-USR-B02 |
| IT-U04 | GET per id → 200; id inesistente → 404 | REQ-USR-F05 |
| IT-U05 | Lista paginata, filtro role | REQ-USR-F06, REQ-USR-B03 |
| IT-U06 | PUT e PATCH → 200, updated_at aggiornato | REQ-USR-F07, REQ-USR-F08, REQ-USR-F11 |
| IT-U07 | DELETE → 204, poi GET → 404 | REQ-USR-F09 |
| IT-U08 | JSON malformato → 400, GET /health → 200 | REQ-USR-F01, REQ-USR-F03 (AC7) |

---

## Note su ambiguità e scelte esplicite

| ID | Ambiguità / Scelta |
|---|---|
| REQ-USR-F04-AC4 | Un PATCH vuoto `{}` è valido (200, risorsa e timestamp invariati). Scelta: `updated_at` NON viene aggiornato per preservare l'idempotenza. Il contratto non specifica questo caso. |
| REQ-USR-F02/F07-extra-fields | La validazione di campi extra (id, created_at, updated_at) in input produce 422, per effetto di `additionalProperties: false` nel contratto su `UserCreate`. Documentato in REQ-USR-F03-AC9/AC10 e REQ-USR-F07-AC4. |
| REQ-USR-F05-AC3 | UUID sintatticamente invalido nel path: il contratto non dichiara 422 per GET/{id}, quindi si risponde 404. |
| REQ-USR-F10-AC3 | Flask restituisce 404/405 automaticamente; il requisito è soddisfatto registrando error handler Flask che producono il formato `Error` standard con `details: {}`. |
| REQ-USR-F14 | user-service non ha dipendenze HTTP esterne; `http_client.py` non è necessario e non viene creato per questo servizio. |
| REQ-USR-F04-AC5 / PATCH 400 | Il contratto non elenca 400 come risposta di PATCH. La regola di piattaforma (`platform-standards.md`) stabilisce 400 per JSON malformato su tutti gli endpoint. La regola di piattaforma prevale; il contratto non è modificato. |
| REQ-USR-F03-AC3 / email format | Il contratto dichiara `format: email` (OpenAPI 3.0). Questa spec non richiede un validatore completo RFC 5322 (che ammette molti formati esotici). La strategia di validazione scelta (regex minima o libreria standard) è documentata in `design.md`. Il requisito si allinea al `format: email` del contratto: un'email accettabile deve avere la forma `local@domain.tld`; la precisione esatta è una decisione di design. |
