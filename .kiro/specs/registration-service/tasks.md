# registration-service — Tasks

**Spec:** `.kiro/specs/registration-service/`
**Contratto:** `Exam/techconf-exam/contracts/openapi/registration-service.yaml`
**Commit format per task:** `feat(registration): <descrizione> [T-XX]`
**Commit format per test:** `test(registration): <descrizione> [T-XX]`
**Commit format per docs:** `docs(registration): <descrizione> [T-XX]`

Eseguire i task tramite **Start task**, uno alla volta, nell'ordine sotto riportato. Gli
ID T-XX restano stabili anche quando l'ordine non è numerico. Ogni task deve essere
verificato e committato separatamente prima del successivo. Spuntare il task principale
solo dopo tutte le verifiche; i sottopunti descrivono il lavoro. Ogni task è verificabile
senza implementare i task successivi.

**Prerequisiti:** user-service **ed** event-service completi e avviabili
(registration-service li chiama entrambi, REQ-REG-B01/B02). Le loro spec sono in
`.kiro/specs/user-service/` e `.kiro/specs/event-service/`.

**Ordine:** T-01 → T-02 → T-04 → T-05 → T-06 → T-07 → T-08 → T-03 → T-09 → T-10 → T-11 → T-12 → T-13 → T-14 → T-15 → T-16 → T-17 → T-18 → T-19 → T-20.

---

- [x] 1. T-01 — Scaffold struttura directory e package

  - Creare `Exam/techconf-exam/services/registration-service/`
  - `app/__init__.py` (docstring), `app/__main__.py` (stub)
  - File vuoti: `app/config.py`, `routes.py`, `service.py`, `repository.py`,
    `http_client.py`, `validators.py`, `errors.py`, `pagination.py`, `models.py`
  - `app/backends/__init__.py`, `memory.py`, `json_backend.py`, `sqlite_backend.py`
  - `requirements.txt` (`flask`, `requests`), `requirements-dev.txt` (`-r requirements.txt`,
    `-r ../../tests/integration/requirements.txt`, `pytest`, `pytest-cov`, `responses`)
  - Installare: `py -3.12 -m pip install -r requirements-dev.txt`; verificare import
  - `tests/unit/` e `tests/integration/` con `__init__.py`
  - **Completamento:** `py -3.12 -c "import app"` senza errori e senza `PORT`

  _Requirements: REQ-REG-F12, REQ-REG-F13_
  _Commit: `feat(registration): scaffold package structure [T-01]`_

- [x] 2. T-02 — Configurazione (`config.py`)

  - `Config` con `port`, `storage_backend`, `data_dir`, `user_service_url`,
    `event_service_url`
  - `load_config()`: `PORT` (ValueError se assente/non intero), `STORAGE_BACKEND`
    default `memory`, `DATA_DIR` default `./data`, `USER_SERVICE_URL` default
    `http://localhost:5001`, `EVENT_SERVICE_URL` default `http://localhost:5002`
  - **Completamento:** import senza PORT; `load_config()` senza PORT → ValueError;
    default dei due URL corretti

  _Requirements: REQ-REG-F12_
  _Commit: `feat(registration): config factory and Config dataclass [T-02]`_

- [x] 3. T-04 — Moduli di supporto (`errors`, `pagination`, `models`, `validators`)

  - `errors.py`: costanti (`VALIDATION_ERROR`, `REFERENCE_NOT_FOUND`, `EVENT_NOT_OPEN`,
    `ALREADY_REGISTERED`, `EVENT_FULL`, `INVALID_STATUS_TRANSITION`, `NOT_FOUND`,
    `METHOD_NOT_ALLOWED`, `MALFORMED_JSON`, `DEPENDENCY_UNAVAILABLE`) +
    `make_error_response` con `details` sempre dict
  - `models.py`: `new_registration_record(user_id, event_id, amount, now)` (UUID v4,
    `status="confirmed"`), `registration_to_dict` (7 campi), `utcnow_iso()` microsecondo
  - `pagination.py`: `parse_pagination_params` (422 su vuoto/non numerico/non intero/
    fuori range), `paginate` con `total` pre-slice
  - `validators.py`: `validate_body_is_object`, `validate_registration_create`
    (`user_id`/`event_id` uuid, no altri campi), `validate_registration_patch` (solo
    `status`, enum), `validate_stats_query` (`event_id` required uuid),
    `validate_list_filters` (`status` enum, `user_id`/`event_id` uuid se presenti)
  - **Completamento:** test unitari dei moduli verdi

  _Requirements: REQ-REG-F03, REQ-REG-F05, REQ-REG-F06, REQ-REG-F10, REQ-REG-F11_
  _Commit: `feat(registration): errors, pagination, models, validators modules [T-04]`_

