# registration-service — Design

**Contratto di riferimento:** `Exam/techconf-exam/contracts/openapi/registration-service.yaml`
**Requirements:** `.kiro/specs/registration-service/requirements.md`
**Standard globali:** `.kiro/steering/structure.md` · `.kiro/steering/tech.md` · `.kiro/steering/platform-standards.md`
**Versione spec:** 1.0 — 2026-09-25
**Workflow:** Requirements-First (fase 2 di 3). Tasks NON ancora prodotti; nessun codice applicativo scritto.

---

## 1. Riferimento al contratto OpenAPI

| Elemento | Dettaglio rilevante |
|---|---|
| `RegistrationCreate` | `additionalProperties: false`; required: `user_id`, `event_id` (nient'altro) |
| `RegistrationPatch` | `additionalProperties: false`; required: `status` (solo `status`) |
| `Registration` (response) | `additionalProperties: false`; required: `id`, `user_id`, `event_id`, `amount`, `status`, `created_at`, `updated_at` |
| `RegistrationStatus` | `enum: [confirmed, cancelled]` |
| `amount` | `type: number` (copiato da `event.price`, read-only) |
| `RegistrationStats` | `additionalProperties: false`; required: `event_id`, `capacity`, `confirmed`, `available` |
| `stats` query `event_id` | **required** (422 se assente) |
| `PUT /{id}` | operazione `putRegistrationNotAllowed` → **405** dichiarato nel contratto |
| `Error` | `additionalProperties: false` su `error`; `details` `additionalProperties: true` |
| `Health` | `additionalProperties: false`; `status: enum: [ok]` |
| Paginazione | `page` min 1 default 1; `page_size` min 1 max 100 default 20 |

**Codici per operazione:** POST 201/400/409/422/503; GET list 200/422; stats
200/404/422/503; GET/{id} 200/404; PATCH 200/404/422; DELETE 204/404; PUT 405.

`amount` (number) e `stats` sono numerici; il validator applica `Draft7`. Il 405 di
`PUT` **è** dichiarato nel contratto: il test di contratto per il 405 di PUT è quindi
lecito (a differenza dei 405 impliciti su altri path).

---

## 2. Struttura dei moduli

Coerente con `structure.md` §7.3. Presente `http_client.py` con **due** client
(user ed event), perché registration chiama entrambe le dipendenze
(REQ-REG-B01/B02/B09).

```
services/registration-service/
  app/
    __init__.py          # create_app(repo=None, config=None, user_client=None, event_client=None)
    __main__.py          # entry point: load_config() → create_app(config=cfg) → run
    config.py            # load_config() → Config (port, storage_backend, data_dir, user_service_url, event_service_url)
    routes.py            # Blueprint: parsing, validazione HTTP, serializzazione, Location
    service.py           # RegistrationService: regole REQ-REG-B01..B09, orchestrazione
    repository.py        # AbstractRegistrationRepository (ABC) + get_repository()
    backends/
      __init__.py
      memory.py          # MemoryRegistrationRepository
      json_backend.py    # JsonRegistrationRepository
      sqlite_backend.py  # SqliteRegistrationRepository
    http_client.py       # UserServiceClient, EventServiceClient (timeout 2s, 404→ref, 5xx/timeout/refused→unavailable)
    validators.py        # validazione input (uuid, body object, status enum, stats query)
    errors.py            # costanti codici errore + make_error_response()
    pagination.py        # parse_pagination_params(), paginate()
    models.py            # new_registration_record(), registration_to_dict(), utcnow_iso()
  tests/
    unit/
      test_routes.py
      test_service.py
      test_repository.py
      test_contracts.py
      test_http_client.py
      test_config.py
      test_concurrency.py
    integration/
      test_registration_integration.py
  requirements.txt
  requirements-dev.txt
  README.md
```

Nessun import applicativo da user-service o event-service (`structure.md` §7.1): solo
HTTP. Moduli di supporto duplicati localmente (§7.2).

---

## 3. Responsabilità dei moduli

### `config.py`

```python
@dataclass
class Config:
    port: int
    storage_backend: str          # default "memory"
    data_dir: Path                # default Path("./data")
    user_service_url: str         # default "http://localhost:5001"
    event_service_url: str        # default "http://localhost:5002"

def load_config(port=_SENTINEL) -> Config:
    raw_port = port if port is not _SENTINEL else os.environ.get("PORT")
    if raw_port is None:
        raise ValueError("PORT environment variable is required to start the server")
    return Config(
        port=int(raw_port),
        storage_backend=os.environ.get("STORAGE_BACKEND", "memory"),
        data_dir=Path(os.environ.get("DATA_DIR", "./data")),
        user_service_url=os.environ.get("USER_SERVICE_URL", "http://localhost:5001"),
        event_service_url=os.environ.get("EVENT_SERVICE_URL", "http://localhost:5002"),
    )
```

Unico punto che legge `os.environ`; import di `app` non richiede `PORT`
(REQ-REG-F12-AC5); nessun URL hard-coded.

### `__init__.py` — Application factory

```python
def create_app(repo=None, config=None, user_client=None, event_client=None) -> Flask:
    app = Flask(__name__)
    if repo is None:
        backend = config.storage_backend if config else os.environ.get("STORAGE_BACKEND", "memory")
        data_dir = config.data_dir if config else Path(os.environ.get("DATA_DIR", "./data"))
        repo = get_repository(backend, data_dir)
    if user_client is None:
        user_client = UserServiceClient(
            (config.user_service_url if config else os.environ.get("USER_SERVICE_URL", "http://localhost:5001")),
            timeout=2.0)
    if event_client is None:
        event_client = EventServiceClient(
            (config.event_service_url if config else os.environ.get("EVENT_SERVICE_URL", "http://localhost:5002")),
            timeout=2.0)
    app.config["REGISTRATION_SERVICE"] = RegistrationService(repo, user_client, event_client)
    app.register_blueprint(registrations_bp)
    register_error_handlers(app)
    return app
```

Injection di `repo`, `user_client`, `event_client` per i test (mock con `responses`).

### `__main__.py`

```python
cfg = load_config()
application = create_app(config=cfg)
application.run(host="0.0.0.0", port=cfg.port, debug=False)  # pragma: no cover
```

Avvio Windows: `$env:PORT="5003"; $env:USER_SERVICE_URL="http://localhost:5001"; $env:EVENT_SERVICE_URL="http://localhost:5002"; py -3.12 -m app`.

### `routes.py`

Blueprint `registrations_bp`. Rotte:
`POST /api/v1/registrations`, `GET /api/v1/registrations`,
`GET /api/v1/registrations/stats`, `GET /api/v1/registrations/<id>`,
`PATCH /api/v1/registrations/<id>`, `DELETE /api/v1/registrations/<id>`,
`PUT /api/v1/registrations/<id>` (→ 405), `GET /health`.

**Ordine di registrazione delle rotte:** `/stats` deve essere registrata **prima** di
`/<id>` (o con un converter che escluda `stats`) affinché `GET /registrations/stats` non
venga interpretato come `GET /registrations/{id=stats}`. Scelta: definire la rotta
statica `/api/v1/registrations/stats` esplicitamente; Flask dà precedenza alle regole
statiche su quelle con variabile, ma l'ordine esplicito rende l'intento chiaro.

Solo livello HTTP; nessuna regola di business. Traduce le eccezioni del service in
status code via `errors.py`.

### `service.py` — RegistrationService

Riceve `repo`, `user_client`, `event_client`. Contiene REQ-REG-B01..B09:

- `create_registration(data)`: verifica utente (B01), verifica evento + stato + prezzo +
  capienza (B02/B03/B06/B05), poi sezione critica atomica duplicato+capienza+create
  (B04/B05) — vedi §5.
- `get_registration(id)`: 404 se assente.
- `list_registrations(filters, page, page_size)`: filtri `user_id`/`event_id`/`status`
  AND, `total` post-filtro.
- `patch_status(id, new_status)`: 404 se assente; transizione `confirmed→cancelled`
  (B07); `cancelled→confirmed`→422 `INVALID_STATUS_TRANSITION`; stesso stato → no-op;
  cancellazione libera il posto (il conteggio dei `confirmed` cala).
- `delete_registration(id)`: 404 se assente.
- `stats(event_id)`: evento da event-service (404→`NOT_FOUND`), `confirmed` contato
  localmente, `available = capacity - confirmed` (B08).

Le regole vivono qui; non importa backend né `requests`.

### `http_client.py` — UserServiceClient, EventServiceClient

```python
class ReferenceNotFoundError(Exception): ...        # → 422 REFERENCE_NOT_FOUND
class DependencyUnavailableError(Exception): ...     # → 503 DEPENDENCY_UNAVAILABLE

class _BaseClient:
    def __init__(self, base_url, timeout=2.0):
        self._base_url = base_url.rstrip("/"); self._timeout = timeout

    def _get(self, path):
        try:
            resp = requests.get(self._base_url + path, timeout=self._timeout)
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise DependencyUnavailableError(str(exc)) from exc
        if resp.status_code == 404:
            raise ReferenceNotFoundError(path)
        if resp.status_code >= 500 or resp.status_code != 200:
            raise DependencyUnavailableError(f"unexpected {resp.status_code}")
        return resp.json()

class UserServiceClient(_BaseClient):
    def get_user(self, user_id): return self._get(f"/api/v1/users/{user_id}")

class EventServiceClient(_BaseClient):
    def get_event(self, event_id): return self._get(f"/api/v1/events/{event_id}")
```

- **Timeout 2 s** per entrambi (REQ-REG-B01-AC2, B02-AC2). URL da `config`.
- 404 → `ReferenceNotFoundError` (→422 `REFERENCE_NOT_FOUND`); timeout / connessione
  rifiutata / 5xx / status inatteso → `DependencyUnavailableError` (→503) (REQ-REG-B09).
  `ConnectionError` copre la porta chiusa della suite di resilienza (harness
  `CLOSED_PORT`, che azzera **tutti** gli `*_SERVICE_URL`).
- `EVENT_NOT_OPEN` e le regole di stato/prezzo/capienza sono nel `service.py`, non nel
  client: il client restituisce il dict evento e il service lo interpreta.

### `validators.py`

- `validate_body_is_object`
- `validate_registration_create(data)` — required `user_id`/`event_id` uuid, nessun
  altro campo (`additionalProperties:false`), no coercizione
- `validate_registration_patch(data)` — required `status`, solo `status`, enum
  `confirmed`/`cancelled`
- `validate_stats_query(args)` — `event_id` presente e uuid, altrimenti 422
- `validate_list_filters(args)` — `status` enum se presente; `user_id`/`event_id` uuid
  se presenti

### `errors.py`

```python
ERROR_CODES = {
    "VALIDATION_ERROR": 422,
    "REFERENCE_NOT_FOUND": 422,
    "EVENT_NOT_OPEN": 422,
    "INVALID_STATUS_TRANSITION": 422,
    "ALREADY_REGISTERED": 409,
    "EVENT_FULL": 409,
    "NOT_FOUND": 404,
    "METHOD_NOT_ALLOWED": 405,
    "MALFORMED_JSON": 400,
    "DEPENDENCY_UNAVAILABLE": 503,
}
```
`make_error_response` come user/event: `details` sempre dict, unico punto di costruzione.

### `models.py`

```python
def new_registration_record(user_id, event_id, amount, now) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "event_id": event_id,
        "amount": amount,             # copiato da event.price (REQ-REG-B06)
        "status": "confirmed",        # sempre confirmed alla creazione (REQ-REG-F02-AC3)
        "created_at": now,
        "updated_at": now,
    }

def registration_to_dict(record) -> dict:
    return {k: record[k] for k in
        ("id","user_id","event_id","amount","status","created_at","updated_at")}
```

`utcnow_iso()` con precisione al microsecondo (come user/event).

---

## 4. Flusso di creazione (REQ-REG-B01..B06)

```
POST /api/v1/registrations
1. body oggetto JSON con user_id/event_id uuid?   no → 422 VALIDATION_ERROR
2. user_client.get_user(user_id)
     ├─ 404              → 422 REFERENCE_NOT_FOUND (B01)
     └─ timeout/refused/5xx → 503 DEPENDENCY_UNAVAILABLE (B09)
3. event = event_client.get_event(event_id)
     ├─ 404              → 422 REFERENCE_NOT_FOUND (B02)
     └─ timeout/refused/5xx → 503 DEPENDENCY_UNAVAILABLE (B09)
4. event.status == "published"?                    no → 422 EVENT_NOT_OPEN (B03)
5. amount = event.price                            (B06)
   capacity = event.capacity                       (per B05)
6. ── SEZIONE CRITICA (repo lock) ──               (B04 + B05 + create atomici)
     a. esiste registrazione confirmed per (user_id,event_id)? sì → 409 ALREADY_REGISTERED
     b. confermate per event_id >= capacity?                    sì → 409 EVENT_FULL
     c. crea record confirmed, amount, timestamp; persiste
   ── FINE SEZIONE CRITICA ──
7. 201 + Location + Registration
```

Le chiamate HTTP (passi 2–3) avvengono **fuori** dal lock (non si tiene il lock durante
I/O di rete). Il controllo duplicato, il conteggio capienza e la scrittura (passo 6)
sono un'unica sezione critica per evitare overselling e doppie iscrizioni sotto
concorrenza (REQ-REG-B04-AC3, B05-AC5). Nessuna mutazione se un controllo fallisce.

---

## 5. Sincronizzazione concorrente (cuore del design)

Flask serve richieste in thread concorrenti. Le regole B04 (no doppio confirmed) e B05
(capienza) sono soggette a race condition classiche: due richieste simultanee per
l'ultimo posto, o due iscrizioni simultanee dello stesso utente, potrebbero entrambe
superare un controllo eseguito prima della scrittura.

**Strategia: sezione critica unica nel repository.** Il repository espone un metodo di
alto livello che esegue *conteggio + controllo duplicato + inserimento* sotto il proprio
`threading.RLock()`:

```python
class AbstractRegistrationRepository(ABC):
    @abstractmethod
    def create_if_allowed(self, user_id, event_id, capacity, make_record) -> dict:
        """Sotto lock: se esiste già un confirmed per (user_id,event_id) → ALREADY_REGISTERED;
        se confirmed(event_id) >= capacity → EVENT_FULL; altrimenti crea e restituisce il record."""
```

- `make_record` è una callback che costruisce il record (con `amount`/timestamp già
  calcolati dal service) — il repository non conosce le regole di dominio, solo il
  vincolo di atomicità.
- Il repository solleva `AlreadyRegisteredError` / `EventFullError`; il service le
  traduce in 409.
- Il conteggio dei `confirmed` e il controllo duplicato leggono lo stato **dentro** lo
  stesso lock che protegge la scrittura: nessuna finestra tra check e write.

In alternativa, il service può tenere il lock del repository esplicitamente attorno a
`count_confirmed` + `exists_confirmed` + `create`. Si sceglie il metodo
`create_if_allowed` per mantenere l'atomicità **dentro** il repository (dove vive il
lock) ed evitare che il service manipoli il lock (coerente con user-service design §10).

