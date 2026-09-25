# event-service

Gestione delle conferenze della piattaforma **TechConf**. Ogni evento ha un ciclo
di vita (`draft` → `published` → `cancelled`), una capienza e un prezzo. È esposto
su `/api/v1/events` (porta di sviluppo `5002`) ed è consumato da
registration-service e feedback-service, che leggono gli eventi tramite le sue API.

A differenza del user-service, l'event-service **chiama un altro microservizio**:
per creare o aggiornare un evento verifica che l'organizzatore (`organizer_id`)
esista nel user-service e abbia il ruolo `organizer` (REQ-EVT-B01, REQ-EVT-B02).

- **Contratto:** `contracts/openapi/event-service.yaml`
- **Spec:** `.kiro/specs/event-service/` (requirements, design, tasks)
- **Framework:** Flask (stdlib `json` e `sqlite3` per i backend di persistenza)
- **Dipendenza:** user-service, interrogato via HTTP con timeout di 2 secondi

Tutti i comandi indicati usano PowerShell su Windows e l'interprete `py -3.12`.
Salvo diversa indicazione, vanno eseguiti **dalla directory del servizio**
(`Exam/techconf-exam/services/event-service/`).

---

## Installazione delle dipendenze

Dalla directory del servizio:

```powershell
py -3.12 -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` include:

- `requirements.txt` del servizio (`flask`, `requests`);
- `../../tests/integration/requirements.txt` (dipendenze della suite del docente,
  che forniscono anche `PyYAML` e `jsonschema` usati dal validator dei contratti);
- `pytest`, `pytest-cov`, `responses`.

Per il solo avvio in produzione bastano le dipendenze runtime:

```powershell
py -3.12 -m pip install -r requirements.txt
```

Usare **lo stesso interprete** (`py -3.12`) sia per i test sia per l'avvio del
servizio.

---

## Avvio del servizio

Il servizio si avvia con `py -3.12 -m app` e ascolta su `0.0.0.0:<PORT>`.
Poiché l'event-service valida l'organizzatore chiamando il user-service, per un
avvio funzionante deve essere raggiungibile un user-service all'indirizzo indicato
da `USER_SERVICE_URL` (default `http://localhost:5001`).

### Variabili d'ambiente

| Variabile | Obbligatoria | Default | Descrizione |
|---|---|---|---|
| `PORT` | **Sì** | — | Porta TCP di ascolto. Se assente o non intera, il servizio termina con errore. |
| `USER_SERVICE_URL` | No | `http://localhost:5001` | Base URL del user-service usato per verificare gli organizzatori (REQ-EVT-B01). |
| `STORAGE_BACKEND` | No | `memory` | Backend di persistenza: `memory`, `json` o `sqlite`. |
| `DATA_DIR` | No | `./data` | Directory dei file di persistenza (usata solo da `json` e `sqlite`). |

Tutte le variabili sono lette esclusivamente in `app/config.py`; nessun URL è
hard-coded altrove (REQ-EVT-F13).

### Backend `memory` (default)

I dati risiedono in memoria e vengono persi al riavvio.

```powershell
$env:PORT="5002"; $env:USER_SERVICE_URL="http://localhost:5001"; py -3.12 -m app
```

### Backend `json`

I dati sono persistiti su un file JSON in `DATA_DIR` (scrittura atomica) e
sopravvivono al riavvio.

```powershell
$env:PORT="5002"; $env:USER_SERVICE_URL="http://localhost:5001"; $env:STORAGE_BACKEND="json"; $env:DATA_DIR="./data"; py -3.12 -m app
```

### Backend `sqlite`

I dati sono persistiti su un database SQLite in `DATA_DIR` e sopravvivono al
riavvio.

```powershell
$env:PORT="5002"; $env:USER_SERVICE_URL="http://localhost:5001"; $env:STORAGE_BACKEND="sqlite"; $env:DATA_DIR="./data"; py -3.12 -m app
```

### Verifica rapida

A servizio avviato, l'health check risponde `200` senza dipendere dal user-service
né dalla persistenza (REQ-EVT-F01):

```powershell
curl http://localhost:5002/health
# {"status": "ok", "service": "event-service"}
```

> Nota: durante il collaudo la suite del docente inietta `PORT` (porte
> 15001-15005) e le eventuali `STORAGE_BACKEND`/`DATA_DIR`, e imposta
> `USER_SERVICE_URL` verso lo user reale. Non usare porte o URL hard-coded: il
> servizio legge sempre la configurazione dall'ambiente.

---

## Test unitari (con coverage)

Dalla directory del servizio, con soglia minima di copertura all'80% sul
package `app/` (REQ-EVT-T01):

```powershell
py -3.12 -m pytest tests/unit -v --cov=app --cov-report=term-missing --cov-fail-under=80
```