- [x] 4. T-05 — Repository: interfaccia astratta e backend memory

  - `AbstractRegistrationRepository(ABC)` con `create_if_allowed(user_id, event_id,
    capacity, make_record)`, `get`, `list_all(filters)`, `set_status(reg_id, new_status,
    now)`, `delete`, `count_confirmed(event_id)`
  - Eccezioni `AlreadyRegisteredError`, `EventFullError`
  - `MemoryRegistrationRepository` con `RLock` per istanza; `create_if_allowed` esegue
    controllo duplicato confirmed + conteggio capienza + creazione **sotto lock**;
    `set_status` e `count_confirmed` sotto lock
  - `get_repository(backend, data_dir)` (import locali); in T-05 solo `memory`
  - **Completamento:** test memory: create_if_allowed (ok/ALREADY_REGISTERED/EVENT_FULL),
    list con filtri, set_status, count_confirmed, delete

  _Requirements: REQ-REG-F13, REQ-REG-B04, REQ-REG-B05, REQ-REG-B07, REQ-REG-B08_
  _Commit: `feat(registration): repository ABC and MemoryRegistrationRepository [T-05]`_

- [x] 5. T-06 — Backend JSON

  - `JsonRegistrationRepository`: `registrations.json`, lettura completa, scrittura
    atomica (tmp + `os.replace()`), `RLock`, stessa semantica `create_if_allowed`/
    `set_status`/`count_confirmed`
  - **Completamento:** persistenza verificata su riapertura; nessun `.tmp` residuo

  _Requirements: REQ-REG-F13_
  _Commit: `feat(registration): JsonRegistrationRepository with atomic writes and RLock [T-06]`_

- [x] 6. T-07 — Backend SQLite

  - `SqliteRegistrationRepository`: `CREATE TABLE registrations (...)`, indice
    `(event_id, status)`, indice unico parziale `(user_id, event_id) WHERE
    status='confirmed'` come rete di sicurezza per B04; connessione condivisa
    `check_same_thread=False`, `RLock`, write in `with conn:`; `IntegrityError` →
    `AlreadyRegisteredError`
  - **Completamento:** persistenza su riapertura; `registrations.db` in `DATA_DIR`
    (escluso via `data/`); il doppio confirmed è impedito sia dal lock sia dall'indice

  _Requirements: REQ-REG-F13, REQ-REG-B04_
  _Commit: `feat(registration): SqliteRegistrationRepository with shared connection and RLock [T-07]`_

- [x] 7. T-08 — Client HTTP verso user ed event (`http_client.py`)

  - `UserServiceClient(base_url, timeout=2.0)` con `get_user(id)`; `EventServiceClient`
    con `get_event(id)`; base `_get` condivisa
  - Eccezioni `ReferenceNotFoundError`, `DependencyUnavailableError`
  - Mappatura: timeout 2s; 404 → `ReferenceNotFoundError`; `Timeout`/`ConnectionError`/
    5xx/status inatteso → `DependencyUnavailableError`
  - **Completamento:** test con `responses` per ogni ramo di entrambi i client; nessuna
    richiesta reale in rete

  _Requirements: REQ-REG-B01, REQ-REG-B02, REQ-REG-B09, REQ-REG-F12_
  _Commit: `feat(registration): UserServiceClient and EventServiceClient with 2s timeout [T-08]`_

