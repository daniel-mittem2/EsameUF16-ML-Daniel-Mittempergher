# event-service — Tasks

**Spec:** `.kiro/specs/event-service/`
**Contratto:** `Exam/techconf-exam/contracts/openapi/event-service.yaml`
**Commit format per task:** `feat(event): <descrizione> [T-XX]`
**Commit format per test:** `test(event): <descrizione> [T-XX]`
**Commit format per docs:** `docs(event): <descrizione> [T-XX]`

Eseguire i task tramite **Start task**, uno alla volta, nell'ordine sotto riportato.
Gli ID T-XX restano stabili anche quando l'ordine non è numerico. Ogni task deve essere
verificato e committato separatamente prima di iniziare il successivo. Spuntare il task
principale solo dopo tutte le verifiche; i sottopunti descrivono il lavoro, non sono
task indipendenti. Ogni task è verificabile senza implementare i task successivi.

**Prerequisito:** user-service completo e avviabile (event-service lo chiama per validare
l'organizzatore, REQ-EVT-B01). Non è richiesto modificarlo.

**Ordine:** T-01 → T-02 → T-04 → T-05 → T-06 → T-07 → T-08 → T-03 → T-09 → T-10 → T-11 → T-12 → T-13 → T-14 → T-15 → T-16 → T-17 → T-18.

---

- [x] 1. T-01 — Scaffold struttura directory e package

  - Creare `Exam/techconf-exam/services/event-service/`
  - Creare `app/__init__.py` (docstring), `app/__main__.py` (stub)
  - Creare file vuoti: `app/config.py`, `app/routes.py`, `app/service.py`,
    `app/repository.py`, `app/http_client.py`, `app/validators.py`, `app/errors.py`,
    `app/pagination.py`, `app/models.py`
  - Creare `app/backends/__init__.py`, `memory.py`, `json_backend.py`, `sqlite_backend.py`
  - Creare `requirements.txt` (`flask`, `requests`) e `requirements-dev.txt`
    (`-r requirements.txt`, `-r ../../tests/integration/requirements.txt`, `pytest`,
    `pytest-cov`, `responses`)
  - Installare le dipendenze: `py -3.12 -m pip install -r requirements-dev.txt`;
    verificare import di flask, requests, pytest, responses, yaml, jsonschema
  - Creare `tests/unit/` e `tests/integration/` con `__init__.py`
  - **Completamento:** `py -3.12 -c "import app"` dalla directory del servizio senza
    errori e senza richiedere `PORT`

  _Requirements: REQ-EVT-F13, REQ-EVT-F14_
  _Commit: `feat(event): scaffold package structure [T-01]`_

- [x] 2. T-02 — Configurazione (`config.py`)

  - Implementare il dataclass `Config` con `port: int`, `storage_backend: str`,
    `data_dir: Path`, `user_service_url: str`
  - Implementare `load_config(port=_SENTINEL) -> Config`: `PORT` da env (ValueError se
    assente/non intero), `STORAGE_BACKEND` default `memory`, `DATA_DIR` default `./data`,
    `USER_SERVICE_URL` default `http://localhost:5001`
  - **Completamento:** `from app import config` senza `PORT`; `load_config()` senza PORT
    → `ValueError`; `load_config(port=5002)` senza env funziona; default URL corretto

  _Requirements: REQ-EVT-F13_
  _Commit: `feat(event): config factory and Config dataclass [T-02]`_

- [x] 3. T-04 — Moduli di supporto (`errors`, `pagination`, `models`, `validators`)

  - `errors.py`: costanti (`VALIDATION_ERROR`, `REFERENCE_NOT_FOUND`,
    `INVALID_ORGANIZER`, `INVALID_STATUS_TRANSITION`, `NOT_FOUND`, `METHOD_NOT_ALLOWED`,
    `MALFORMED_JSON`, `DEPENDENCY_UNAVAILABLE`) e `make_error_response(code, message,
    details=None, status=None)` con `details` sempre dict
  - `models.py`: `new_event_record(data, now)` (default `status="draft"`,
    `description=None`, UUID v4), `event_to_dict(record)` (13 campi del contratto),
    `utcnow_iso()` con precisione al microsecondo e suffisso `Z`
  - `pagination.py`: `parse_pagination_params(args)` (422 su vuoto/non numerico/non
    intero/fuori range, page≥1, page_size 1..100), `paginate(items, page, page_size)`
    con `total` pre-slice
  - `validators.py`: `validate_body_is_object`, `validate_event_create` (required, tipi
    senza coercizione, `title` 3–120, `venue`≤100, `city`≤60, `capacity` int 1–10000,
    `price`≥0, `description`≤2000 nullable, `status` enum, `organizer_id` uuid),
    `validate_event_update` (tutti opzionali, `additionalProperties:false`),
    `validate_date`, `validate_dates_coherent`
  - **Completamento:** test unitari dei moduli (inclusi in questo task) verdi

  _Requirements: REQ-EVT-F03, REQ-EVT-F04, REQ-EVT-F06, REQ-EVT-F11, REQ-EVT-F12, REQ-EVT-B03_
  _Commit: `feat(event): errors, pagination, models, validators modules [T-04]`_

- [x] 4. T-05 — Repository: interfaccia astratta e backend memory

  - Definire `AbstractEventRepository(ABC)` in `repository.py` con `create`, `get`,
    `list_all(filters)`, `update`, `delete`
  - Implementare `MemoryEventRepository` con `threading.RLock()` per istanza; sequenze
    read-modify-write sotto lock
  - Implementare `get_repository(backend, data_dir)` (import locali); in T-05 solo il
    ramo `memory`, rami json/sqlite in T-06/T-07
  - `list_all` applica i filtri `status` e `city` (AND)
  - **Completamento:** test memory (create/get/list con filtri/update/delete) verdi

  _Requirements: REQ-EVT-F14, REQ-EVT-B06_
  _Commit: `feat(event): repository ABC and MemoryEventRepository [T-05]`_

- [x] 5. T-06 — Backend JSON

  - Implementare `JsonEventRepository`: legge `events.json` all'apertura (lista vuota se
    assente), scrittura atomica (tmp + `os.replace()`), `RLock` per istanza, filtri in
    `list_all`
  - **Completamento:** persistenza verificata riaprendo il file su nuova istanza
    (dati presenti); nessun file `.tmp` residuo

  _Requirements: REQ-EVT-F14_
  _Commit: `feat(event): JsonEventRepository with atomic writes and RLock [T-06]`_

