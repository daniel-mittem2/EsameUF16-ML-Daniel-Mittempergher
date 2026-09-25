# user-service — Design

**Contratto di riferimento:** `Exam/techconf-exam/contracts/openapi/user-service.yaml`
**Requirements:** `.kiro/specs/user-service/requirements.md`
**Standard globali:** `.kiro/steering/structure.md` · `.kiro/steering/platform-standards.md`
**Versione spec:** 1.0 — 2026-09-25

---

## 1. Riferimento al contratto OpenAPI

Il contratto `user-service.yaml` è la fonte di verità. Tutte le scelte di design
devono essere conformi ad esso senza modificarlo. I punti critici estratti dal
contratto che guidano il design:

| Elemento | Dettaglio rilevante |
|---|---|
| `UserCreate` | `additionalProperties: false`; campi required: `first_name`, `last_name`, `email` |
| `UserUpdate` | `additionalProperties: false`; tutti i campi opzionali |
| `User` (response) | `additionalProperties: false`; tutti i 7 campi required |
| `company` | `nullable: true` — unico campo che accetta `null` |
| `role` | `enum: [attendee, speaker, organizer]`; default `attendee` |
| `Error` | `additionalProperties: false` su `error`; `details` è `additionalProperties: true` |
| `Health` | `additionalProperties: false`; `status: enum: [ok]`, `service: string` |
| Paginazione | `page` min 1 default 1; `page_size` min 1 max 100 default 20 |

Il contratto usa `nullable: true` per `company` (stile OpenAPI 3.0). Il
`validator.py` lo traduce a `{"type": ["string", "null"]}` via `_resolve_refs`
prima della validazione JSON Schema Draft 7. Non è necessario alcun adattamento
nell'implementazione: basta restituire `null` e non `""` quando company è assente.

---

## 2. Struttura dei moduli

```
services/user-service/
  app/
    __init__.py          # create_app(config=None) — Flask application factory
    __main__.py          # entry point: legge config.PORT, chiama create_app(), avvia server
    config.py            # legge os.environ UNA SOLA VOLTA, espone costanti tipizzate
    routes.py            # Blueprint Flask: parsing, validazione HTTP, serializzazione
    service.py           # UserService: regole di business REQ-USR-B*, orchestrazione
    repository.py        # AbstractUserRepository (ABC) + helper get_repository()
    backends/
      __init__.py
      memory.py          # MemoryUserRepository
      json_backend.py    # JsonUserRepository
      sqlite_backend.py  # SqliteUserRepository
    validators.py        # funzioni di validazione input (email, campi, tipo body)
    errors.py            # costanti codici errore + make_error_response()
    pagination.py        # parse_pagination_params(), paginate()
    models.py            # user_to_dict(), new_user_record()
  tests/
    unit/
      test_routes.py
      test_service.py
      test_repository.py
      test_contracts.py
    integration/
      test_user_integration.py
  requirements.txt
```

`http_client.py` è **assente**: user-service non effettua chiamate HTTP ad altri
servizi (REQ-USR-F14, nota ambiguità).

---

## 3. Responsabilità dei moduli

### `config.py`

Legge `os.environ` una sola volta all'import. Espone costanti:

```python
PORT: int           # da PORT (obbligatorio — ValueError se assente o non intero)
STORAGE_BACKEND: str  # "memory" | "json" | "sqlite", default "memory"
DATA_DIR: Path      # da DATA_DIR, default Path("./data")
```

Nessun altro modulo chiama `os.environ` direttamente. I test unitari impostano
i valori iniettando `monkeypatch.setenv` **prima** dell'import del modulo, oppure
usando `importlib.reload(config)` dopo aver modificato le variabili.

### `__init__.py` — Application factory

```python
def create_app(repo=None) -> Flask:
    app = Flask(__name__)
    if repo is None:
        repo = get_repository()   # legge config.STORAGE_BACKEND
    app.config["REPO"] = repo
    app.register_blueprint(users_bp)
    register_error_handlers(app)
    return app
```

La factory accetta un `repo` opzionale: i test unitari iniettano un repository
fittizio (o uno dei backend reali su `tmp_path`) senza leggere variabili
d'ambiente né avviare un server.

**Distinzione avvio server / creazione app nei test:**