**PATCH cancellazione** libera il posto semplicemente cambiando `status` a `cancelled`
sotto lock; il successivo `count_confirmed` rifletterà il posto liberato. Anche la
transizione (lettura stato corrente + scrittura) avviene sotto lock per coerenza.

Un solo processo per servizio (la suite avvia un processo per istanza); non è promesso
coordinamento tra processi sullo stesso file. `test_concurrency.py` prova con
`threading.Thread` che, su un evento con capacità 1 e due create simultanee, esattamente
una riesce (201) e l'altra ottiene `EVENT_FULL` (REQ-REG-T01-AC6).

---

## 6. Interfaccia repository e tre backend (REQ-REG-F13)

### AbstractRegistrationRepository

```python
class AbstractRegistrationRepository(ABC):
    @abstractmethod
    def create_if_allowed(self, user_id, event_id, capacity, make_record) -> dict: ...
    @abstractmethod
    def get(self, reg_id) -> dict | None: ...
    @abstractmethod
    def list_all(self, filters) -> list[dict]: ...       # user_id, event_id, status
    @abstractmethod
    def set_status(self, reg_id, new_status, now) -> dict | None: ...  # transizione sotto lock
    @abstractmethod
    def delete(self, reg_id) -> bool: ...
    @abstractmethod
    def count_confirmed(self, event_id) -> int: ...      # per stats (B08)
```

