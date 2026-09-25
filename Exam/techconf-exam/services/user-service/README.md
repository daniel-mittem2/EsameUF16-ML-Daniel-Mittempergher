# user-service

Anagrafica centrale della piattaforma **TechConf**. Gestisce gli utenti con tre
ruoli (`attendee`, `speaker`, `organizer`) ed è la fonte di verità per l'identità:
event-service, registration-service e notification-service lo interrogano per
validare i riferimenti agli utenti. Il servizio non chiama nessun altro
microservizio.

- **Contratto:** `contracts/openapi/user-service.yaml`
- **Spec:** `.kiro/specs/user-service/` (requirements, design, tasks)
- **Framework:** Flask (stdlib `sqlite3` per il backend SQLite)

Tutti i comandi indicati usano PowerShell su Windows e l'interprete `py -3.12`.
Salvo diversa indicazione, vanno eseguiti **dalla directory del servizio**
(`Exam/techconf-exam/services/user-service/`).

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

### Variabili d'ambiente

| Variabile | Obbligatoria | Default | Descrizione |
|---|---|---|---|
| `PORT` | **Sì** | — | Porta TCP di ascolto. Se assente, il servizio termina con errore. |
| `STORAGE_BACKEND` | No | `memory` | Backend di persistenza: `memory`, `json` o `sqlite`. |
| `DATA_DIR` | No | `./data` | Directory dei file di persistenza (usata solo da `json` e `sqlite`). |

Tutte le variabili sono lette esclusivamente in `app/config.py`.

### Backend `memory` (default)

I dati risiedono in memoria e vengono persi al riavvio.

```powershell
$env:PORT="5001"; py -3.12 -m app
```

### Backend `json`

I dati sono persistiti su un file JSON in `DATA_DIR` e sopravvivono al riavvio.

```powershell
$env:PORT="5001"; $env:STORAGE_BACKEND="json"; $env:DATA_DIR="./data"; py -3.12 -m app
```

### Backend `sqlite`

I dati sono persistiti su un database SQLite in `DATA_DIR` e sopravvivono al
riavvio.

```powershell
$env:PORT="5001"; $env:STORAGE_BACKEND="sqlite"; $env:DATA_DIR="./data"; py -3.12 -m app
```

### Verifica rapida

A servizio avviato, l'health check risponde `200`:

```powershell
curl http://localhost:5001/health
# {"status": "ok", "service": "user-service"}
```

> Nota: durante il collaudo la suite del docente inietta `PORT` (porte
> 15001-15005) e le eventuali `STORAGE_BACKEND`/`DATA_DIR`. Non usare porte
> hard-coded: il servizio legge sempre `PORT` dall'ambiente.

---

## Test unitari (con coverage)

Dalla directory del servizio, con soglia minima di copertura all'80% sul
package `app/`:

```powershell
py -3.12 -m pytest tests/unit -v --cov=app --cov-report=term-missing --cov-fail-under=80
```

I test unitari coprono routes, service layer, repository (tutti e tre i backend,
con `tmp_path` per `json`/`sqlite`), configurazione e conformità ai contratti.
Non richiedono un servizio in esecuzione: usano il Flask test client in-process.

---

## Test di integrazione propri

Dalla directory del servizio:

```powershell
py -3.12 -m pytest tests/integration -v
```

Questi test avviano il servizio come sottoprocesso reale su una porta libera
(`STORAGE_BACKEND=memory`), attendono `/health`, eseguono casi positivi e
negativi (POST → GET by id, riferimento inesistente → 404, email duplicata →
409) e terminano il processo.

---

## Suite di collaudo del docente (solo user)

Dalla **root dell'esame** (`Exam/techconf-exam/`), dopo aver dichiarato il
servizio in `services.yaml`:

```powershell
py -3.12 -m pytest tests/integration -k user -v
```

Il manifest `services.yaml` alla root dichiara solo il servizio `user`:

```yaml
services:
  user:
    cwd: services/user-service
    command: py -3.12 -m app
    health_path: /health
```

Se non già presenti, installare le dipendenze della suite:

```powershell
py -3.12 -m pip install -r tests/integration/requirements.txt
```

---

## Riferimenti a requisiti e task

### Requisiti (`REQ-USR-*`)

| ID | Descrizione |
|---|---|
| REQ-USR-F01 | Health check `GET /health` |
| REQ-USR-F02 | Creazione utente (`POST`) |
| REQ-USR-F03 | Validazione dei campi (POST e PUT) |
| REQ-USR-F04 | Validazione dei campi (PATCH) |
| REQ-USR-F05 | Lettura utente per ID (`GET /{id}`) |
| REQ-USR-F06 | Lista paginata (`GET /`) |
| REQ-USR-F07 | Sostituzione utente (`PUT /{id}`) |
| REQ-USR-F08 | Aggiornamento parziale (`PATCH /{id}`) |
| REQ-USR-F09 | Cancellazione utente (`DELETE /{id}`) |
| REQ-USR-F10 | Metodi non consentiti e percorsi sconosciuti (405 / 404) |
| REQ-USR-F11 | Immutabilità di `created_at`, aggiornamento di `updated_at` |
| REQ-USR-F12 | Formato uniforme degli errori |
| REQ-USR-F13 | Configurazione e variabili d'ambiente |
| REQ-USR-F14 | Persistenza intercambiabile (memory / json / sqlite) |
| REQ-USR-B01 | Email univoca (case-insensitive) |
| REQ-USR-B02 | Email normalizzata in minuscolo |
| REQ-USR-B03 | Filtri lista per `role` ed `email` |
| REQ-USR-T01 | Test coverage ≥ 80% e qualità (inclusa questa documentazione) |

### Task (`T-01..T-17`)

| ID | Descrizione |
|---|---|
| T-01 | Scaffold struttura directory e package |
| T-02 | Configurazione (`config.py`) |
| T-03 | Health endpoint e application factory |
| T-04 | Moduli di supporto (`errors`, `pagination`, `models`, `validators`) |
| T-05 | Repository: interfaccia astratta e backend memory |
| T-06 | Backend JSON |
| T-07 | Backend SQLite |
| T-08 | UserService: create e regole B01/B02 |
| T-09 | UserService: get, list e filtri B03 |
| T-10 | UserService: replace (PUT) e update (PATCH) |
| T-11 | UserService: delete |
| T-12 | Routes HTTP complete |
| T-13 | Test unitari completi (`tests/unit/`) |
| T-14 | `services.yaml` e preparazione ambiente |
| T-15 | Test di integrazione propri (`tests/integration/`) |
| T-16 | Collaudo con suite del docente (solo user) e verifica checksum |
| T-17 | `README.md` del servizio (questo documento) |
