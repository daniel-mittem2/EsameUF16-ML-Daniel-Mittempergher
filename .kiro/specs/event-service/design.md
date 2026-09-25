# event-service — Design

**Contratto di riferimento:** `Exam/techconf-exam/contracts/openapi/event-service.yaml`
**Requirements:** `.kiro/specs/event-service/requirements.md`
**Standard globali:** `.kiro/steering/structure.md` · `.kiro/steering/tech.md` · `.kiro/steering/platform-standards.md`
**Versione spec:** 1.0 — 2026-09-25
**Workflow:** Requirements-First (fase 2 di 3). Tasks NON ancora prodotti; nessun codice applicativo scritto.

---

## 1. Riferimento al contratto OpenAPI

Il contratto `event-service.yaml` è la fonte di verità. Punti critici che guidano il design:

| Elemento | Dettaglio rilevante |
|---|---|
| `EventCreate` | `additionalProperties: false`; required: `title`, `organizer_id`, `venue`, `city`, `start_date`, `end_date`, `capacity`, `price` |
| `EventUpdate` | `additionalProperties: false`; **tutti** i campi opzionali (usato da PATCH) |
| `Event` (response) | `additionalProperties: false`; 12 campi required incluso `status`, `created_at`, `updated_at` |
| `description` | `nullable: true` — unico campo che accetta `null` |
| `status` | `enum: [draft, published, cancelled]`; default `draft` |
| `capacity` | `integer`, min 1, max 10000 |
| `price` | `number`, min 0 |
| `title` | `string`, minLength 3, maxLength 120 |
| `venue`/`city` | max 100 / max 60 |
| `start_date`/`end_date` | `format: date` (`YYYY-MM-DD`) |
| `Error` | `additionalProperties: false` su `error`; `details` è `additionalProperties: true` |
| `Health` | `additionalProperties: false`; `status: enum: [ok]`, `service: string` |
| Paginazione | `page` min 1 default 1; `page_size` min 1 max 100 default 20 |

Il contratto usa `nullable: true` per `description` (OpenAPI 3.0). Il `validator.py` lo
traduce in `{"type": ["string", "null"]}` prima della validazione Draft 7: basta
restituire `null` (non `""`) quando `description` è assente.

**Codici di risposta dichiarati per operazione:** POST 201/400/422/503; GET list
200/422; GET/{id} 200/404; PUT 200/404/422/503; PATCH 200/404/422/503; DELETE 204/404.
Il 405 (metodo non previsto) e alcuni 400/404 di infrastruttura non sono elencati per
ogni operazione: per quei casi i test **non** usano `assert_matches_contract` (vedi §12).

---

## 2. Struttura dei moduli

Coerente con `structure.md` §7.3. A differenza di user-service, **è presente**
`http_client.py` perché event-service chiama user-service (REQ-EVT-B01/B02/B05).

```
services/event-service/
  app/
    __init__.py          # create_app(repo=None, config=None, user_client=None) — Flask factory
    __main__.py          # entry point: load_config() → create_app(config=cfg) → app.run
    config.py            # load_config() → Config (port, storage_backend, data_dir, user_service_url)
    routes.py            # Blueprint: parsing, validazione HTTP, serializzazione, Location
    service.py           # EventService: regole REQ-EVT-B01..B06, orchestrazione
    repository.py        # AbstractEventRepository (ABC) + get_repository()
    backends/
      __init__.py
      memory.py          # MemoryEventRepository
      json_backend.py    # JsonEventRepository
      sqlite_backend.py  # SqliteEventRepository
    http_client.py       # UserServiceClient: GET /api/v1/users/{id}, timeout 2s, 404→422, 5xx/timeout/refused→503
    validators.py        # validazione input (campi, tipi, date, enum, body object)
    errors.py            # costanti codici errore + make_error_response()
    pagination.py        # parse_pagination_params(), paginate()
    models.py            # new_event_record(), event_to_dict(), utcnow_iso()
  tests/
    unit/
      test_routes.py
      test_service.py
      test_repository.py
      test_contracts.py
      test_http_client.py
      test_config.py
    integration/
      test_event_integration.py
  requirements.txt
  requirements-dev.txt
  README.md
```