| Contesto | Come si usa `create_app` |
|---|---|
| Produzione / suite | `__main__.py` chiama `create_app()` poi `app.run(...)` |
| Test unitari | `client = create_app(repo=FakeRepo()).test_client()` |
| Test di integrazione propri | sottoprocesso reale su porta libera |

### `__main__.py`

```python
from app import config, create_app

app = create_app()
app.run(host="0.0.0.0", port=config.PORT, debug=False)
```

Non legge mai `os.environ` direttamente. Compatibile con `python -m app` dal
`cwd` del servizio (come richiesto da `services.yaml`).

**Avvio Windows:** il `services.yaml` usa `command: python -m app`; la suite
inietta la variabile `PORT` prima del lancio. In sviluppo locale si usa
`py -3.12 -m app` dalla directory del servizio con `PORT=5001` impostata.

### `routes.py`

Registra un Blueprint `users_bp` con prefix vuoto (le rotte sono già complete).
Gestisce:

- parsing e validazione del JSON body (delega a `validators.py`)
- estrazione e validazione dei query param (delega a `pagination.py`)
- chiamata al `UserService` (ottenuto da `current_app.config["REPO"]` → injected
  nel service)
- serializzazione della risposta con `jsonify()`
- header `Location` su 201

Il Blueprint **non contiene logica di business**: decide solo status code e formato
della risposta.

### `service.py` — UserService

Riceve il repository via costruttore (`__init__(self, repo)`). Contiene tutte le
regole REQ-USR-B*:

- normalizzazione email a lowercase (REQ-USR-B02) prima di qualsiasi operazione
- controllo unicità email con esclusione self (REQ-USR-B01)
- applicazione dei default (`role="attendee"`, `company=None`)
- generazione UUID v4 e timestamp
- logica PUT sostitutivo vs PATCH parziale
- regola empty PATCH → risorsa e timestamp invariati (REQ-USR-F04-AC4)

Non importa mai i backend direttamente: usa solo l'interfaccia `AbstractUserRepository`.

### `validators.py`

Funzioni pure (senza stato, senza accesso a Flask context):

- `validate_body_is_object(data)` → 422 se `data` non è dict
- `validate_user_create(data)` → lista di errori di campo
- `validate_user_update(data)` → lista di errori (tutti facoltativi)
- `validate_email_format(email)` → bool (vedi §4 email)
- `validate_pagination_params(page, page_size)` → (int, int) o 422

Separare la validazione in un modulo dedicato permette di testarla senza avviare
Flask e senza toccare il repository.

### `errors.py`

```python
ERROR_CODES = {
    "NOT_FOUND": 404,
    "VALIDATION_ERROR": 422,
    "EMAIL_ALREADY_EXISTS": 409,
    ...
}

def make_error_response(code: str, message: str, details: dict = None, status: int = None):
    body = {"error": {"code": code, "message": message, "details": details or {}}}
    http_status = status or ERROR_CODES.get(code, 422)
    return jsonify(body), http_status
```

`details` è sempre un dict, mai `null` (REQ-USR-F12-AC3). L'helper è l'unico
punto dove viene costruita la risposta d'errore: nessun altro modulo può restituire
un corpo `{"error": ...}` direttamente.

### `models.py`

```python
def new_user_record(data: dict, now: str) -> dict:
    """Crea il dict persistibile per un nuovo utente."""
    return {
        "id": str(uuid.uuid4()),
        "first_name": data["first_name"],
        "last_name": data["last_name"],
        "email": data["email"].lower(),    # REQ-USR-B02
        "company": data.get("company"),    # None se assente
        "role": data.get("role", "attendee"),
        "created_at": now,
        "updated_at": now,
    }

def user_to_dict(record: dict) -> dict:
    """Serializza per la risposta HTTP (subset pulito del record interno)."""
    return {k: record[k] for k in
            ("id","first_name","last_name","email","company","role","created_at","updated_at")}
```

---

## 4. Validazione email

**Strategia scelta:** regex minimale che verifica la forma `local@domain.tld`.

Il contratto OpenAPI dichiara `format: email`. Una validazione RFC 5322 completa
è volutamente non richiesta (accetterebbe formati esotici rari e richiederebbe una
dipendenza esterna). La strategia scelta:

```python
import re
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def validate_email_format(email: str) -> bool:
    return bool(_EMAIL_RE.match(email)) if isinstance(email, str) else False
```

Questa regex:
- accetta `alice@example.com`, `user+tag@sub.domain.org`
- rifiuta `notanemail`, `@domain.com`, `user@`, `user@@domain.com`
- è sufficiente per i test di collaudo IT-U01..IT-U08

La scelta è documentata qui; se il docente richiede validazione più rigorosa,
si sostituisce solo `validate_email_format` senza toccare altri moduli.

---

## 5. Gestione della paginazione

```python
def parse_pagination_params(args: dict) -> tuple[int, int]:
    """Estrae e valida page e page_size da request.args."""
    # 422 se assenti come stringa vuota, non numerici, non interi, fuori range
    ...

def paginate(items: list, page: int, page_size: int) -> dict:
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": items[start:end],
        "page": page,
        "page_size": page_size,
        "total": len(items),   # dopo filtri, prima di paginazione
    }
```

`total` riflette sempre il numero di record filtrati, non quelli nella pagina
corrente (REQ-USR-F06-AC7, REQ-USR-B03-AC4).

---

## 6. PUT vs PATCH — implementazione

**PUT** usa lo schema `UserCreate` (stessi campi obbligatori di POST). Il service
layer:
1. valida il body come se fosse una POST
2. recupera il record esistente (404 se non trovato)
3. sostituisce tutti i campi mutable: `first_name`, `last_name`, `email`,
   `company`, `role`
4. mantiene `id` e `created_at` dal record originale
5. aggiorna `updated_at` al timestamp corrente

**PATCH** usa lo schema `UserUpdate` (tutti opzionali). Il service layer:
1. verifica che il body sia un dict (422 se non lo è)
2. filtra i campi presenti nel body (ignora chiavi non previste — sono già 422
   per `additionalProperties: false`)
3. **se il body è `{}` (nessun campo)**: ritorna il record invariato, `updated_at`
   non aggiornato (REQ-USR-F04-AC4)
4. altrimenti: applica solo i campi presenti, aggiorna `updated_at`

---

## 7. Error handlers Flask

Registrati in `register_error_handlers(app)` dentro `__init__.py`:

```python
@app.errorhandler(400)
def bad_request(e): return make_error_response("MALFORMED_JSON", str(e), status=400)

@app.errorhandler(404)
def not_found(e): return make_error_response("NOT_FOUND", str(e), status=404)

@app.errorhandler(405)
def method_not_allowed(e): return make_error_response("METHOD_NOT_ALLOWED", str(e), status=405)
```

Questo garantisce che anche i 404 per path sconosciuti e i 405 per metodi non
consentiti producano il formato `Error` standard con `details: {}` (REQ-USR-F10,
REQ-USR-F12). Flask genera questi errori automaticamente; non servono route
catch-all.

Il gestore 400 intercetta anche il `BadRequest` che Flask lancia quando il body
non è JSON valido (`request.get_json(force=True, silent=False)`).

---

## 8. Timestamp

```python
from datetime import datetime, timezone

def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
```

- Generato dal server all'atto della creazione/modifica
- Formato `Z` finale (es. `2026-10-15T09:30:00Z`)
- `created_at` salvato nel record e mai sovrascritto
- `updated_at` aggiornato in PUT e in PATCH non-vuoto; invariato per PATCH `{}`

---

## 9. Interfaccia repository e tre backend

### AbstractUserRepository

```python
from abc import ABC, abstractmethod

class AbstractUserRepository(ABC):
    @abstractmethod
    def create(self, record: dict) -> dict: ...

    @abstractmethod
    def get(self, user_id: str) -> dict | None: ...

    @abstractmethod
    def list_all(self, filters: dict) -> list[dict]: ...

    @abstractmethod
    def update(self, user_id: str, changes: dict) -> dict | None: ...

    @abstractmethod
    def delete(self, user_id: str) -> bool: ...

    @abstractmethod
    def get_by_email(self, email: str) -> dict | None: ...
```

`get_by_email` è separato da `get` perché la ricerca per email è usata dal
service layer nel controllo unicità. Tutti i backend lo implementano.

