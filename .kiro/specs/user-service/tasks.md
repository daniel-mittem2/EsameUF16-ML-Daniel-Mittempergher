# user-service — Tasks

**Spec:** `.kiro/specs/user-service/`
**Commit format per task:** `feat(user): <descrizione> [T-XX]`
**Commit format per test:** `test(user): <descrizione> [T-XX]`
**Commit format per docs:** `docs(user): <descrizione> [T-XX]`

Eseguire i task tramite Start task, uno alla volta, nell'ordine sotto riportato. Gli ID T-XX restano stabili anche quando l'ordine non è numerico. Ogni task deve essere verificato e committato separatamente prima di iniziare il successivo. Spuntare il task principale solo dopo tutte le verifiche; i sottopunti descrivono il lavoro, non sono task indipendenti.

**Ordine:** T-01 → T-02 → T-04 → T-05 → T-06 → T-07 → T-03 → T-08 → T-09 → T-10 → T-11 → T-12 → T-13 → T-14 → T-15 → T-16 → T-17.

T-01 prepara anche le dipendenze. T-03 segue moduli di supporto e backend, quindi può creare una factory funzionante. I test pertinenti alle verifiche di ciascun task possono essere introdotti nello stesso task; T-13 completa la copertura.

---

- [ ] 1. T-01 — Scaffold struttura directory e package

  - Creare la directory `Exam/techconf-exam/services/user-service/`
  - Creare `app/__init__.py` (vuoto, con docstring)
  - Creare `app/__main__.py` (stub: `print("user-service starting...")`)
  - Creare file vuoti: `app/config.py`, `app/routes.py`, `app/service.py`,
    `app/repository.py`, `app/validators.py`, `app/errors.py`,
    `app/pagination.py`, `app/models.py`
  - Creare `app/backends/__init__.py`, `app/backends/memory.py`,
    `app/backends/json_backend.py`, `app/backends/sqlite_backend.py`
  - Creare `requirements.txt` con: `flask`, `requests`
  - Creare `requirements-dev.txt` con: `-r requirements.txt`, `-r ../../tests/integration/requirements.txt`, `pytest`, `pytest-cov`, `responses`. Il requirements della suite fornisce anche PyYAML e jsonschema per il validator.
  - Dalla directory del servizio installare le dipendenze prima delle verifiche: `py -3.12 -m pip install -r requirements-dev.txt`. Usare lo stesso interprete per test e avvio; verificare import di flask, requests, pytest, responses, yaml e jsonschema.
  - Creare directory `tests/unit/` e `tests/integration/` con `__init__.py`
  - Verificare che `py -3.12 -c "from app import __init__"` dalla directory
    del servizio non produca errori (import silenzioso senza PORT)

  _Requirements: REQ-USR-F13, REQ-USR-F14_
  _Commit: `feat(user): scaffold package structure [T-01]`_

- [ ] 2. T-02 — Configurazione (`config.py`)

  - Implementare il dataclass `Config` con campi `port: int`,
    `storage_backend: str`, `data_dir: Path`
  - Implementare `load_config(port=_SENTINEL) -> Config` che:
    - legge `PORT` da env; solleva `ValueError` se assente o non intero
    - legge `STORAGE_BACKEND` (default `"memory"`)
    - legge `DATA_DIR` (default `Path("./data")`)
  - Verificare che `from app import config` funzioni **senza** `PORT` impostata
  - Verificare che `load_config()` senza `PORT` in env sollevi `ValueError`
  - Verificare che `load_config(port=5001)` funzioni anche senza env

  _Requirements: REQ-USR-F13_
  _Commit: `feat(user): config factory and Config dataclass [T-02]`_