- [x] 6. T-07 — Backend SQLite

  - Implementare `SqliteEventRepository`: `CREATE TABLE IF NOT EXISTS events (...)`,
    connessione condivisa `check_same_thread=False`, `RLock` per istanza, ogni write in
    `with conn:`, filtri in `list_all`
  - **Completamento:** persistenza su riapertura verificata; `events.db` in `DATA_DIR`
    (escluso da git via `data/`)

  _Requirements: REQ-EVT-F14_
  _Commit: `feat(event): SqliteEventRepository with shared connection and RLock [T-07]`_

- [x] 7. T-08 — Client HTTP verso user-service (`http_client.py`)

  - Implementare `UserServiceClient(base_url, timeout=2.0)` con `get_user(id)` e
    `verify_organizer(id)`
  - Definire eccezioni `ReferenceNotFoundError`, `InvalidOrganizerError`,
    `DependencyUnavailableError`
  - Mappatura: `requests` timeout 2s; 404 → `ReferenceNotFoundError`; `role≠organizer`
    → `InvalidOrganizerError`; `Timeout`/`ConnectionError`/5xx/status inatteso →
    `DependencyUnavailableError`
  - **Completamento:** test con `responses` per ogni ramo (200+organizer, 200+ruolo
    errato, 404, 5xx, ConnectionError/Timeout) verdi; nessuna richiesta reale in rete

  _Requirements: REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B05, REQ-EVT-F13_
  _Commit: `feat(event): UserServiceClient with 2s timeout and error mapping [T-08]`_