`set_status` applica la transizione atomicamente (legge stato, valida `confirmed→
cancelled` a livello service prima di chiamare, aggiorna `updated_at`). La validazione
della transizione (B07) resta nel service; il repository esegue la scrittura sotto lock.

### MemoryRegistrationRepository
- dict `{id: record}`, `RLock` per istanza. `create_if_allowed`, `set_status`,
  `count_confirmed` sotto lock.

### JsonRegistrationRepository
- `DATA_DIR/registrations.json`, lettura completa all'apertura, scrittura atomica
  (tmp + `os.replace()`), `RLock` per istanza. Persistenza verificata su riapertura.

### SqliteRegistrationRepository
```sql
CREATE TABLE IF NOT EXISTS registrations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    amount REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reg_event_status ON registrations (event_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_reg_user_event_confirmed
    ON registrations (user_id, event_id) WHERE status = 'confirmed';
```
- connessione condivisa `check_same_thread=False`, `RLock` per istanza, write in
  `with conn:`. L'indice parziale `WHERE status='confirmed'` fornisce una rete di
  sicurezza a livello DB contro il doppio confirmed (B04): `IntegrityError` →
  `AlreadyRegisteredError`. La capienza (B05) è comunque verificata sotto lock nel
  metodo `create_if_allowed`. `registrations.db` in `DATA_DIR` escluso via `data/`.