- [ ] 3. T-04 — Moduli di supporto (`errors.py`, `pagination.py`, `models.py`)

  - `errors.py`: costanti codici errore (`VALIDATION_ERROR`, `NOT_FOUND`,
    `EMAIL_ALREADY_EXISTS`, `MALFORMED_JSON`, `METHOD_NOT_ALLOWED`),
    `make_error_response(code, message, details=None, status=None)` che produce
    `(jsonify(...), http_status)` con `details` sempre dict non null
  - `models.py`: `new_user_record(data, now) -> dict` con email lowercase,
    `role` default `"attendee"`, `company` default `None`;
    `user_to_dict(record) -> dict` con i soli 8 campi del contratto
  - `pagination.py`: `parse_pagination_params(args) -> tuple[int,int]`
    che valida tipo (deve essere intero), range (page≥1, page_size 1..100),
    valori vuoti e non numerici → 422; `paginate(items, page, page_size) -> dict`
    con `total` = len(items) pre-slice
  - `validators.py`: funzioni pure `validate_body_is_object(data)`,
    `validate_email_format(email)` (regex `^[^@\s]+@[^@\s]+\.[^@\s]+$`),
    `validate_user_create(data) -> list[str]`, `validate_user_update(data) -> list[str]`
    che controllano anche campi sconosciuti (`additionalProperties: false`)

  _Requirements: REQ-USR-F03, REQ-USR-F04, REQ-USR-F06, REQ-USR-F12_
  _Commit: `feat(user): errors, pagination, models, validators modules [T-04]`_

- [ ] 4. T-05 — Repository: interfaccia astratta e backend memory

  - Definire `AbstractUserRepository(ABC)` in `repository.py` con metodi:
    `create`, `get`, `list_all`, `update`, `delete`, `get_by_email`
  - Definire `EmailAlreadyExistsError(Exception)` in `repository.py`
  - Implementare `MemoryUserRepository` con `threading.RLock()` condiviso
    per l'istanza; l'intera sequenza check-unicità + scrittura avviene
    dentro il lock
  - Implementare `get_repository(backend, data_dir) -> AbstractUserRepository`
    (factory) in `repository.py`; in T-05 implementare solo il ramo memory con import locali. Aggiungere i rami json/sqlite in T-06/T-07, senza importare classi non ancora implementate.
  - Verificare che due chiamate `create` concorrenti con la stessa email
    producano esattamente un successo e un `EmailAlreadyExistsError` (test
    con `threading.Thread` su `MemoryUserRepository`)

  _Requirements: REQ-USR-F14, REQ-USR-B01 (concorrenza)_
  _Commit: `feat(user): repository ABC, EmailAlreadyExistsError, MemoryUserRepository [T-05]`_

- [ ] 5. T-06 — Backend JSON

  - Implementare `JsonUserRepository(AbstractUserRepository)`:
    - legge `users.json` all'apertura (crea lista vuota se il file non esiste)
    - scrittura atomica con file temporaneo + `os.replace()`
    - `threading.RLock()` per istanza: check-unicità + scrittura dentro il lock
    - `get_by_email` con confronto case-insensitive
  - Verificare persistenza: creare utente, istanziare nuovo `JsonUserRepository`
    sullo stesso file, recuperare l'utente → presente (riapertura dati)
  - Verificare che la riapertura carichi correttamente i dati esistenti

  _Requirements: REQ-USR-F14 (json backend), REQ-USR-B01 (lock)_
  _Commit: `feat(user): JsonUserRepository with atomic writes and RLock [T-06]`_

- [ ] 6. T-07 — Backend SQLite

  - Implementare `SqliteUserRepository(AbstractUserRepository)`:
    - `CREATE TABLE IF NOT EXISTS users (...)` con `UNIQUE INDEX LOWER(email)`
    - connessione condivisa `check_same_thread=False`
    - `threading.RLock()` per istanza (protegge check + write)
    - cattura `sqlite3.IntegrityError` → rilancia `EmailAlreadyExistsError`
    - ogni write con `with conn:` per transazione automatica
  - Verificare persistenza dopo riapertura (stesso pattern del backend JSON)
  - Verificare che il file `users.db` finisca in `DATA_DIR` e non in git
    (la directory `data/` è già in `.gitignore`)

  _Requirements: REQ-USR-F14 (sqlite backend), REQ-USR-B01 (IntegrityError)_
  _Commit: `feat(user): SqliteUserRepository with shared connection and RLock [T-07]`_