La factory `get_repository()` in `repository.py` legge `config.STORAGE_BACKEND`
e restituisce l'istanza corretta. Chiamata una volta sola in `create_app()`.

### MemoryUserRepository

- dizionario in-memoria `{id: record}`
- nessuna persistenza tra riavvii
- thread-safe per test single-process (nessun lock necessario)
- `get_by_email`: iterazione lineare sul dizionario, case-insensitive

### JsonUserRepository

```
DATA_DIR/users.json   ← lista di record [{id, ...}, ...]
```

- legge il file intero all'apertura; scrive il file intero a ogni modifica
- **scrittura sicura**: scrive su file temporaneo (`users.json.tmp`) nella stessa
  directory, poi `os.replace()` atomico — evita file corrotto in caso di crash
- `DATA_DIR` creato automaticamente se assente (`os.makedirs(exist_ok=True)`)
- riapertura dati persistenti: al prossimo avvio legge `users.json` esistente
- **unicità email concorrente**: `os.replace()` è atomico su filesystem POSIX;
  su Windows è atomico dalla Python 3.3+. Il service layer esegue il check-then-
  write in sequenza sincrona; Flask development server è single-threaded. Per
  workload multi-threaded la protezione rimane nel service layer (vedi §10).

### SqliteUserRepository

```sql
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    first_name  TEXT NOT NULL,
    last_name   TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,  -- index per performance e unicità DB
    company     TEXT,                  -- NULL quando assente
    role        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower ON users (LOWER(email));
```

- connessione aperta in `__init__` del backend e chiusa in `close()` (o con
  context manager)
- `check_same_thread=False` perché Flask può servire richieste in thread diversi
- **unicità email**: l'indice `LOWER(email)` garantisce unicità a livello DB;
  `IntegrityError` viene catturato nel backend e rilancia `EmailAlreadyExistsError`
- **transazioni**: ogni write usa un `with conn:` per commit automatico o rollback
  in caso di eccezione
- `DATA_DIR/users.db` — esclusa da git tramite `.gitignore` (`*.sqlite`)

### `get_repository()` factory

```python
def get_repository() -> AbstractUserRepository:
    backend = config.STORAGE_BACKEND
    if backend == "memory":
        return MemoryUserRepository()
    elif backend == "json":
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        return JsonUserRepository(config.DATA_DIR / "users.json")
    elif backend == "sqlite":
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        return SqliteUserRepository(config.DATA_DIR / "users.db")
    raise ValueError(f"Unknown STORAGE_BACKEND: {backend!r}")
```

---

## 10. Protezione unicità email con richieste concorrenti

La regola REQ-USR-B01 (email univoca) richiede un controllo prima della scrittura.
In un ambiente concorrente, due richieste simultane potrebbero passare entrambe il
controllo e poi scrivere, violando l'unicità.

**Strategia scelta: le regole di business rimangono nel service layer** (in linea
con gli steering). La protezione effettiva è delegata al backend:

- **memory**: single-threaded in Flask dev server — nessun race condition reale
- **json**: `os.replace()` atomico protegge la scrittura; il check-then-write
  rimane vulnerabile a race condition multi-thread teoriche, ma il Flask dev server
  è single-threaded per default. Se necessario, si aggiunge un `threading.Lock()`
  nel `JsonUserRepository` senza toccare `service.py`.
- **sqlite**: il vincolo `UNIQUE INDEX` sul DB garantisce atomicità; l'`IntegrityError`
  viene intercettato nel backend e propagato come `EmailAlreadyExistsError` al
  service layer, che lo converte in 409.

In tutti i casi il service layer esegue `get_by_email` prima di `create`/`update`:
questa doppia verifica (controllo esplicito + vincolo DB) garantisce messaggi di
errore coerenti in tutti i backend.

---

## 11. Adattamento della risposta per `assert_matches_contract`

Il `validator.py` accetta sia `requests.Response` che un dizionario con chiavi
`status_code`, `headers`, `json`. Il Flask test client restituisce un
`flask.testing.FlaskClient` response che espone `status_code`, `headers` e `.json`
come proprietà/metodi.