- [x] 8. T-03 — Health endpoint e application factory

  - Implementare `create_app(repo=None, config=None, user_client=None) -> Flask` in
    `app/__init__.py`
  - Registrare `GET /health` → `{"status": "ok", "service": "event-service"}`
  - Registrare error handler 400/404/405 → formato `Error` con `details: {}`
  - Implementare `__main__.py`: `load_config()` → `create_app(config=cfg)` →
    `app.run(host="0.0.0.0", port=cfg.port)` (`# pragma: no cover` sull'entrypoint)
  - **Completamento:** `GET /health` → 200 body esatto conforme al contratto; `POST
    /health` → 405 con corpo JSON. Registrare il Blueprint completo in T-12.

  _Requirements: REQ-EVT-F01, REQ-EVT-F10, REQ-EVT-F12, REQ-EVT-F13_
  _Commit: `feat(event): health endpoint and app factory [T-03]`_

- [x] 9. T-09 — EventService: create e regole B01/B02/B03/B05

  - Implementare `EventService.__init__(self, repo, user_client)`
  - `create_event(data)`: validazione già passata a monte; `verify_organizer` (B01/B02),
    mappa `ReferenceNotFoundError`→422, `InvalidOrganizerError`→422,
    `DependencyUnavailableError`→503 (B05); default `status="draft"`; genera UUID e
    timestamp; `repo.create`
  - La coerenza date (B03) è verificata prima della chiamata all'organizzatore
    (nessuna chiamata HTTP se il campo è invalido)
  - **Completamento:** test service con repo memory + `responses`: successo,
    REFERENCE_NOT_FOUND, INVALID_ORGANIZER, DEPENDENCY_UNAVAILABLE, end<start→422

  _Requirements: REQ-EVT-F02, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B03, REQ-EVT-B05, REQ-EVT-F11_
  _Commit: `feat(event): EventService.create_event with organizer verification [T-09]`_

- [x] 10. T-10 — EventService: get, list e filtri B06

  - `get_event(id)` (404 se assente, nessuna chiamata HTTP)
  - `list_events(filters, page, page_size)`: filtri `status`/`city` AND (B06), `total`
    post-filtro pre-paginazione
  - **Completamento:** test filtri combinati, `total` corretto, `status` invalido→422,
    pagina oltre l'ultima → items vuoti

  _Requirements: REQ-EVT-F05, REQ-EVT-F06, REQ-EVT-B06_
  _Commit: `feat(event): EventService.get_event and list_events with filters [T-10]`_

- [x] 11. T-11 — EventService: replace (PUT), update (PATCH) e transizioni B04

  - `replace_event(id, data)` (PUT): 404 se assente; verifica organizzatore se
    `organizer_id` presente; transizione stato vs stored (B04); mantiene
    `id`/`created_at`, aggiorna `updated_at`; default POST-style per opzionali assenti
  - `update_event(id, data)` (PATCH): recupera **per primo** (404 anche per `{}`);
    rifiuta campi sconosciuti; empty PATCH → invariato, `updated_at` non aggiornato;
    ri-valida `end_date≥start_date` sull'effettivo (B03); ri-verifica organizzatore se
    `organizer_id` cambia; enforce transizione (B04)
  - `check_transition(current, new)`: ammesse `draft→published`, `draft→cancelled`,
    `published→cancelled`; `new==current` o `status` assente → no-op (stato invariato);
    altrimenti `INVALID_STATUS_TRANSITION`→422
  - **Completamento:** test PUT/PATCH, empty PATCH invariato, `draft→published` ok,
    `published→draft`→422, stato invariato accettato, `created_at` immutato, `updated_at`
    aggiornato (monkeypatch orologio)

  _Requirements: REQ-EVT-F07, REQ-EVT-F08, REQ-EVT-B03, REQ-EVT-B04, REQ-EVT-F11_
  _Commit: `feat(event): EventService.replace_event, update_event and status transitions [T-11]`_

- [x] 12. T-12 — Routes HTTP complete

  - Implementare tutte le rotte in `routes.py` come Blueprint:
    `POST /api/v1/events` (201 + `Location`), `GET /api/v1/events` (paginato+filtri),
    `GET /api/v1/events/<id>`, `PUT /api/v1/events/<id>`, `PATCH /api/v1/events/<id>`,
    `DELETE /api/v1/events/<id>` (204 senza body)
  - Validare il body con `validators.py` per POST/PUT/PATCH; tradurre le eccezioni del
    service in status code via `errors.py` (422/404/503)
  - **Completamento:** verifiche via Flask test client (user-service mockato con
    `responses`): `page_size=101`→422, `page=abc`→422, body `[]`→422, tipo errato→422,
    DELETE→204 senza Content-Type JSON, `POST /events/<id>`→405, PUT su id inesistente→404

  _Requirements: REQ-EVT-F02..F12_
  _Commit: `feat(event): all HTTP routes in Blueprint [T-12]`_

- [x] 13. T-13 — Test unitari completi (`tests/unit/`)

  - `test_routes.py`: Flask test client per ogni endpoint (400/404/405/422/503); mock
    user-service con `responses`; test di contratto con `flask_to_contract_dict`
  - `test_service.py`: ogni metodo `EventService` con `MemoryEventRepository` +
    `responses`; monkeypatch su `utcnow_iso`; no-mutazione in caso di errore
  - `test_repository.py`: parametrizzato sui **tre** backend con `tmp_path`; create, get,
    list_all con filtri, update, delete; riapertura dati json/sqlite
  - `test_http_client.py`: `UserServiceClient` con `responses` per tutti i rami
  - `test_contracts.py`: una `assert_matches_contract` per ciascuna delle 7 operazioni
    (`health`, `createEvent`, `listEvents`, `getEvent`, `replaceEvent`, `updateEvent`,
    `deleteEvent`)
  - `test_config.py`: `load_config()` senza PORT → ValueError; default; import senza PORT
  - Eseguire `py -3.12 -m pytest tests/unit -v --cov=app --cov-report=term-missing
    --cov-fail-under=80` → coverage ≥ 80%
  - Ogni test contiene `REQ-EVT-<ID>` nel nome o docstring (o `@pytest.mark.req`)
  - **Completamento:** suite unit verde e coverage ≥ 80%

  _Requirements: REQ-EVT-T01_
  _Commit: `test(event): full unit test suite with >=80% coverage [T-13]`_

- [x] 14. T-14 — Aggiornamento `services.yaml` (user + event)

  - Aggiornare `Exam/techconf-exam/services.yaml` dichiarando `user` **ed** `event`:
    ```yaml
    services:
      user:
        cwd: services/user-service
        command: py -3.12 -m app
        health_path: /health
      event:
        cwd: services/event-service
        command: py -3.12 -m app
        health_path: /health
    ```
  - **Completamento:** avvio manuale `$env:PORT="5002"; $env:USER_SERVICE_URL="http://localhost:5001"; py -3.12 -m app` → `/health` risponde; `py -3.12 -m pytest tests/unit -v` verde

  _Requirements: REQ-EVT-F13, REQ-EVT-F14_
  _Commit: `feat(event): declare event in services.yaml [T-14]`_

- [x] 15. T-15 — Test di integrazione propri (`tests/integration/`)

  - Implementare `test_event_integration.py` con fixture che avvia **user-service** ed
    **event-service** reali come sottoprocessi su porte libere (`STORAGE_BACKEND=memory`),
    inietta `USER_SERVICE_URL` dell'event verso lo user reale, attende `/health`,
    `try/finally` con `terminate()` + `kill()` di fallback
  - Caso positivo: crea organizer nel user reale → crea evento → 201, `status="draft"`
  - Caso riferimento inesistente: `organizer_id` uuid casuale → 422 `REFERENCE_NOT_FOUND`
  - Caso dipendenza spenta: event con `USER_SERVICE_URL` su porta chiusa → POST → 503
    `DEPENDENCY_UNAVAILABLE`
  - **Completamento:** `py -3.12 -m pytest tests/integration -v` → tutti verdi

  _Requirements: REQ-EVT-T02_
  _Commit: `test(event): own integration tests with real user+event services [T-15]`_

- [x] 16. T-16 — Collaudo con suite del docente (event) e verifica checksum

  - Eseguire dalla root `Exam/techconf-exam/`:
    `py -3.12 -m pytest tests/integration -k event -v` (IT-E01..IT-E08)
  - Verificare che i test IT-E01..IT-E08 passino (user ed event dichiarati in
    services.yaml)
  - Verificare i checksum: nessun file protetto (`contracts/`, `tests/integration/`,
    `CHECKSUMS.sha256`) modificato
  - Se un test fallisce: aprire issue GitHub, classificare (impl vs spec) e seguire il
    workflow §6.4/§6.5 di Exam.MD **prima** di procedere
  - **Completamento:** IT-E01..IT-E08 verdi; checksum invariati

  _Requirements: REQ-EVT-B01..B06, REQ-EVT-F01..F14_
  _Commit: `docs(event): acceptance run notes for event suite [T-16]`_

- [x] 17. T-17 — `README.md` del servizio

  - Creare `services/event-service/README.md`: installazione dipendenze; avvio (env
    `PORT`, `USER_SERVICE_URL`, `STORAGE_BACKEND`, `DATA_DIR`; tre backend); test unit
    con coverage; test di integrazione propri; suite del docente (`-k event`);
    riferimento a `REQ-EVT-*` e `T-01..T-18`
  - **Completamento:** comandi del README eseguibili e coerenti con `py -3.12`

  _Requirements: REQ-EVT-T01_
  _Commit: `docs(event): service README with setup and test commands [T-17]`_

- [x] 18. T-18 — Verifica finale di coerenza event-service

  - Rieseguire unit (`--cov-fail-under=80`) e integrazione propri; confermare verdi
  - Confermare che il collaudo `-k event` resta verde con user+event in services.yaml
  - Verificare che nessun URL sia hard-coded (solo `config.py` legge env) e nessun import
    applicativo da user-service
  - **Completamento:** tutte le verifiche verdi; pronto per iniziare registration-service

  _Requirements: REQ-EVT-T01, REQ-EVT-T02, REQ-EVT-F13_
  _Commit: `docs(event): final consistency check [T-18]`_

---

## Copertura requisiti → task

| Requisito | Task |
|---|---|
| REQ-EVT-F01 | T-03 |
| REQ-EVT-F02 | T-09, T-12 |
| REQ-EVT-F03 | T-04, T-12 |
| REQ-EVT-F04 | T-04, T-11, T-12 |
| REQ-EVT-F05 | T-10, T-12 |
| REQ-EVT-F06 | T-04, T-10, T-12 |
| REQ-EVT-F07 | T-11, T-12 |
| REQ-EVT-F08 | T-11, T-12 |
| REQ-EVT-F09 | T-12 |
| REQ-EVT-F10 | T-03, T-12 |
| REQ-EVT-F11 | T-04, T-09, T-11 |
| REQ-EVT-F12 | T-04, T-12 |
| REQ-EVT-F13 | T-02, T-08, T-14 |
| REQ-EVT-F14 | T-05, T-06, T-07 |
| REQ-EVT-B01 | T-08, T-09, T-16 |
| REQ-EVT-B02 | T-08, T-09, T-16 |
| REQ-EVT-B03 | T-04, T-09, T-11, T-16 |
| REQ-EVT-B04 | T-11, T-16 |
| REQ-EVT-B05 | T-08, T-09, T-16 |
| REQ-EVT-B06 | T-05, T-10, T-16 |
| REQ-EVT-T01 | T-13, T-17, T-18 |
| REQ-EVT-T02 | T-15, T-18 |

## Punti aperti

| ID | Punto aperto | Azione |
|---|---|---|
| OPEN-EVT-01 | Bug trovati in collaudo | Se IT-E0x fallisce → issue GitHub + workflow §6.4/§6.5 (registro in `BUGS.md`) |
| OPEN-EVT-02 | Hook su file event-service | Il matcher del hook copre `services/<svc>/**/*.py`: verificare l'esecuzione al primo salvataggio sotto `services/event-service/` |