- [ ] 7. T-03 — Health endpoint e application factory

  - Implementare `create_app(repo=None, config=None) -> Flask` in `app/__init__.py`
  - Registrare la rotta `GET /health` → `{"status": "ok", "service": "user-service"}`
  - Registrare error handler per 400, 404, 405 che producono `{"error": {"code": "...", "message": "...", "details": {}}}` (usa `errors.py`)
  - Implementare `__main__.py`: chiama `load_config()`, poi `create_app(config=cfg)`, poi `app.run(host="0.0.0.0", port=cfg.port, debug=False)`
  - Verificare `GET /health` → 200 con body esatto e schema conforme
  - Verificare che POST su `/health` risponda 405 con corpo JSON. In questo task registrare soltanto health e gli error handler; registrare il Blueprint utenti completo in T-12, dopo il service layer.

  _Requirements: REQ-USR-F01, REQ-USR-F10, REQ-USR-F12, REQ-USR-F13_
  _Commit: `feat(user): health endpoint and app factory [T-03]`_

- [ ] 8. T-08 — UserService: create e regole B01/B02

  - Implementare `UserService.__init__(self, repo)`
  - Implementare `UserService.create_user(data) -> dict`:
    - normalizza email a lowercase (REQ-USR-B02)
    - chiama `repo.get_by_email` per controllo unicità (REQ-USR-B01)
    - genera timestamp con `utcnow_iso()` (microsecondo, suffisso Z)
    - chiama `models.new_user_record`
    - chiama `repo.create`
    - cattura `EmailAlreadyExistsError` → rilancia come eccezione del service
  - Implementare `utcnow_iso()` in `models.py` con formato `%Y-%m-%dT%H:%M:%S.%fZ`
  - Verificare che `create_user` con email maiuscola la salvi in minuscolo
  - Verificare che due create con stessa email (case diversa) producano conflitto

  _Requirements: REQ-USR-F02, REQ-USR-B01, REQ-USR-B02, REQ-USR-F11_
  _Commit: `feat(user): UserService.create_user with email normalisation [T-08]`_

- [ ] 9. T-09 — UserService: get, list e filtri B03

  - Implementare `UserService.get_user(user_id) -> dict` (404 se mancante)
  - Implementare `UserService.list_users(filters, page, page_size) -> dict`:
    - filtro `role` (confronto esatto)
    - filtro `email` (confronto case-insensitive sulla email normalizzata)
    - filtri combinati AND logic (REQ-USR-B03-AC3)
    - `total` = conteggio post-filtro pre-paginazione (REQ-USR-B03-AC4)
  - Verificare che `total` rifletta i record filtrati e non il totale assoluto
  - Verificare filtro `role` invalido → propaga errore 422 al chiamante

  _Requirements: REQ-USR-F05, REQ-USR-F06, REQ-USR-B03_
  _Commit: `feat(user): UserService.get_user and list_users with filters [T-09]`_

- [ ] 10. T-10 — UserService: replace (PUT) e update (PATCH)

  - Implementare `UserService.replace_user(user_id, data) -> dict` (PUT):
    - 404 se non trovato
    - normalizza email, controlla unicità escludendo se stesso (REQ-USR-B01-AC3)
    - mantiene `created_at`, aggiorna `updated_at`
  - Implementare `UserService.update_user(user_id, data) -> dict` (PATCH):
    - cerca risorsa **per prima cosa** (404 se non trovata, anche per `{}`)
    - rifiuta campi sconosciuti esplicitamente
    - se `data == {}`: ritorna record invariato, `updated_at` non aggiornato
    - altrimenti: applica solo i campi presenti, normalizza email se presente,
      controlla unicità, aggiorna `updated_at`
  - Verificare che PUT con stessa email dell'utente non produca 409
  - Verificare che PATCH `{}` su ID inesistente produca 404 (non 200)
  - Verificare che `created_at` non cambi dopo PUT (REQ-USR-F11-AC3)
  - Verificare con orologio mockato che `updated_at` sia diverso da `created_at`
    dopo un aggiornamento reale (REQ-USR-F11; usa `monkeypatch` su `utcnow_iso`)

  _Requirements: REQ-USR-F07, REQ-USR-F08, REQ-USR-B01, REQ-USR-B02, REQ-USR-F11_
  _Commit: `feat(user): UserService.replace_user and update_user [T-10]`_