- [x] 8. T-03 — Health endpoint e application factory

  - `create_app(repo=None, config=None, user_client=None, event_client=None) -> Flask`
  - `GET /health` → `{"status": "ok", "service": "registration-service"}`
  - Error handler 400/404/405 → formato `Error` con `details: {}`
  - `__main__.py`: `load_config()` → `create_app(config=cfg)` → `app.run(...)`
    (`# pragma: no cover`)
  - **Completamento:** `GET /health` → 200 body esatto conforme; `POST /health` → 405.
    Blueprint completo in T-12.

  _Requirements: REQ-REG-F01, REQ-REG-F09, REQ-REG-F11, REQ-REG-F12_
  _Commit: `feat(registration): health endpoint and app factory [T-03]`_

- [x] 9. T-09 — RegistrationService: create (B01/B02/B03/B06 + atomico B04/B05/B09)

  - `RegistrationService.__init__(self, repo, user_client, event_client)`
  - `create_registration(data)`: validazione a monte; `user_client.get_user` (B01,
    404→422 REFERENCE_NOT_FOUND, unavailable→503); `event_client.get_event` (B02,
    404→422, unavailable→503); `event.status=="published"` (B03, else 422 EVENT_NOT_OPEN);
    `amount=event.price` (B06); poi `repo.create_if_allowed(user_id, event_id,
    event.capacity, make_record)` (B04→409 ALREADY_REGISTERED, B05→409 EVENT_FULL);
    timestamp; le chiamate HTTP avvengono **fuori** dal lock
  - **Completamento:** test service con memory + `responses`: successo (amount=price,
    confirmed), REFERENCE_NOT_FOUND (user, event), EVENT_NOT_OPEN, ALREADY_REGISTERED,
    EVENT_FULL, DEPENDENCY_UNAVAILABLE; nessuna mutazione su errore

  _Requirements: REQ-REG-F02, REQ-REG-B01, REQ-REG-B02, REQ-REG-B03, REQ-REG-B05, REQ-REG-B06, REQ-REG-B09, REQ-REG-F10_
  _Commit: `feat(registration): RegistrationService.create_registration with dependency checks [T-09]`_

- [x] 10. T-10 — RegistrationService: get, list e filtri

  - `get_registration(id)` (404 se assente); `list_registrations(filters, page,
    page_size)` con filtri `user_id`/`event_id`/`status` AND, `total` post-filtro
  - **Completamento:** test filtri combinati, `total` corretto, `status` invalido→422,
    pagina oltre l'ultima → items vuoti

  _Requirements: REQ-REG-F04, REQ-REG-F05_
  _Commit: `feat(registration): RegistrationService.get and list with filters [T-10]`_

- [x] 11. T-11 — RegistrationService: PATCH stato e transizioni B07

  - `patch_status(id, new_status)`: 404 se assente; `confirmed→cancelled` ok (libera il
    posto); `cancelled→confirmed`→422 `INVALID_STATUS_TRANSITION`; stesso stato → no-op
    (nessun aggiornamento `updated_at`); `repo.set_status` sotto lock; aggiorna
    `updated_at` su cambiamento
  - **Completamento:** test cancel→200 e posto liberato (nuova iscrizione riesce),
    reactivation→422, no-op invariato, `updated_at` aggiornato (monkeypatch)

  _Requirements: REQ-REG-F06, REQ-REG-B07, REQ-REG-F10_
  _Commit: `feat(registration): RegistrationService.patch_status with transition rules [T-11]`_

- [x] 12. T-12 — Routes HTTP complete (inclusi stats e PUT→405)

  - Rotte Blueprint: `POST` (201+Location), `GET` lista (paginato+filtri),
    `GET /stats` (registrata **prima** di `/<id>`), `GET /<id>`, `PATCH /<id>`
    (solo status), `DELETE /<id>` (204), `PUT /<id>` → 405 con corpo `Error`
  - `stats(event_id)`: `event_id` required (422 se assente); evento da event-service
    (404→404 NOT_FOUND, unavailable→503); `confirmed` da `repo.count_confirmed`;
    `available=capacity-confirmed` (B08)
  - Tradurre le eccezioni del service in status via `errors.py`
  - **Completamento:** verifiche via test client (dipendenze mockate): `PUT`→405,
    `stats` senza `event_id`→422, `stats` evento inesistente→404, DELETE→204 senza CT
    JSON, `page_size=101`→422, body `[]`→422

  _Requirements: REQ-REG-F02..F11, REQ-REG-B08_
  _Commit: `feat(registration): all HTTP routes incl stats and PUT 405 [T-12]`_