### `get_repository(backend, data_dir)`
Factory con import locali (come user-service), rami memory/json/sqlite, `ValueError` per
backend sconosciuto.

---

## 7. Error handlers Flask

`@app.errorhandler(400|404|405)` → formato `Error` con `details: {}`. Il 400 intercetta
il `BadRequest` di Flask sul JSON non valido. Il 405 di `PUT /registrations/{id}` può
essere gestito con una rotta esplicita che restituisce `make_error_response(
"METHOD_NOT_ALLOWED", ..., status=405)`, così il corpo è conforme e il contratto
(che dichiara 405 per PUT) è soddisfatto (REQ-REG-F08).

---

## 8. Timestamp (REQ-REG-F10)

`utcnow_iso()` microsecondo. `created_at` immutabile; `updated_at` aggiornato su PATCH
che cambia stato; invariato su no-op. Test con `monkeypatch` su `utcnow_iso`.

---

## 9. Adattamento risposta per `assert_matches_contract`

Come user/event: `flask_to_contract_dict(resp)` → `{status_code, headers, json}` con
`resp.get_json(silent=True)`. Per DELETE 204 body `None`. `validator.py` non modificato.
Per PUT 405, il contratto dichiara l'operazione `putRegistrationNotAllowed` con risposta
405 → `assert_matches_contract("registration","PUT","/api/v1/registrations/<id>", ...)`
è valido.