- [ ] 11. T-11 — UserService: delete

  - Implementare `UserService.delete_user(user_id) -> None`:
    - 404 se non trovato
    - chiama `repo.delete`
  - Verificare che dopo delete, `get_user` sullo stesso ID sollevi 404
  - Verificare che un secondo delete sullo stesso ID sollevi 404

  _Requirements: REQ-USR-F09_
  _Commit: `feat(user): UserService.delete_user [T-11]`_

- [ ] 12. T-12 — Routes HTTP complete

  - Implementare tutte le rotte in `routes.py` come Blueprint:
    - `POST /api/v1/users` → 201 + `Location` header + body `User`
    - `GET /api/v1/users` → 200 paginato con filtri
    - `GET /api/v1/users/<id>` → 200 o 404
    - `PUT /api/v1/users/<id>` → 200 o 404/409/422
    - `PATCH /api/v1/users/<id>` → 200 o 404/409/422
    - `DELETE /api/v1/users/<id>` → 204 senza body
  - Per le rotte POST/PUT/PATCH validare il body con `validators.py`; GET e DELETE non richiedono un body. Delegare al
    `UserService`, serializzare con `user_to_dict`
  - Verificare `GET /api/v1/users` con `page_size=101` → 422
  - Verificare `GET /api/v1/users?page=abc` → 422
  - Verificare `POST /api/v1/users` con body `[]` (array) → 422
  - Verificare `POST /api/v1/users` con body `{"first_name": 123, ...}` → 422
    (tipo sbagliato, nessuna coercizione)
  - Verificare `DELETE /api/v1/users/<id>` → 204 senza corpo e senza Content-Type JSON
  - Verificare `POST /api/v1/users/<id>` → 405 con corpo JSON; `PUT /api/v1/users/<id-inesistente>` con body valido → 404 NOT_FOUND.

  _Requirements: REQ-USR-F02..F12_
  _Commit: `feat(user): all HTTP routes in Blueprint [T-12]`_

- [ ] 13. T-13 — Test unitari completi (`tests/unit/`)

  - `test_routes.py`: test Flask test client per tutti gli endpoint
    (inclusi casi 400/404/405/409/422 per ogni vincolo); usa `flask_to_contract_dict`
    per i test di contratto
  - `test_service.py`: test di ogni metodo `UserService` con
    `MemoryUserRepository`; usa `monkeypatch` su `utcnow_iso` per i test
    di timestamp; verifica no-mutazione in caso di errore (REQ-USR-F11-AC4)
  - `test_repository.py`: test parametrizzati su tutti e tre i backend
    con `tmp_path` per json/sqlite; copre: create, get, get_by_email,
    list_all con filtri, update, delete; test di riapertura dati per
    json e sqlite (REQ-USR-F14-AC2/AC3); test di unicità concorrente con
    `threading.Thread` (REQ-USR-B01)
  - `test_contracts.py`: una chiamata `assert_matches_contract` per ciascuna
    delle 7 operazioni definite nel contratto, usando `flask_to_contract_dict`
  - `test_config.py`: verifica `load_config()` senza PORT → `ValueError`;
    verifica default di STORAGE_BACKEND e DATA_DIR; verifica che import di
    `app` non richieda PORT
  - Eseguire `py -3.12 -m pytest tests/unit -v --cov=app --cov-report=term-missing --cov-fail-under=80`
    dalla directory del servizio e verificare coverage ≥ 80%
  - Ogni funzione di test deve contenere `REQ-USR-<ID>` nel nome o nella docstring

  _Requirements: REQ-USR-T01_
  _Commit: `test(user): full unit test suite with ≥80% coverage [T-13]`_