- [x] 13. T-13 — Test unitari completi (`tests/unit/`)

  - `test_routes.py`: ogni endpoint (400/404/405/409/422/503); dipendenze mockate con
    `responses`; contratto con `flask_to_contract_dict`
  - `test_service.py`: ogni metodo con memory + `responses`; B01..B09; no-mutazione su
    errore; `updated_at` monkeypatch
  - `test_repository.py`: parametrizzato sui **tre** backend con `tmp_path`;
    create_if_allowed, get, list con filtri, set_status, delete, count_confirmed;
    riapertura dati json/sqlite
  - `test_http_client.py`: entrambi i client con `responses` (200/404/5xx/Connection/
    Timeout)
  - `test_contracts.py`: una `assert_matches_contract` per operazione (`health`,
    `createRegistration`, `listRegistrations`, `registrationStats`, `getRegistration`,
    `updateRegistration`, `deleteRegistration`, `putRegistrationNotAllowed` 405)
  - `test_config.py`: senza PORT → ValueError; default dei due URL; import senza PORT
  - `test_concurrency.py`: capacità 1 + due create simultanee → un 201 e un EVENT_FULL;
    due create simultanee stesso utente → un 201 e un ALREADY_REGISTERED
  - Eseguire `py -3.12 -m pytest tests/unit -v --cov=app --cov-report=term-missing
    --cov-fail-under=80` → coverage ≥ 80%
  - Ogni test contiene `REQ-REG-<ID>` nel nome/docstring (o `@pytest.mark.req`)
  - **Completamento:** suite unit verde e coverage ≥ 80%

  _Requirements: REQ-REG-T01_
  _Commit: `test(registration): full unit test suite with >=80% coverage [T-13]`_