---

## 10. Strategia di test (REQ-REG-T01/T02)

### Unit (`tests/unit/`)

- **`test_routes.py`** — Flask test client, user+event mockati con `responses`. Ogni
  endpoint, status code, `Location`, 400/404/405/409/422/503. Contratto via
  `flask_to_contract_dict`.
- **`test_service.py`** — `RegistrationService` con `MemoryRegistrationRepository` +
  `responses`: B01 (user 404), B02 (event 404), B03 (EVENT_NOT_OPEN), B04
  (ALREADY_REGISTERED), B05 (EVENT_FULL), B06 (amount=price), B07 (cancel frees seat,
  reactivation→422, no-op), B08 (stats present/missing), B09 (timeout/refused/5xx),
  no-mutazione su errore, `updated_at` (monkeypatch).
- **`test_repository.py`** — parametrizzato sui **tre** backend con `tmp_path`:
  `create_if_allowed`, get, list_all con filtri, set_status, delete, count_confirmed;
  riapertura dati json/sqlite.
- **`test_http_client.py`** — `UserServiceClient`/`EventServiceClient` con `responses`:
  200, 404, 5xx, `ConnectionError`/`Timeout`.
- **`test_contracts.py`** — `assert_matches_contract` per: `health`,
  `createRegistration`, `listRegistrations`, `registrationStats`, `getRegistration`,
  `updateRegistration` (PATCH), `deleteRegistration`, `putRegistrationNotAllowed` (405).
- **`test_config.py`** — `load_config()` senza PORT → ValueError; default dei due URL;
  import senza PORT.
- **`test_concurrency.py`** — `threading.Thread`: capacità 1, due create simultanee →
  esattamente un 201 e un `EVENT_FULL`; due create simultanee stesso utente → un 201 e
  un `ALREADY_REGISTERED` (REQ-REG-T01-AC6).

Ogni test tracciato con `@pytest.mark.req("REQ-REG-…")` o id nel nome/docstring.

### Integrazione propria (`tests/integration/`)

`test_registration_integration.py` avvia **user**, **event** e **registration** reali su
porte libere (REQ-REG-T02):

```python
@pytest.fixture(scope="module")
def live_stack():
    up = free_port(); ep = free_port(); rp = free_port()
    user = start("user-service", {"PORT": up, "STORAGE_BACKEND": "memory"})
    try:
        wait_health(up)
        event = start("event-service", {"PORT": ep, "STORAGE_BACKEND": "memory",
                                        "USER_SERVICE_URL": url(up)})
        try:
            wait_health(ep)
            reg = start("registration-service", {"PORT": rp, "STORAGE_BACKEND": "memory",
                        "USER_SERVICE_URL": url(up), "EVENT_SERVICE_URL": url(ep)})
            try:
                wait_health(rp)
                yield {...}
            finally: terminate(reg)
        finally: terminate(event)
    finally: terminate(user)
```