**Nessun import applicativo da user-service** (`structure.md` §7.1): la comunicazione
è solo HTTP via `http_client.py`. I moduli di supporto (`errors`, `pagination`,
`models`, `validators`) sono duplicati localmente, non importati (§7.2).

---

## 3. Responsabilità dei moduli

### `config.py`

Legge **tutte** le variabili d'ambiente in un solo punto (REQ-EVT-F13-AC4).

```python
from dataclasses import dataclass
from pathlib import Path
import os

@dataclass
class Config:
    port: int
    storage_backend: str          # "memory" | "json" | "sqlite", default "memory"
    data_dir: Path                # default Path("./data")
    user_service_url: str         # default "http://localhost:5001"

_SENTINEL = object()

def load_config(port=_SENTINEL) -> Config:
    raw_port = port if port is not _SENTINEL else os.environ.get("PORT")
    if raw_port is None:
        raise ValueError("PORT environment variable is required to start the server")
    return Config(
        port=int(raw_port),
        storage_backend=os.environ.get("STORAGE_BACKEND", "memory"),
        data_dir=Path(os.environ.get("DATA_DIR", "./data")),
        user_service_url=os.environ.get("USER_SERVICE_URL", "http://localhost:5001"),
    )
```

- Importare il package `app` **non** richiede `PORT` (REQ-EVT-F13-AC5): `load_config()`
  è chiamata solo in `__main__.py`.
- Nessun altro modulo legge `os.environ`; l'URL di user-service non è mai hard-coded
  (REQ-EVT-F13-AC4, penalità §8 di Exam.MD).

### `__init__.py` — Application factory

```python
def create_app(repo=None, config=None, user_client=None) -> Flask:
    app = Flask(__name__)
    if repo is None:
        backend = config.storage_backend if config else os.environ.get("STORAGE_BACKEND", "memory")
        data_dir = config.data_dir if config else Path(os.environ.get("DATA_DIR", "./data"))
        repo = get_repository(backend, data_dir)
    if user_client is None:
        base_url = config.user_service_url if config else os.environ.get("USER_SERVICE_URL", "http://localhost:5001")
        user_client = UserServiceClient(base_url, timeout=2.0)
    app.config["EVENT_SERVICE"] = EventService(repo, user_client)
    app.register_blueprint(events_bp)
    register_error_handlers(app)
    return app
```

La factory accetta `repo` e `user_client` opzionali per **dependency injection nei
test**: i test unitari passano un `MemoryEventRepository` e un `UserServiceClient`
reale con le richieste mockate da `responses`, oppure un doppio di test.

| Contesto | Come si usa `create_app` |
|---|---|
| Produzione / suite | `create_app(config=load_config())` poi `app.run(...)` |
| Test unitari routes | `create_app(repo=MemoryEventRepository(), user_client=UserServiceClient("http://user"))` + `responses` |
| Test integrazione propri | sottoprocesso reale, `PORT`/`USER_SERVICE_URL` iniettati |

### `__main__.py`

```python
from app.config import load_config
from app import create_app

cfg = load_config()                        # valida PORT qui
application = create_app(config=cfg)
application.run(host="0.0.0.0", port=cfg.port, debug=False)  # pragma: no cover
```

Avvio Windows sviluppo: `$env:PORT="5002"; $env:USER_SERVICE_URL="http://localhost:5001"; py -3.12 -m app`.

### `routes.py`

Blueprint `events_bp`. Solo livello HTTP:

- parsing JSON body (400 se non parseable, delega error handler)
- validazione formato/tipo (delega a `validators.py`)
- estrazione/validazione query param (delega a `pagination.py`)
- chiamata a `EventService` (da `current_app.config["EVENT_SERVICE"]`)
- serializzazione con `jsonify()`, header `Location` su 201
- traduzione delle eccezioni del service in status code via `errors.py`

Nessuna regola di business qui. Le rotte registrate:
`POST /api/v1/events`, `GET /api/v1/events`, `GET /api/v1/events/<id>`,
`PUT /api/v1/events/<id>`, `PATCH /api/v1/events/<id>`, `DELETE /api/v1/events/<id>`,
`GET /health`.

### `service.py` — EventService

Riceve `repo` e `user_client` via costruttore. Contiene **tutte** le regole
REQ-EVT-B01..B06:

- `create_event(data)`: valida (già fatto in routes), verifica organizzatore
  (B01/B02/B05), applica default (`status="draft"`, `description=None`), genera UUID
  v4 e timestamp, chiama `repo.create`.
- `get_event(id)`: 404 se assente (nessuna chiamata HTTP).
- `list_events(filters, page, page_size)`: filtri `status`/`city` AND (B06), `total`
  post-filtro.
- `replace_event(id, data)` (PUT): 404 se assente; se `organizer_id` presente verifica
  organizzatore; enforce transizione `status` (B04); mantiene `id`/`created_at`,
  aggiorna `updated_at`.
- `update_event(id, data)` (PATCH): recupera **per primo** (404 anche per `{}`);
  applica solo i campi presenti; ri-valida `end_date≥start_date` sull'effettivo (B03);
  ri-verifica organizzatore se `organizer_id` cambia; enforce transizione (B04);
  empty PATCH → invariato, `updated_at` non aggiornato.
- `delete_event(id)`: 404 se assente.

Le regole vivono qui, mai in `routes.py` o `repository.py` (`structure.md` §7.3).
`service.py` non importa i backend né `requests` direttamente: usa l'ABC del
repository e l'interfaccia di `http_client.py`.

### `http_client.py` — UserServiceClient

Isola la chiamata a user-service (REQ-EVT-B01/B02/B05), mockabile con `responses`.

```python
import requests

class ReferenceNotFoundError(Exception): ...      # → 422 REFERENCE_NOT_FOUND
class InvalidOrganizerError(Exception): ...        # → 422 INVALID_ORGANIZER
class DependencyUnavailableError(Exception): ...   # → 503 DEPENDENCY_UNAVAILABLE

class UserServiceClient:
    def __init__(self, base_url: str, timeout: float = 2.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def get_user(self, user_id: str) -> dict:
        url = f"{self._base_url}/api/v1/users/{user_id}"
        try:
            resp = requests.get(url, timeout=self._timeout)
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise DependencyUnavailableError(str(exc)) from exc
        if resp.status_code == 404:
            raise ReferenceNotFoundError(user_id)
        if resp.status_code >= 500:
            raise DependencyUnavailableError(f"user-service {resp.status_code}")
        if resp.status_code != 200:
            raise DependencyUnavailableError(f"unexpected {resp.status_code}")
        return resp.json()

    def verify_organizer(self, user_id: str) -> dict:
        user = self.get_user(user_id)
        if user.get("role") != "organizer":
            raise InvalidOrganizerError(user_id)
        return user
```

- **Timeout 2 s** hard-coded nel default del costruttore, alimentato da
  `Config.user_service_url` (REQ-EVT-B01-AC2, platform standards).
- Mappatura errori: 404 → `ReferenceNotFoundError` (→422); timeout/connessione
  rifiutata/5xx → `DependencyUnavailableError` (→503) (REQ-EVT-B05).
  `requests.ConnectionError` copre la porta chiusa usata dalla suite di resilienza
  (harness `CLOSED_PORT`).
- `verify_organizer` combina esistenza (B01) e ruolo (B02).
- Il service traduce queste eccezioni in codici HTTP tramite `errors.py`.

### `validators.py`

Funzioni pure, testabili senza Flask:

- `validate_body_is_object(data)` → 422 se non dict (REQ-EVT-F03-AC10)
- `validate_event_create(data)` → lista errori (required + tipi + range + enum + date)
- `validate_event_update(data)` → lista errori (tutti opzionali, additionalProperties
  false, REQ-EVT-F04-AC2)
- `validate_date(value)` → bool (`YYYY-MM-DD` valido)
- `validate_dates_coherent(start, end)` → `end ≥ start` (REQ-EVT-B03)
- niente coercizione di tipo (REQ-EVT-F03-AC11): un `"100"` string per `capacity` → 422

### `errors.py`

```python
ERROR_CODES = {
    "VALIDATION_ERROR": 422,
    "REFERENCE_NOT_FOUND": 422,
    "INVALID_ORGANIZER": 422,
    "INVALID_STATUS_TRANSITION": 422,
    "NOT_FOUND": 404,
    "METHOD_NOT_ALLOWED": 405,
    "MALFORMED_JSON": 400,
    "DEPENDENCY_UNAVAILABLE": 503,
}

def make_error_response(code, message, details=None, status=None):
    body = {"error": {"code": code, "message": message, "details": details or {}}}
    return jsonify(body), (status or ERROR_CODES.get(code, 422))
```

