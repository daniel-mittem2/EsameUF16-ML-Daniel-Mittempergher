# techconf-exam — Template Repository

Template repository for the **TechConf** practical exam (Spec-Driven Development with Kiro).

Fork this repository and implement the microservices described in `Exam.MD` / the exam
brief. This template ships the **non-modifiable** contracts and the acceptance test suite.

## What this template provides

| Path | Content | Modifiable? |
|---|---|---|
| `contracts/openapi/*.yaml` | OpenAPI 3.0 contracts for the 5 services — the source of truth | ❌ NO |
| `contracts/validator.py` | `assert_matches_contract(service, method, path, response)` helper | ❌ NO |
| `tests/integration/` | Acceptance test suite (client→service, service→service, e2e, resilience) | ❌ NO |
| `CHECKSUMS.sha256` | Fingerprints of the non-modifiable files | ❌ NO |
| `services.example.yaml` | Example manifest read by the suite to launch your services | ✅ copy to `services.yaml` |

Everything else (service code, unit tests, specs, steering) is designed by you.

## Verifying the protected files

```bash
sha256sum -c CHECKSUMS.sha256
```

If you believe a contract is wrong, **open an issue** — do not modify it.

## Running the acceptance suite

1. Copy the manifest and declare the services you implemented:

   ```bash
   cp services.example.yaml services.yaml
   ```

2. Install the suite dependencies:

   ```bash
   pip install -r tests/integration/requirements.txt
   ```

3. Run the suite:

   ```bash
   pytest tests/integration -v                 # all declared services
   pytest tests/integration -m mandatory -v    # only the 3 mandatory services
   pytest tests/integration -k registration -v # a single service
   ```

Services not declared in `services.yaml` are **skipped**, not failed.

## The manifest (`services.yaml`)

For each implemented service declare its working directory (`cwd`) and start `command`.
The suite injects `PORT` and `*_SERVICE_URL` environment variables. Each service **must**
listen on the port given by `PORT`.

See `services.example.yaml` for the exact schema.

## Ports

- Development ports: `5001`–`5005`.
- Acceptance ports: `15001`–`15005` (and `15101+` for resilience instances).
- Your service must **always** read the port from the `PORT` environment variable.

Logs of services launched by the suite are written to `.it-logs/<service>.log`.


---

# TechConf — Consegna (parte obbligatoria)

Questa sezione documenta l''implementazione consegnata dei **tre servizi obbligatori**
(`user`, `event`, `registration`). I due servizi opzionali (feedback, notification) non
fanno parte di questa consegna.

Comandi indicati per **PowerShell su Windows** con l''interprete `py -3.12`.

## Struttura del repository

| Percorso | Contenuto |
|---|---|
| `services/user-service/` | user-service (`/api/v1/users`, porta dev 5001) |
| `services/event-service/` | event-service (`/api/v1/events`, porta dev 5002) — chiama user |
| `services/registration-service/` | registration-service (`/api/v1/registrations`, porta dev 5003) — chiama user + event |
| `services.yaml` | manifest letto dalla suite di collaudo (3 servizi dichiarati) |
| `collaudo.txt` | output reale di `pytest tests/integration -m mandatory -v` |
| `BUGS.md` | registro dei bug reali documentati e corretti |
| `.github/ISSUES/` | testo pronto delle issue GitHub (da pubblicare) |
| `../../.kiro/specs/<servizio>/` | spec Kiro (requirements, design, tasks) per ogni servizio |
| `../../.kiro/steering/` | 4 steering file (product, tech, structure, platform-standards) |
| `../../.kiro/hooks/` | hook "unit test on save" |

## Installazione

Dipendenze runtime + test di ciascun servizio (dalla cartella del servizio):

```powershell
py -3.12 -m pip install -r requirements-dev.txt
```

Dipendenze della suite di collaudo del docente (dalla root `techconf-exam/`):

```powershell
py -3.12 -m pip install -r tests/integration/requirements.txt
```

## Variabili d''ambiente

| Variabile | Usata da | Default | Descrizione |
|---|---|---|---|
| `PORT` | tutti | — (obbligatoria) | Porta TCP di ascolto |
| `USER_SERVICE_URL` | event, registration | `http://localhost:5001` | Base URL di user-service |
| `EVENT_SERVICE_URL` | registration | `http://localhost:5002` | Base URL di event-service |
| `STORAGE_BACKEND` | tutti | `memory` | `memory` \| `json` \| `sqlite` |
| `DATA_DIR` | tutti (json/sqlite) | `./data` | Directory dei file dati (esclusa da git) |

Tutte le variabili sono lette in un unico punto (`app/config.py`) di ogni servizio;
nessun URL di dipendenza e nessuna porta sono hard-coded.

## Avvio dei tre servizi

Ordine consigliato: user -> event -> registration. In tre terminali separati:

```powershell
# user-service
cd services/user-service ; $env:PORT="5001" ; py -3.12 -m app
```

```powershell
# event-service
cd services/event-service ; $env:PORT="5002" ; $env:USER_SERVICE_URL="http://localhost:5001" ; py -3.12 -m app
```

```powershell
# registration-service
cd services/registration-service ; $env:PORT="5003" ; $env:USER_SERVICE_URL="http://localhost:5001" ; $env:EVENT_SERVICE_URL="http://localhost:5002" ; py -3.12 -m app
```

Health check (per ogni servizio): `GET /health` -> `200 {"status":"ok","service":"<nome>"}`.

## Backend di persistenza

Ogni servizio supporta tre backend selezionabili con `STORAGE_BACKEND`, senza
modifiche alla logica di business:

- `memory` (default): dati in memoria, persi al riavvio;
- `json`: file JSON in `DATA_DIR` con scrittura atomica;
- `sqlite`: database SQLite in `DATA_DIR` (solo `sqlite3` della libreria standard).

I file dati (`data/`, `*.sqlite`) sono esclusi da Git.

## Test e collaudo

Unit test + coverage (dalla cartella del servizio, soglia 80%):

```powershell
py -3.12 -m pytest tests/unit --cov=app --cov-report=term-missing --cov-fail-under=80
```

Coverage attuale: user 95.33%, event 97.16%, registration 97.19%.

Test di integrazione propri (avviano i servizi reali come sottoprocessi):

```powershell
# da services/event-service/  e  da services/registration-service/
py -3.12 -m pytest tests/integration -v
```

Suite di collaudo del docente (dalla root `techconf-exam/`, richiede `services.yaml`):

```powershell
py -3.12 -m pytest tests/integration -v                 # tutti i servizi dichiarati
py -3.12 -m pytest tests/integration -m mandatory -v    # solo i 3 obbligatori
py -3.12 -m pytest tests/integration -k registration -v # un singolo servizio
```

L''output del collaudo obbligatorio è salvato in `collaudo.txt` (27 passed, 10 deselected).

## Verifica dei file protetti

```powershell
# nessun file in contracts/ o tests/integration/ è modificato
sha256sum -c CHECKSUMS.sha256   # oppure lo script di verifica equivalente
```

## Bug e issue

`BUGS.md` documenta i bug reali trovati, con requisito, causa, test di regressione e
commit di fix. Il testo pronto delle issue GitHub è in `.github/ISSUES/`; le issue vanno
pubblicate manualmente sul repository e i loro numeri riportati in `BUGS.md`.