Casi (REQ-REG-T02):
1. **positivo**: crea organizer + attendee + evento pubblicato (via event reale, che
   verifica l'organizer su user reale) → registra → 201 `confirmed`, `amount == price`.
2. **riferimento inesistente**: `user_id` (o `event_id`) casuale → 422
   `REFERENCE_NOT_FOUND`.
3. **dipendenza spenta**: registration con `USER_SERVICE_URL`/`EVENT_SERVICE_URL` su
   porta chiusa → POST → 503 `DEPENDENCY_UNAVAILABLE`.

Cleanup garantito con `try/finally` annidati e `kill()` di fallback.

### Comandi (Windows, `py -3.12`)

```powershell
py -3.12 -m pytest tests/unit -v --cov=app --cov-report=term-missing --cov-fail-under=80
py -3.12 -m pytest tests/integration -v
```

Coverage ≥ 80% sul package `app`. `__main__.py` con `# pragma: no cover`.

---

## 11. services.yaml e avvio (Windows)

Al task di preparazione ambiente, `Exam/techconf-exam/services.yaml` viene esteso per
dichiarare **user, event e registration** (registration ha bisogno di entrambe le
dipendenze avviate dalla suite):

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

Con i tre servizi dichiarati la suite può eseguire IT-R01..IT-R10 e la journey IT-J01.
La suite inietta `PORT` (15003) e gli `*_SERVICE_URL` (→15001/15002). Aggiornamento nel
relativo task.

---

## 12. Matrice requisiti → componenti → verifiche

| Requisito | Componente principale | Verifiche |
|---|---|---|
| REQ-REG-F01 | `routes.py` GET /health | `test_routes::health` + contratto |
| REQ-REG-F02 | `routes.py` POST + `service.create_registration` | `test_routes`, `test_service`, `test_contracts`, IT-R01 |
| REQ-REG-F03 | `validators.validate_registration_create` | `test_routes` (422), `test_service` |
| REQ-REG-F04 | `service.get_registration` | `test_routes`, `test_contracts`, IT-R01 |
| REQ-REG-F05 | `pagination.py`, `service.list_registrations` | `test_routes`, `test_contracts` |
| REQ-REG-F06 | `service.patch_status` | `test_service`, `test_contracts`, IT-R07 |
| REQ-REG-F07 | `service.delete_registration` | `test_routes`, `test_contracts` |
| REQ-REG-F08 | rotta PUT → 405 | `test_routes`, `test_contracts` (put405), IT-R09 |
| REQ-REG-F09 | error handlers 404/405 | `test_routes` |
| REQ-REG-F10 | `models.utcnow_iso`, `service` | `test_service` (monkeypatch) |
| REQ-REG-F11 | `errors.make_error_response` | `test_routes` |
| REQ-REG-F12 | `config.load_config` | `test_config` |
| REQ-REG-F13 | `repository.py`, `backends/` | `test_repository` (3 backend) |
| REQ-REG-B01 | `http_client.UserServiceClient`, `service` | `test_http_client`, `test_service`, IT-R02 |
| REQ-REG-B02 | `http_client.EventServiceClient`, `service` | `test_http_client`, `test_service`, IT-R03 |
| REQ-REG-B03 | `service` (event.status) | `test_service`, IT-R04 |
| REQ-REG-B04 | `repo.create_if_allowed` (duplicato) | `test_service`, `test_concurrency`, IT-R05, IT-J01 |
| REQ-REG-B05 | `repo.create_if_allowed` (capienza) | `test_service`, `test_concurrency`, IT-R06, IT-J01 |
| REQ-REG-B06 | `service` (amount=price) | `test_service`, IT-R01 |
| REQ-REG-B07 | `service.patch_status`, `repo.set_status` | `test_service`, IT-R07, IT-J01 |
| REQ-REG-B08 | `service.stats`, `repo.count_confirmed` | `test_service`, `test_contracts` (stats), IT-R08, IT-J01 |
| REQ-REG-B09 | `http_client` (timeout/refused/5xx) | `test_http_client`, `test_service`, IT-R10 |
| REQ-REG-T01 | intera suite unit | coverage ≥80%, contratto per operazione, 3 backend, concorrenza |
| REQ-REG-T02 | `tests/integration/test_registration_integration.py` | positivo, 422, 503 con 3 servizi reali |