- [ ] 14. T-14 — `services.yaml` e preparazione ambiente

  - Creare (o aggiornare) `Exam/techconf-exam/services.yaml` dichiarando
    **solo** `user`:
    ```yaml
    services:
      user:
        cwd: services/user-service
        command: py -3.12 -m app
        health_path: /health
    ```
  - Verificare le dipendenze già installate in T-01 nello stesso interprete usato dal manifest; non assumere che la suite attivi automaticamente un venv.
  - Verificare avvio manuale: `$env:PORT="5001"; py -3.12 -m app` dalla
    directory del servizio → nessun errore, `GET /health` risponde
  - Verificare `py -3.12 -m pytest tests/unit -v` dalla directory del
    servizio → tutti i test passano

  _Requirements: REQ-USR-F13, REQ-USR-F14_
  _Commit: `feat(user): services.yaml with user service declaration [T-14]`_

- [ ] 15. T-15 — Test di integrazione propri (`tests/integration/`)

  - Implementare `test_user_integration.py` con fixture `live_server`:
    - avvia `py -3.12 -m app` come sottoprocesso con `PORT` libera e
      `STORAGE_BACKEND=memory`
    - attende `/health` con timeout 10s
    - `try/finally` garantisce `proc.terminate()` + fallback `proc.kill()`
      (REQ-USR-T01-AC6)
  - Test positivo: POST utente → GET by id → 200 con dati corretti
  - Test riferimento inesistente: GET `/api/v1/users/<uuid-fake>` → 404
  - Test email duplicata: due POST con stessa email → secondo produce 409
  - Eseguire `py -3.12 -m pytest tests/integration -v` → tutti passano

  _Requirements: REQ-USR-T01-AC6_
  _Commit: `test(user): own integration tests with real subprocess [T-15]`_

- [ ] 16. T-16 — Collaudo con suite del docente (solo user) e verifica checksum

  - Installare dipendenze della suite:
    `py -3.12 -m pip install -r Exam/techconf-exam/tests/integration/requirements.txt`
  - Eseguire dalla root di `Exam/techconf-exam/`:
    `py -3.12 -m pytest tests/integration -k user -v`
  - Verificare che tutti i test IT-U01..IT-U08 passino
  - Salvare l'output in `Exam/techconf-exam/collaudo_user.txt`
  - Verificare i 17 checksum con lo script Python (nessun file protetto modificato)
  - Se qualche test fallisce: aprire issue GitHub, classificare il tipo di bug
    (implementazione vs specifica) e seguire il workflow §6.4/§6.5 di Exam.MD
    **prima** di procedere ai servizi successivi

  _Requirements: tutti REQ-USR-*_
  _Commit: `docs(user): acceptance test output collaudo_user.txt [T-16]`_

- [ ] 17. T-17 — `README.md` del servizio

  - Creare `Exam/techconf-exam/services/user-service/README.md` con:
    - come installare le dipendenze
    - come avviare il servizio (variabili d'ambiente, comandi per i tre backend)
    - come eseguire i test unitari con coverage
    - come eseguire i test di integrazione propri
    - come eseguire la suite del docente (solo user)
    - riferimento ai requisiti (`REQ-USR-*`) e ai task (`T-01..T-17`)

  _Requirements: REQ-USR-T01 (documentazione)_
  _Commit: `docs(user): service README with setup and test commands [T-17]`_

---

## Punti aperti da risolvere prima o durante l'implementazione

| ID | Punto aperto | Azione richiesta |
|---|---|---|
| OPEN-01 | Issue GitHub non ancora pubblicata | Pubblicare `ISSUE_DRAFT.md` su GitHub dal browser; aggiornare `ISSUE_DRAFT.md` con il numero dell'issue assegnato |
| OPEN-02 | Hook Kiro non verificato nel pannello | Aprire Explorer → Agent Hooks → confermare che "Run Unit Tests on Python Save" sia visibile e abilitato |
| OPEN-03 | Hook non ancora eseguito su file reale | Verificare al primo salvataggio di un file `.py` sotto `services/user-service/` dopo T-01 |