- [x] 14. T-14 — Aggiornamento `services.yaml` (user + event + registration)

  - Estendere `Exam/techconf-exam/services.yaml` con `registration` oltre a `user` ed
    `event`:
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
      registration:
        cwd: services/registration-service
        command: py -3.12 -m app
        health_path: /health
    ```
  - **Completamento:** avvio manuale con `PORT`, `USER_SERVICE_URL`, `EVENT_SERVICE_URL`
    → `/health` risponde; `py -3.12 -m pytest tests/unit -v` verde

  _Requirements: REQ-REG-F12, REQ-REG-F13_
  _Commit: `feat(registration): declare all three mandatory services in services.yaml [T-14]`_

- [x] 15. T-15 — Test di integrazione propri (`tests/integration/`)

  - `test_registration_integration.py`: avvia **user**, **event** e **registration**
    reali su porte libere (`STORAGE_BACKEND=memory`), inietta gli `*_SERVICE_URL`
    corretti, attende `/health`, `try/finally` annidati con `terminate()`+`kill()`
  - Positivo: organizer + attendee + evento pubblicato (via event reale) → registra →
    201 `confirmed`, `amount == price`
  - Riferimento inesistente: `user_id`/`event_id` casuale → 422 `REFERENCE_NOT_FOUND`
  - Dipendenza spenta: `USER_SERVICE_URL`/`EVENT_SERVICE_URL` su porta chiusa → POST →
    503 `DEPENDENCY_UNAVAILABLE`
  - **Completamento:** `py -3.12 -m pytest tests/integration -v` → tutti verdi

  _Requirements: REQ-REG-T02_
  _Commit: `test(registration): own integration tests with three real services [T-15]`_

- [x] 16. T-16 — Collaudo obbligatorio completo e salvataggio `collaudo.txt`

  - Con user, event e registration dichiarati in `services.yaml`, eseguire dalla root
    `Exam/techconf-exam/`:
    `py -3.12 -m pytest tests/integration -m mandatory -v | Tee-Object collaudo.txt`
    (o redirezione equivalente) — copre IT-U01..U08, IT-E01..E08, IT-R01..R10, IT-J01
  - Salvare l'output completo in `Exam/techconf-exam/collaudo.txt` (checklist §9)
  - Verificare che i test obbligatori passino; per ogni fallimento seguire T-18 (bug
    workflow) **prima** di considerare il collaudo concluso
  - **Completamento:** `collaudo.txt` presente con l'output reale del run `-m mandatory`

  _Requirements: REQ-REG-T01, REQ-REG-T02, REQ-REG-B01..B09_
  _Commit: `docs(registration): mandatory acceptance output collaudo.txt [T-16]`_

- [x] 17. T-17 — Verifica dei checksum (file protetti intatti)

  - Verificare `Exam/techconf-exam/CHECKSUMS.sha256` con lo strumento disponibile
    (es. `sha256sum -c CHECKSUMS.sha256` o script Python equivalente su Windows)
  - Confermare che `contracts/`, `tests/integration/` e `CHECKSUMS.sha256` **non** sono
    stati modificati (penalità −20, §8)
  - **Completamento:** tutti i checksum verificati OK

  _Requirements: (vincolo §3/§8 Exam.MD)_
  _Commit: `docs(registration): verify protected files checksums [T-17]`_

- [ ] 18. T-18 — Gestione bug reali (BUGS.md) — workflow §6.4/§6.5

  - Per ogni test di collaudo fallito o bug reale trovato durante T-13/T-15/T-16:
    1. aprire **issue GitHub reale** (servizio, test fallito es. `IT-R06`, atteso vs
       ottenuto, requisito violato)
    2. classificare: **impl** (fix in Vibe su `fix/<svc>-<issue#>`, prima test di
       regressione che fallisce, poi fix) oppure **spec** (aggiornare requirements →
       design → tasks, poi eseguire il task)
    3. commit `fix(<svc>): <descr> (closes #N)`, merge su `main`
    4. registrare in `BUGS.md` la riga (ID, issue, trovato da, tipo, requisito, causa
       radice, test di regressione, commit)
  - Requisito di consegna: **almeno 2 bug reali** documentati e chiusi, di cui **almeno
    1 di implementazione**. **Non inventare bug**: registrare solo difetti realmente
    riscontrati con issue e commit reali.
  - **Completamento:** `BUGS.md` con ≥2 bug reali chiusi (≥1 impl), issue e commit
    referenziati esistono davvero

  _Requirements: (§6.5 Exam.MD — consegna)_
  _Commit: `docs: BUGS.md with real documented and closed bugs`_

- [ ] 19. T-19 — README del servizio e verifica checklist di consegna

  - `services/registration-service/README.md`: dipendenze; avvio (env `PORT`,
    `USER_SERVICE_URL`, `EVENT_SERVICE_URL`, `STORAGE_BACKEND`, `DATA_DIR`; tre backend);
    test unit con coverage; integrazione propria; suite del docente (`-k registration`,
    `-m mandatory`); riferimenti `REQ-REG-*` e `T-01..T-20`
  - Verificare la **checklist di consegna §9** con evidenze reali:
    - [ ] steering (4 file) e ≥1 hook funzionante (script verificato; confermare
      esecuzione al salvataggio di un `.py` sotto `services/registration-service/`)
    - [x] specs dei 3 servizi obbligatori con requirements/design/tasks (tasks spuntati
      solo quando realmente eseguiti)
    - [x] `services.yaml` con i 3 servizi; backend memory/json/sqlite funzionanti
    - [x] coverage ≥ 80% per ogni servizio
    - [x] integration test propri per event e registration
    - [x] `collaudo.txt` dal run `-m mandatory` (T-16)
    - [ ] `BUGS.md` con ≥2 bug reali chiusi (T-18): fix verificati, issue non pubblicate
    - [x] README presenti; file protetti non modificati (T-17)
  - **Completamento:** README presente; ogni voce di checklist confermata con evidenza
    reale (nessuna voce spuntata senza prova)

  _Requirements: REQ-REG-T01_
  _Commit: `docs(registration): service README and delivery checklist verification [T-19]`_