`details` sempre dict (mai `null`). Unico punto di costruzione degli errori
(REQ-EVT-F12).

### `models.py`

```python
def new_event_record(data: dict, now: str) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "title": data["title"],
        "description": data.get("description"),     # None se assente
        "organizer_id": data["organizer_id"],
        "venue": data["venue"],
        "city": data["city"],
        "start_date": data["start_date"],
        "end_date": data["end_date"],
        "capacity": data["capacity"],
        "price": data["price"],
        "status": data.get("status", "draft"),       # REQ-EVT-B04-AC3
        "created_at": now,
        "updated_at": now,
    }

def event_to_dict(record: dict) -> dict:
    return {k: record[k] for k in (
        "id","title","description","organizer_id","venue","city",
        "start_date","end_date","capacity","price","status",
        "created_at","updated_at")}

def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
```

---

## 4. Verifica dell'organizzatore (flusso REQ-EVT-B01/B02/B05)

Ordine per POST/PUT/PATCH quando `organizer_id` è presente/cambia (REQ-EVT-F02-AC7):

```
1. body è un oggetto JSON?           no → 422 VALIDATION_ERROR (routes/validators)
2. validazione campo-per-campo       fail → 422 VALIDATION_ERROR
   (incl. end_date ≥ start_date, B03)
3. user_client.verify_organizer(organizer_id)
     ├─ requests.get(USER_SERVICE_URL/api/v1/users/{id}, timeout=2s)
     ├─ 404                → ReferenceNotFoundError → 422 REFERENCE_NOT_FOUND (B01)
     ├─ 200 & role≠organizer → InvalidOrganizerError → 422 INVALID_ORGANIZER (B02)
     ├─ 200 & role=organizer → ok
     └─ timeout/refused/5xx → DependencyUnavailableError → 503 (B05)
4. crea/aggiorna record, timestamp, persistenza
```

Nessuna chiamata HTTP viene emessa se la validazione di campo fallisce
(REQ-EVT-B01-AC4): un input malformato non genera 503 fuorvianti. Il 404 della
dipendenza è **riferimento** (422), non **disponibilità** (503) (REQ-EVT-B05-AC5).

GET (lista e per id) e DELETE non chiamano user-service (REQ-EVT-F05-AC4,
REQ-EVT-F06-AC7, REQ-EVT-F09-AC4).

---

## 5. Transizioni di stato (REQ-EVT-B04)

Insieme ammesso: `draft→published`, `draft→cancelled`, `published→cancelled`.

```python
_ALLOWED = {("draft","published"), ("draft","cancelled"), ("published","cancelled")}

def check_transition(current: str, new: str):
    if new == current:
        return                      # no-op: stato invariato (REQ-EVT-B04-AC5)
    if (current, new) not in _ALLOWED:
        raise InvalidStatusTransitionError(current, new)   # → 422
```

- **Create (POST):** `status` iniziale è un valore fornito dal client (default
  `draft`), validato solo contro l'enum del contratto — non è una transizione
  (REQ-EVT-B04-AC3).
- **PUT/PATCH:** se `status` inviato è diverso da quello memorizzato → transizione,
  soggetta a `check_transition`. Se uguale o assente → no-op, lo stato resta invariato
  e non si genera `INVALID_STATUS_TRANSITION` (REQ-EVT-B04-AC5, gestione esplicita
  dello stato invariato).
- Trace IT-E05: `draft→published` 200; `published→draft` 422
  `INVALID_STATUS_TRANSITION`. La fixture `make_event(status="published")` di conftest
  pubblica via PATCH: il flusso deve funzionare.

---

## 6. PUT vs PATCH — implementazione

**PUT** (schema `EventCreate`, tutti i required presenti):
1. valida il body come POST (REQ-EVT-F03)
2. recupera il record (404 se assente)
3. se `organizer_id` presente → verifica organizzatore (B01/B02/B05)
4. calcola transizione di stato rispetto allo stored (B04)
5. sostituisce i campi mutable; `description`/`status` assenti → default POST-style
6. mantiene `id`/`created_at`, aggiorna `updated_at`