Il validator chiama `response.json()` come metodo. Flask `Response` espone
`.get_json()` e `.json` come property, ma **non** `.json()` come callable. Si
risolve con un wrapper leggero nei test:

```python
class FlaskResponseAdapter:
    """Wraps flask.testing.FlaskClient response to match requests.Response API."""
    def __init__(self, resp):
        self._resp = resp
        self.status_code = resp.status_code
        self.headers = dict(resp.headers)

    def json(self):
        return self._resp.get_json(force=True)
```

Uso nei test di contratto:
```python
resp = client.post("/api/v1/users", json=payload)
assert_matches_contract("user", "POST", "/api/v1/users",
                         FlaskResponseAdapter(resp))
```

`validator.py` non viene modificato.

---

## 12. Gestione degli errori non elencati per singola operazione nel contratto

Il contratto OpenAPI elenca i codici di risposta per ogni operazione. Alcuni
codici (400, 405) sono impliciti per gli standard HTTP ma non dichiarati in ogni
singola operazione. La strategia:

- **400 per PATCH**: la platform-standard lo richiede; il gestore globale Flask
  lo produce. Il `validator.py` solleverebbe `ContractError` se invocato su una
  risposta 400 per PATCH (perché 400 non è nel contratto di PATCH). Per i test
  di errore 400 si **non usa** `assert_matches_contract` ma si verifica solo
  `status_code == 400` e la struttura del body manualmente.
- **405**: il contratto non elenca 405 nelle singole operazioni ma Flask lo genera.
  Stessa soluzione: nei test per 405 non si chiama `assert_matches_contract`.
- **Nota**: questa è la prassi corretta — il validator valida solo le risposte
  previste dal contratto, non le eccezioni di infrastruttura.

---

## 13. Strategia di test

### Test unitari (`tests/unit/`)

**`test_routes.py`** — usa `create_app(repo=FakeRepo()).test_client()`:
- testa ogni endpoint (7 operazioni + /health) con Flask test client
- verifica status code, header `Location` su POST, body JSON
- testa casi di errore: 400 malformed, 404, 409, 422 per ogni vincolo
- usa `FlaskResponseAdapter` per i test di contratto

**`test_service.py`** — testa `UserService` con `MemoryUserRepository`:
- verifica ogni regola REQ-USR-B*
- testa normalizzazione email, default role, UUID generato
- testa PUT vs PATCH semantics, empty PATCH invariato
- testa updated_at aggiornato / non aggiornato

**`test_repository.py`** — testa tutti e tre i backend con parametrizzazione:
```python
@pytest.fixture(params=["memory", "json", "sqlite"])
def repo(request, tmp_path):
    if request.param == "memory":
        return MemoryUserRepository()
    elif request.param == "json":
        return JsonUserRepository(tmp_path / "users.json")
    else:
        return SqliteUserRepository(tmp_path / "users.db")
```
Copre: create, get, get_by_email, list_all con filtri, update, delete.

**`test_contracts.py`** — usa `FlaskResponseAdapter`, una chiamata per operazione:

| Operazione | Metodo | Path usato in assert_matches_contract |
|---|---|---|
| GET /health | GET | `/health` |
| POST /api/v1/users | POST | `/api/v1/users` |
| GET /api/v1/users | GET | `/api/v1/users` |
| GET /api/v1/users/{id} | GET | `/api/v1/users/<id>` |
| PUT /api/v1/users/{id} | PUT | `/api/v1/users/<id>` |
| PATCH /api/v1/users/{id} | PATCH | `/api/v1/users/<id>` |
| DELETE /api/v1/users/{id} | DELETE | `/api/v1/users/<id>` |

Per DELETE 204 il body è vuoto: `validator.py` accetta risposte senza body
quando lo schema non prevede contenuto (il codice `_response_schema` ritorna
`None` per 204 → `assert_matches_contract` non valida il body).

### Test di integrazione propri (`tests/integration/`)

`test_user_integration.py` avvia il servizio come sottoprocesso reale:

```python
@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    port = find_free_port()   # socket(AF_INET, SOCK_STREAM).bind(('', 0))
    env = {**os.environ, "PORT": str(port), "STORAGE_BACKEND": "memory"}
    proc = subprocess.Popen(
        ["py", "-3.12", "-m", "app"],
        cwd=str(SERVICE_DIR),
        env=env,
    )
    wait_for_health(f"http://localhost:{port}/health", timeout=10)
    yield f"http://localhost:{port}"
    proc.terminate()
    proc.wait(timeout=5)
```