- [ ] 20. T-20 — Verifica finale e tag v1.0.0 (solo dopo completamento reale)

  - Rieseguire l'intera piattaforma: unit dei 3 servizi (`--cov-fail-under=80`),
    integrazione propria di event e registration, collaudo `-m mandatory` verde
  - Confermare: checksum intatti (T-17), `BUGS.md` con bug reali chiusi (T-18), issue
    reali chiuse, hook funzionante, `collaudo.txt` aggiornato
  - **Solo se tutte le verifiche precedenti sono reali e verdi**, creare il tag
    `v1.0.0` su `main`. **Non** creare il tag se anche una sola voce non è realmente
    soddisfatta; **non** inventare risultati. Il push del tag/branch avviene solo su
    indicazione esplicita.
  - **Completamento:** tutte le verifiche reali verdi; tag `v1.0.0` creato su `main`
    solo a fronte del completamento effettivo

  _Requirements: (§6.6/§9 Exam.MD — consegna)_
  _Commit: `chore(release): tag v1.0.0 after verified mandatory delivery`_

---

## Copertura requisiti → task

| Requisito | Task |
|---|---|
| REQ-REG-F01 | T-03 |
| REQ-REG-F02 | T-09, T-12 |
| REQ-REG-F03 | T-04, T-12 |
| REQ-REG-F04 | T-10, T-12 |
| REQ-REG-F05 | T-04, T-10, T-12 |
| REQ-REG-F06 | T-11, T-12 |
| REQ-REG-F07 | T-12 |
| REQ-REG-F08 | T-12 |
| REQ-REG-F09 | T-03, T-12 |
| REQ-REG-F10 | T-04, T-09, T-11 |
| REQ-REG-F11 | T-04, T-12 |
| REQ-REG-F12 | T-02, T-08, T-14 |
| REQ-REG-F13 | T-05, T-06, T-07 |
| REQ-REG-B01 | T-08, T-09, T-16 |
| REQ-REG-B02 | T-08, T-09, T-16 |
| REQ-REG-B03 | T-09, T-16 |
| REQ-REG-B04 | T-05, T-07, T-09, T-13 (concorrenza), T-16 |
| REQ-REG-B05 | T-05, T-09, T-13 (concorrenza), T-16 |
| REQ-REG-B06 | T-09, T-16 |
| REQ-REG-B07 | T-05, T-11, T-16 |
| REQ-REG-B08 | T-05, T-12, T-16 |
| REQ-REG-B09 | T-08, T-09, T-16 |
| REQ-REG-T01 | T-13, T-16, T-19, T-20 |
| REQ-REG-T02 | T-15, T-16, T-20 |

## Punti aperti (consegna — devono essere reali, non inventati)

| ID | Punto aperto | Azione |
|---|---|---|
| OPEN-REG-01 | Bug reali in collaudo | T-18: issue GitHub reale + fix + `BUGS.md` (≥2 bug, ≥1 impl) |
| OPEN-REG-02 | Issue GitHub | `gh` CLI non disponibile in ambiente: pubblicare le issue reali dal browser prima di chiuderle nei commit |
| OPEN-REG-03 | Hook su file registration | Verificare l'esecuzione al primo salvataggio di un `.py` sotto `services/registration-service/` |
| OPEN-REG-04 | Tag `v1.0.0` | Creare solo dopo il completamento reale (T-20); push solo su indicazione esplicita |

## Verifica del 25 settembre 2026

I log in `Exam/techconf-exam/verification/` documentano i test effettivi. T-18, T-19 e T-20 rimangono aperti per la chiusura delle issue, la verifica del trigger in Kiro e il tag della consegna finale. Il test dello script hook con payload simulato non prova l’attivazione del trigger nell’IDE.