**PATCH** (schema `EventUpdate`, tutti opzionali):
1. recupera il record **per primo** (404 anche per `{}`, REQ-EVT-F04-AC5)
2. valida che il body sia dict; rifiuta chiavi sconosciute esplicitamente
   (`additionalProperties:false` non è automatico, va implementato)
3. se body `{}` → ritorna invariato, `updated_at` non aggiornato (REQ-EVT-F04-AC6)
4. altrimenti: valida i campi presenti; ricalcola `end_date≥start_date` sull'effettivo
   (B03); se `organizer_id` cambia → verifica organizzatore; enforce transizione (B04);
   applica i campi, aggiorna `updated_at`

---

## 7. Error handlers Flask

```python
@app.errorhandler(400)  # JSON malformato
@app.errorhandler(404)  # path sconosciuto / risorsa mancante
@app.errorhandler(405)  # metodo non previsto
```

Ogni handler produce il formato `Error` con `details: {}` (REQ-EVT-F10, F12). Il 400
intercetta il `BadRequest` di Flask quando il body non è JSON valido. I 404 per id
inesistente sono generati dal service e tradotti in `NOT_FOUND`.

---

## 8. Timestamp (REQ-EVT-F11)

`utcnow_iso()` con precisione al microsecondo (`%Y-%m-%dT%H:%M:%S.%fZ`), come
user-service, così due operazioni ravvicinate producono timestamp distinti senza
`time.sleep`. `created_at` immutabile; `updated_at` aggiornato su PUT e PATCH non
vuoto, invariato su PATCH `{}`. I test iniettano `utcnow_iso` via `monkeypatch`.

---

## 9. Interfaccia repository e tre backend (REQ-EVT-F14)

### AbstractEventRepository

```python
class AbstractEventRepository(ABC):
    @abstractmethod
    def create(self, record: dict) -> dict: ...
    @abstractmethod
    def get(self, event_id: str) -> dict | None: ...
    @abstractmethod
    def list_all(self, filters: dict) -> list[dict]: ...   # filtri status, city
    @abstractmethod
    def update(self, event_id: str, changes: dict) -> dict | None: ...
    @abstractmethod
    def delete(self, event_id: str) -> bool: ...
```

Nessun `get_by_email`-equivalente: event non ha vincoli di unicità. `list_all`
applica i filtri `status`/`city`; la paginazione è del chiamante.

### MemoryEventRepository
- dict in-memoria `{id: record}`, `threading.RLock()` per istanza a protezione di
  letture/scritture (Flask serve in thread concorrenti — vedi §10).

### JsonEventRepository
- `DATA_DIR/events.json` (lista di record); lettura completa all'apertura, scrittura
  atomica con file temporaneo + `os.replace()`; `RLock` per istanza; `DATA_DIR` creato
  se assente. Persistenza verificata riaprendo il file (REQ-EVT-F14-AC2).

### SqliteEventRepository
```sql
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    organizer_id TEXT NOT NULL,
    venue TEXT NOT NULL,
    city TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    capacity INTEGER NOT NULL,
    price REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```
- connessione condivisa `check_same_thread=False`, `RLock` per istanza, ogni write in
  `with conn:`; `DATA_DIR/events.db` escluso da git via `data/`. Persistenza verificata
  su riapertura (REQ-EVT-F14-AC3).

### `get_repository(backend, data_dir)`
Factory con import locali dei backend (come user-service `repository.py`), rami
`memory`/`json`/`sqlite`, `ValueError` per backend sconosciuto. `service.py` riceve il
repo per injection e non importa mai i backend (REQ-EVT-F14-AC4).

---

## 10. Sincronizzazione concorrente