I test unitari coprono routes, service layer, repository (tutti e tre i backend,
con `tmp_path` per `json`/`sqlite`), client HTTP verso user-service,
configurazione e conformità ai contratti. Non richiedono servizi in esecuzione:
usano il Flask test client in-process e mockano le chiamate al user-service con
`responses` (nessuna richiesta reale lascia il processo di test).

---

## Test di integrazione propri

Dalla directory del servizio:

```powershell
py -3.12 -m pytest tests/integration -v
```

Questi test avviano **user-service** ed **event-service** reali come sottoprocessi
su porte libere (`STORAGE_BACKEND=memory`), iniettano `USER_SERVICE_URL`
dell'event verso lo user reale, attendono `/health` e terminano i processi in un
blocco `try/finally` (con `kill()` di fallback). Coprono almeno (REQ-EVT-T02):

- caso positivo: organizer valido → creazione evento → `201` con `status="draft"`;
- riferimento inesistente: `organizer_id` sconosciuto → `422` `REFERENCE_NOT_FOUND`;
- dipendenza spenta: `USER_SERVICE_URL` su porta chiusa → `503` `DEPENDENCY_UNAVAILABLE`.

---

## Suite di collaudo del docente (solo event)

Dalla **root dell'esame** (`Exam/techconf-exam/`), dopo aver dichiarato `user`
ed `event` in `services.yaml`:

```powershell
py -3.12 -m pytest tests/integration -k event -v
```

La suite del docente (IT-E01..IT-E08) avvia i servizi dichiarati e verifica il
comportamento end-to-end. Il manifest `services.yaml` alla root deve dichiarare
sia `user` (dipendenza) sia `event`:

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

Se non già presenti, installare le dipendenze della suite:

```powershell
py -3.12 -m pip install -r tests/integration/requirements.txt
```

I file protetti (`contracts/`, `tests/integration/`, `CHECKSUMS.sha256`) non
vanno modificati.

---

## Riferimenti a requisiti e task

### Requisiti (`REQ-EVT-*`)

| ID | Descrizione |
|---|---|
| REQ-EVT-F01 | Health check `GET /health` |
| REQ-EVT-F02 | Creazione evento (`POST`) |
| REQ-EVT-F03 | Validazione dei campi (POST e PUT) |
| REQ-EVT-F04 | Validazione dei campi (PATCH) |
| REQ-EVT-F05 | Lettura evento per ID (`GET /{id}`) |
| REQ-EVT-F06 | Lista paginata e filtri (`GET /`) |
| REQ-EVT-F07 | Sostituzione evento (`PUT /{id}`) |
| REQ-EVT-F08 | Aggiornamento parziale (`PATCH /{id}`) |
| REQ-EVT-F09 | Cancellazione evento (`DELETE /{id}`) |
| REQ-EVT-F10 | Metodi non consentiti e percorsi sconosciuti (405 / 404) |
| REQ-EVT-F11 | Timestamp e immutabilità (`created_at`, `updated_at`) |
| REQ-EVT-F12 | Formato uniforme degli errori |
| REQ-EVT-F13 | Configurazione e variabili d'ambiente |
| REQ-EVT-F14 | Persistenza intercambiabile (memory / json / sqlite) |
| REQ-EVT-B01 | Esistenza dell'organizzatore (user-service) |
| REQ-EVT-B02 | Ruolo dell'organizzatore = `organizer` |
| REQ-EVT-B03 | Coerenza delle date (`end_date` ≥ `start_date`) |
| REQ-EVT-B04 | Transizioni di stato ammesse |
| REQ-EVT-B05 | Dipendenza non raggiungibile → `503` |
| REQ-EVT-B06 | Filtri lista per `status` e `city` |
| REQ-EVT-T01 | Test unitari, di contratto, tre backend, coverage ≥ 80% |
| REQ-EVT-T02 | Test di integrazione propri (positivo, 422, 503) |

### Task (`T-01..T-18`)

| ID | Descrizione |
|---|---|
| T-01 | Scaffold struttura directory e package |
| T-02 | Configurazione (`config.py`) |
| T-03 | Health endpoint e application factory |
| T-04 | Moduli di supporto (`errors`, `pagination`, `models`, `validators`) |
| T-05 | Repository: interfaccia astratta e backend memory |
| T-06 | Backend JSON |
| T-07 | Backend SQLite |
| T-08 | Client HTTP verso user-service (`http_client.py`) |
| T-09 | EventService: create e regole B01/B02/B03/B05 |
| T-10 | EventService: get, list e filtri B06 |
| T-11 | EventService: replace (PUT), update (PATCH) e transizioni B04 |
| T-12 | Routes HTTP complete |
| T-13 | Test unitari completi (`tests/unit/`) |
| T-14 | Aggiornamento `services.yaml` (user + event) |
| T-15 | Test di integrazione propri (`tests/integration/`) |
| T-16 | Collaudo con suite del docente (event) e verifica checksum |
| T-17 | `README.md` del servizio (questo documento) |
| T-18 | Verifica finale di coerenza event-service |