Casi verificati:
- positivo: POST + GET by id
- riferimento inesistente: GET /api/v1/users/{fake-uuid} → 404
- email duplicata: due POST con stessa email → 409

### Comandi

```bash
# Dalla directory del servizio
py -3.12 -m pytest tests/unit -v --cov=app --cov-report=term-missing

# Solo test di contratto
py -3.12 -m pytest tests/unit/test_contracts.py -v

# Con backend specifico (via env var, test parametrizzati lo gestiscono da soli)
py -3.12 -m pytest tests/unit/test_repository.py -v

# Test di integrazione propri (avvia processo reale)
py -3.12 -m pytest tests/integration -v
```

### Coverage ≥ 80%

Le aree a rischio per la coverage:
- rami `if STORAGE_BACKEND == "sqlite"` — coperti dai test parametrizzati
- error handler Flask — coperti dai test 404/405 in `test_routes.py`
- `__main__.py` — escluso dalla coverage con `# pragma: no cover` sull'`if __name__`

---

## 14. Avvio Windows e compatibilità con `services.yaml`

Il `services.yaml` dichiara:
```yaml
user:
  cwd: services/user-service
  command: python -m app
  health_path: /health
```

La suite di collaudo (harness.py) lancia il processo con `subprocess.Popen(command,
shell=True, cwd=cwd)`. Su Windows, `python` deve essere nel PATH. Se non lo è,
l'alternativa è cambiare `command` in `services.yaml` in `py -3.12 -m app`.

**In sviluppo locale** il comando è `py -3.12 -m app` con `PORT=5001` impostata
nel terminale. Il `services.yaml` usa `python` perché la suite gira in un ambiente
Python già attivato.

**Verifica compatibilità:** il servizio legge `PORT` da env (REQ-USR-F13-AC1);
la suite inietta `PORT=15001` prima del lancio. Non c'è hard-coding della porta.

---

## 15. Matrice requisiti → componenti → test previsti

| Requisito | Componente principale | Test previsti |
|---|---|---|
| REQ-USR-F01 | `routes.py` (GET /health) | `test_routes.py::test_health` + contratto |
| REQ-USR-F02 | `routes.py` POST + `service.py` + `models.py` | `test_routes.py::test_create_*` + contratto |
| REQ-USR-F03 | `validators.py` | `test_routes.py::test_validation_*` |
| REQ-USR-F04 | `validators.py` + `service.py` (PATCH) | `test_routes.py::test_patch_*` |
| REQ-USR-B01 | `service.py::check_email_unique` | `test_service.py::test_email_unique_*` |
| REQ-USR-B02 | `service.py` (normalize) + `models.py` | `test_service.py::test_email_lowercase` |
| REQ-USR-B03 | `service.py::list_users` | `test_service.py::test_list_filters` |
| REQ-USR-F05 | `routes.py` GET /{id} + `service.py` | `test_routes.py::test_get_by_id_*` + contratto |
| REQ-USR-F06 | `pagination.py` | `test_routes.py::test_list_pagination` + contratto |
| REQ-USR-F07 | `routes.py` PUT + `service.py` | `test_routes.py::test_put_*` + contratto |
| REQ-USR-F08 | `routes.py` PATCH + `service.py` | `test_routes.py::test_patch_*` + contratto |
| REQ-USR-F09 | `routes.py` DELETE + `service.py` | `test_routes.py::test_delete_*` + contratto |
| REQ-USR-F10 | error handlers Flask | `test_routes.py::test_method_not_allowed` |
| REQ-USR-F11 | `service.py` (timestamp logic) | `test_service.py::test_timestamps_*` |
| REQ-USR-F12 | `errors.py` + error handlers | `test_routes.py::test_error_format_*` |
| REQ-USR-F13 | `config.py` | `test_config.py` (monkeypatch env) |
| REQ-USR-F14 | `repository.py` + `backends/` | `test_repository.py` (3 backend) |
| REQ-USR-T01 | tutti | `pytest --cov=app` ≥ 80% |