Flask serve richieste in thread concorrenti. Event-service non ha vincoli di unicità
(nessun equivalente dell'email), ma le operazioni read-modify-write su PATCH/PUT
(recupero record → calcolo transizione → scrittura) devono essere coerenti. Ogni
backend mantiene un `threading.RLock()` per istanza; le sequenze check-then-write nel
repository avvengono sotto il lock. Il `service.py` resta privo di logica di lock (vive
nel repository). Un solo processo per servizio (la suite avvia un processo per istanza);
non è promesso coordinamento tra processi sullo stesso file.

---

## 11. Adattamento risposta per `assert_matches_contract`

Come user-service (design §11): il Flask test client non espone `.json()` callable, si
costruisce il dizionario accettato dal validator:

```python
def flask_to_contract_dict(resp) -> dict:
    return {"status_code": resp.status_code,
            "headers": dict(resp.headers),
            "json": resp.get_json(silent=True)}
```

Uso: `assert_matches_contract("event", "POST", "/api/v1/events", flask_to_contract_dict(resp))`.
Per DELETE 204 il body è `None` e il validator non valida il corpo (schema assente per
204). `validator.py` **non** viene modificato.

---

## 12. Codici non elencati per operazione

- **405** (metodo non previsto, es. `POST /api/v1/events/{id}`): generato da Flask; i
  test verificano `status_code == 405` e il corpo `Error` manualmente, **senza**
  `assert_matches_contract` (405 non è nel contratto delle singole operazioni).
- **400** (JSON malformato) su POST è dichiarato nel contratto; su PATCH/PUT il 400 è
  gestito dall'handler globale e verificato manualmente dove non dichiarato.
- Il validator valida solo le risposte previste dal contratto; le eccezioni di
  infrastruttura si verificano direttamente.

---

## 13. Strategia di test (REQ-EVT-T01/T02)

### Unit (`tests/unit/`)

- **`test_routes.py`** — `create_app(repo=MemoryEventRepository(), user_client=...)`
  + `responses` per mockare user-service. Copre ogni endpoint, status code, header
  `Location`, casi 400/404/405/422/503. Test di contratto via `flask_to_contract_dict`.
- **`test_service.py`** — `EventService` con `MemoryEventRepository` e un
  `UserServiceClient` con `responses`. Copre B01..B06, PUT/PATCH semantics, empty PATCH,
  transizioni, `updated_at` (monkeypatch su `utcnow_iso`), no-mutazione in caso di
  errore.
- **`test_repository.py`** — parametrizzato sui **tre** backend con `tmp_path` per
  json/sqlite (REQ-EVT-T01-AC3): create, get, list_all con filtri, update, delete,
  riapertura dati per json/sqlite.
- **`test_http_client.py`** — `UserServiceClient` con `responses`: 200+organizer (ok),
  200+ruolo errato (`InvalidOrganizerError`), 404 (`ReferenceNotFoundError`), 5xx e
  `ConnectionError`/`Timeout` (`DependencyUnavailableError`). Copre REQ-EVT-T01-AC5.
- **`test_contracts.py`** — una `assert_matches_contract` per ciascuna delle 7
  operazioni (`health`, `createEvent`, `listEvents`, `getEvent`, `replaceEvent`,
  `updateEvent`, `deleteEvent`), user-service mockato con `responses` dove serve
  (REQ-EVT-T01-AC4).
- **`test_config.py`** — `load_config()` senza PORT → `ValueError`; default di
  `STORAGE_BACKEND`, `DATA_DIR`, `USER_SERVICE_URL`; import di `app` senza PORT.

Ogni test è tracciato con `@pytest.mark.req("REQ-EVT-…")` o l'ID nel nome/docstring
(REQ-EVT-T01-AC6).

### Integrazione propria (`tests/integration/`)

`test_event_integration.py` avvia **user-service** ed **event-service** reali come
sottoprocessi su porte libere (REQ-EVT-T02):

```python
@pytest.fixture(scope="module")
def live_stack(tmp_path_factory):
    user_port = free_port(); event_port = free_port()
    user = start(SERVICE("user-service"), {"PORT": str(user_port), "STORAGE_BACKEND": "memory"})
    try:
        wait_health(user_port)
        event = start(SERVICE("event-service"), {
            "PORT": str(event_port), "STORAGE_BACKEND": "memory",
            "USER_SERVICE_URL": f"http://127.0.0.1:{user_port}"})
        try:
            wait_health(event_port)
            yield {"user": user_port, "event": event_port}
        finally:
            terminate(event)     # try/finally + kill fallback
    finally:
        terminate(user)
```

Casi (REQ-EVT-T02-AC2/3/4):
1. **positivo**: crea organizer nel user reale → crea evento → 201, `status="draft"`.
2. **riferimento inesistente**: `organizer_id` uuid casuale → 422 `REFERENCE_NOT_FOUND`.
3. **dipendenza spenta**: event avviato con `USER_SERVICE_URL` su porta chiusa → POST
   → 503 `DEPENDENCY_UNAVAILABLE`.

Cleanup garantito con `try/finally` e `kill()` di fallback (processi su porte libere).

### Comandi (Windows, `py -3.12`)

```powershell
# dalla directory del servizio
py -3.12 -m pytest tests/unit -v --cov=app --cov-report=term-missing --cov-fail-under=80
py -3.12 -m pytest tests/integration -v
```

Coverage ≥ 80% sul package `app` (REQ-EVT-T01-AC1). `__main__.py` escluso con
`# pragma: no cover`.

---

## 14. services.yaml e avvio (Windows)

Al task di preparazione ambiente, `Exam/techconf-exam/services.yaml` viene esteso per
dichiarare `event` **oltre** a `user` (necessario perché la suite avvia le dipendenze):

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

`command: py -3.12 -m app` è la scelta robusta su Windows (come user-service T-14):
la suite lancia con `shell=True` dal `cwd` e non attiva venv. La suite inietta `PORT`
(15002) e `USER_SERVICE_URL` (→15001); il servizio legge sempre da env
(REQ-EVT-F13). L'aggiornamento del manifest avviene nel relativo task, non ora.

---

## 15. Matrice requisiti → componenti → verifiche

| Requisito | Componente principale | Verifiche |
|---|---|---|
| REQ-EVT-F01 | `routes.py` GET /health, `__init__` | `test_routes::health` + contratto |
| REQ-EVT-F02 | `routes.py` POST + `service.create_event` | `test_routes`, `test_service`, `test_contracts` (createEvent), IT-E01 |
| REQ-EVT-F03 | `validators.validate_event_create` | `test_routes` (422 vari), `test_service` |
| REQ-EVT-F04 | `validators.validate_event_update`, `service.update_event` | `test_service` (PATCH, empty, unknown field) |
| REQ-EVT-F05 | `routes.py` GET/{id}, `service.get_event` | `test_routes`, `test_contracts` (getEvent), IT-E07 |
| REQ-EVT-F06 | `pagination.py`, `service.list_events` | `test_routes` (paginazione/422), `test_contracts` (listEvents), IT-E06 |
| REQ-EVT-F07 | `service.replace_event` | `test_service`, `test_contracts` (replaceEvent), IT-E07 |
| REQ-EVT-F08 | `service.update_event` | `test_service`, `test_contracts` (updateEvent), IT-E05/E07 |
| REQ-EVT-F09 | `service.delete_event` | `test_routes`, `test_contracts` (deleteEvent), IT-E07 |
| REQ-EVT-F10 | error handlers 404/405 | `test_routes` (405, path sconosciuto) |
| REQ-EVT-F11 | `models.utcnow_iso`, `service` | `test_service` (monkeypatch orologio) |
| REQ-EVT-F12 | `errors.make_error_response` | `test_routes` (formato errori) |
| REQ-EVT-F13 | `config.load_config` | `test_config` |
| REQ-EVT-F14 | `repository.py`, `backends/` | `test_repository` (3 backend) |
| REQ-EVT-B01 | `http_client.verify_organizer`, `service` | `test_http_client` (404), `test_service`, IT-E02 |
| REQ-EVT-B02 | `http_client.verify_organizer` | `test_http_client` (ruolo), `test_service`, IT-E03 |
| REQ-EVT-B03 | `validators.validate_dates_coherent` | `test_service`/`test_routes`, IT-E04 |
| REQ-EVT-B04 | `service.check_transition` | `test_service` (transizioni + no-op), IT-E05 |
| REQ-EVT-B05 | `http_client` (timeout/refused/5xx) | `test_http_client`, IT-E08 |
| REQ-EVT-B06 | `service.list_events` filtri | `test_service`, IT-E06 |
| REQ-EVT-T01 | intera suite unit | coverage ≥80%, contratto per operazione, 3 backend |
| REQ-EVT-T02 | `tests/integration/test_event_integration.py` | positivo, 422, 503 con servizi reali |
