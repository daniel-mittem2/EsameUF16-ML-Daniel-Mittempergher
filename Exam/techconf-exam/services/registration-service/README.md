# registration-service

Gestione delle iscrizioni degli utenti agli eventi della piattaforma **TechConf**.
Ogni iscrizione lega un utente a un evento, con un importo (`amount`) e uno stato
(`confirmed` → `cancelled`). È esposto su `/api/v1/registrations` (porta di sviluppo
`5003`) ed è a sua volta consumato da feedback-service e notification-service.

È il servizio più connesso tra gli obbligatori: **chiama due dipendenze** via HTTP
(entrambe con timeout di 2 secondi):

- **user-service** — per validare che `user_id` esista (REQ-REG-B01);
- **event-service** — per validare che `event_id` esista, che l'evento sia
  `published`, per copiare `event.price` in `amount` e per leggere `event.capacity`
  ai fini della capienza e delle statistiche (REQ-REG-B02, B03, B05, B06, B08).

Un `404` da una dipendenza diventa `422 REFERENCE_NOT_FOUND`; timeout, connessione
rifiutata o `5xx` diventano `503 DEPENDENCY_UNAVAILABLE` (REQ-REG-B09).

- **Contratto:** `contracts/openapi/registration-service.yaml`
- **Spec:** `.kiro/specs/registration-service/` (requirements, design, tasks)
- **Framework:** Flask (stdlib `json` e `sqlite3` per i backend di persistenza)
- **Dipendenze:** user-service ed event-service, interrogati via HTTP con timeout di
  2 secondi

Tutti i comandi indicati usano PowerShell su Windows e l'interprete `py -3.12`.
Salvo diversa indicazione, vanno eseguiti **dalla directory del servizio**
(`Exam/techconf-exam/services/registration-service/`).

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
Poiché registration-service valida ogni iscrizione chiamando **sia** user-service
**sia** event-service, per un avvio funzionante devono essere raggiungibili
entrambe le dipendenze agli indirizzi indicati da `USER_SERVICE_URL` (default
`http://localhost:5001`) ed `EVENT_SERVICE_URL` (default `http://localhost:5002`).

### Variabili d'ambiente

| Variabile | Obbligatoria | Default | Descrizione |
|---|---|---|---|
| `PORT` | **Sì** | — | Porta TCP di ascolto. Se assente o non intera, il servizio termina con errore. |
| `USER_SERVICE_URL` | No | `http://localhost:5001` | Base URL del user-service usato per verificare `user_id` (REQ-REG-B01). |
| `EVENT_SERVICE_URL` | No | `http://localhost:5002` | Base URL dell'event-service usato per verificare `event_id`, leggere stato, prezzo e capienza (REQ-REG-B02). |
| `STORAGE_BACKEND` | No | `memory` | Backend di persistenza: `memory`, `json` o `sqlite`. |
| `DATA_DIR` | No | `./data` | Directory dei file di persistenza (usata solo da `json` e `sqlite`). |

Tutte le variabili sono lette esclusivamente in `app/config.py`; nessun URL è
hard-coded altrove (REQ-REG-F12).

### Backend `memory` (default)

I dati risiedono in memoria e vengono persi al riavvio.

```powershell
$env:PORT="5003"; $env:USER_SERVICE_URL="http://localhost:5001"; $env:EVENT_SERVICE_URL="http://localhost:5002"; py -3.12 -m app
```

### Backend `json`

I dati sono persistiti su un file JSON in `DATA_DIR` (scrittura atomica) e
sopravvivono al riavvio.

```powershell
$env:PORT="5003"; $env:USER_SERVICE_URL="http://localhost:5001"; $env:EVENT_SERVICE_URL="http://localhost:5002"; $env:STORAGE_BACKEND="json"; $env:DATA_DIR="./data"; py -3.12 -m app
```

### Backend `sqlite`

I dati sono persistiti su un database SQLite in `DATA_DIR` e sopravvivono al
riavvio.

```powershell
$env:PORT="5003"; $env:USER_SERVICE_URL="http://localhost:5001"; $env:EVENT_SERVICE_URL="http://localhost:5002"; $env:STORAGE_BACKEND="sqlite"; $env:DATA_DIR="./data"; py -3.12 -m app
```

### Verifica rapida

A servizio avviato, l'health check risponde `200` senza dipendere né dalla
persistenza né dalle due dipendenze HTTP (REQ-REG-F01):

```powershell
curl http://localhost:5003/health
# {"status": "ok", "service": "registration-service"}
```

> Nota: durante il collaudo la suite del docente inietta `PORT` (porte
> 15001-15005) e imposta `USER_SERVICE_URL`/`EVENT_SERVICE_URL` verso i servizi
> reali. Non usare porte o URL hard-coded: il servizio legge sempre la
> configurazione dall'ambiente.

---

## Endpoint

Base path: `/api/v1/registrations`.

| Metodo | Path | Descrizione | Codici |
|---|---|---|---|
| `GET` | `/health` | Health check | 200 |
| `POST` | `/api/v1/registrations` | Crea un'iscrizione (`confirmed`, `amount` = `event.price`); `Location` in risposta | 201 / 400 / 409 / 422 / 503 |
| `GET` | `/api/v1/registrations` | Lista paginata con filtri `user_id`, `event_id`, `status` (AND) | 200 / 422 |
| `GET` | `/api/v1/registrations/stats?event_id=<id>` | Statistiche evento `{event_id, capacity, confirmed, available}` | 200 / 404 / 422 / 503 |
| `GET` | `/api/v1/registrations/{id}` | Lettura per id | 200 / 404 |
| `PATCH` | `/api/v1/registrations/{id}` | Aggiorna solo `status` (`confirmed → cancelled`) | 200 / 404 / 422 |
| `DELETE` | `/api/v1/registrations/{id}` | Rimozione fisica del record | 204 / 404 |
| `PUT` | `/api/v1/registrations/{id}` | Non consentito (dichiarato dal contratto) | 405 |

Regole di business principali: verifica utente ed evento presso le dipendenze,
evento `published`, `amount` copiato dal prezzo dell'evento, nessuna doppia
iscrizione `confirmed` per la stessa coppia `(user_id, event_id)`, capienza
dell'evento, transizione `confirmed → cancelled` che libera un posto (la
riattivazione `cancelled → confirmed` è respinta con `INVALID_STATUS_TRANSITION`).
Il controllo duplicato, il conteggio della capienza e la creazione del record
avvengono in un'unica sezione critica per evitare overselling e doppie iscrizioni
sotto concorrenza.

---

## Test unitari (con coverage)

Dalla directory del servizio, con soglia minima di copertura all'80% sul
package `app/` (REQ-REG-T01):

```powershell
py -3.12 -m pytest tests/unit -v --cov=app --cov-report=term-missing --cov-fail-under=80
```

I test unitari coprono routes, service layer, repository (tutti e tre i backend,
con `tmp_path` per `json`/`sqlite`), i client HTTP verso user-service ed
event-service, la configurazione, la conformità ai contratti (una
`assert_matches_contract` per operazione, incluso il `405` di `PUT`) e la
concorrenza (capienza 1 con due create simultanee → un `201` e un `EVENT_FULL`).
Non richiedono servizi in esecuzione: usano il Flask test client in-process e
mockano le chiamate alle dipendenze con `responses` (nessuna richiesta reale
lascia il processo di test).

---

## Test di integrazione propri

Dalla directory del servizio:

```powershell
py -3.12 -m pytest tests/integration -v
```

Questi test avviano **user-service**, **event-service** e **registration-service**
reali come sottoprocessi su porte libere (`STORAGE_BACKEND=memory`), iniettano gli
`*_SERVICE_URL` corretti, attendono `/health` e terminano i processi in blocchi
`try/finally` annidati (con `kill()` di fallback). Coprono almeno (REQ-REG-T02):

- caso positivo: organizer + attendee + evento pubblicato (via event reale, che a
  sua volta verifica l'organizer su user reale) → iscrizione → `201` `confirmed`
  con `amount == event.price`;
- riferimento inesistente: `user_id`/`event_id` sconosciuto → `422`
  `REFERENCE_NOT_FOUND`;
- dipendenza spenta: `USER_SERVICE_URL`/`EVENT_SERVICE_URL` su porta chiusa → POST
  → `503` `DEPENDENCY_UNAVAILABLE`.

---

## Suite di collaudo del docente

Dalla **root dell'esame** (`Exam/techconf-exam/`), dopo aver dichiarato `user`,
`event` e `registration` in `services.yaml`.

Solo i test di registration (IT-R01..IT-R10):

```powershell
py -3.12 -m pytest tests/integration -k registration -v
```

Intero collaudo obbligatorio (IT-U01..U08, IT-E01..E08, IT-R01..R10, IT-J01),
il cui output è salvato in `collaudo.txt` (T-16):

```powershell
py -3.12 -m pytest tests/integration -m mandatory -v | Tee-Object collaudo.txt
```

Il manifest `services.yaml` alla root dichiara tutti e tre i servizi obbligatori:

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

Se non già presenti, installare le dipendenze della suite:

```powershell
py -3.12 -m pip install -r tests/integration/requirements.txt
```

I file protetti (`contracts/`, `tests/integration/`, `CHECKSUMS.sha256`) non
vanno modificati.

---

## Riferimenti a requisiti e task

### Requisiti (`REQ-REG-*`)

| ID | Descrizione |
|---|---|
| REQ-REG-F01 | Health check `GET /health` |
| REQ-REG-F02 | Creazione iscrizione (`POST`) |
| REQ-REG-F03 | Validazione dei campi (POST) |
| REQ-REG-F04 | Lettura iscrizione per ID (`GET /{id}`) |
| REQ-REG-F05 | Lista paginata e filtri (`GET /`) |
| REQ-REG-F06 | Aggiornamento stato (`PATCH /{id}`) |
| REQ-REG-F07 | Cancellazione iscrizione (`DELETE /{id}`) |
| REQ-REG-F08 | `PUT` non consentito (405) |
| REQ-REG-F09 | Metodi non consentiti e percorsi sconosciuti (405 / 404) |
| REQ-REG-F10 | Timestamp e immutabilità (`created_at`, `updated_at`) |
| REQ-REG-F11 | Formato uniforme degli errori |
| REQ-REG-F12 | Configurazione e variabili d'ambiente |
| REQ-REG-F13 | Persistenza intercambiabile (memory / json / sqlite) |
| REQ-REG-B01 | Esistenza dell'utente (user-service) |
| REQ-REG-B02 | Esistenza dell'evento (event-service) |
| REQ-REG-B03 | Evento `published` |
| REQ-REG-B04 | Nessuna doppia iscrizione `confirmed` |
| REQ-REG-B05 | Capienza evento |
| REQ-REG-B06 | `amount` = `event.price` |
| REQ-REG-B07 | Transizione `confirmed → cancelled`, libera il posto, no riattivazione |
| REQ-REG-B08 | Statistiche per evento (`stats`) |
| REQ-REG-B09 | Dipendenza non raggiungibile → `503` |
| REQ-REG-T01 | Test unitari, di contratto, tre backend, coverage ≥ 80% |
| REQ-REG-T02 | Test di integrazione propri (positivo, 422, 503) |

### Task (`T-01..T-20`)

| ID | Descrizione |
|---|---|
| T-01 | Scaffold struttura directory e package |
| T-02 | Configurazione (`config.py`) |
| T-03 | Health endpoint e application factory |
| T-04 | Moduli di supporto (`errors`, `pagination`, `models`, `validators`) |
| T-05 | Repository: interfaccia astratta e backend memory |
| T-06 | Backend JSON |
| T-07 | Backend SQLite |
| T-08 | Client HTTP verso user ed event (`http_client.py`) |
| T-09 | RegistrationService: create (B01/B02/B03/B06 + atomico B04/B05/B09) |
| T-10 | RegistrationService: get, list e filtri |
| T-11 | RegistrationService: PATCH stato e transizioni B07 |
| T-12 | Routes HTTP complete (inclusi stats e PUT → 405) |
| T-13 | Test unitari completi (`tests/unit/`) |
| T-14 | Aggiornamento `services.yaml` (user + event + registration) |
| T-15 | Test di integrazione propri (`tests/integration/`) |
| T-16 | Collaudo obbligatorio completo e salvataggio `collaudo.txt` |
| T-17 | Verifica dei checksum (file protetti intatti) |
| T-18 | Gestione bug reali (`BUGS.md`) |
| T-19 | `README.md` del servizio e verifica checklist di consegna (questo documento) |
| T-20 | Verifica finale e tag `v1.0.0` |

---

## Verifica della checklist di consegna §9 (T-19)

Verifica eseguita con **evidenze reali** (nessuna voce spuntata senza prova). I comandi
sono riproducibili sull'ambiente descritto sopra (`py -3.12`, PowerShell su Windows).
Ultima esecuzione della verifica: suite unit dei tre servizi, integrazione propria di
event e registration, checksum dei file protetti e validazione dell'hook.

| # | Voce §9 | Stato | Evidenza reale |
|---|---------|-------|----------------|
| 1 | Steering (4 file) e ≥1 hook funzionante | ✅ Fatto | `.kiro/steering/` contiene esattamente 4 file: `platform-standards.md`, `product.md`, `structure.md`, `tech.md`. Hook `.kiro/hooks/unit-tests-on-save.json` (`PostFileSave`) con matcher `services/<*-service>/**/*.py`; `py -3.12 .kiro/scripts/validate_hook.py` conferma schema, matcher (match su path registration/user/event, no-match su `contracts/`, `tests/integration/`) e **dry-run reale** dello script `run_unit_tests.py` che lancia pytest sul servizio interessato. |
| 2 | Specs dei 3 servizi obbligatori (requirements/design/tasks) | ✅ Fatto | `.kiro/specs/user-service/`, `.kiro/specs/event-service/`, `.kiro/specs/registration-service/` contengono ciascuna `requirements.md`, `design.md`, `tasks.md`. I task sono spuntati solo dove realmente eseguiti (T-20 resta aperto). |
| 3 | `services.yaml` con i 3 servizi; backend memory/json/sqlite | ✅ Fatto | `Exam/techconf-exam/services.yaml` dichiara `user`, `event`, `registration`. I tre backend di registration sono esercitati dai test parametrizzati: `py -3.12 -m pytest tests/unit/test_repository.py -k "memory or json or sqlite"` → 34 passed. |
| 4 | Coverage ≥ 80% per servizio | ✅ Fatto | Esecuzioni reali `--cov-fail-under=80`: user-service **168 passed, 95.33%**; event-service **222 passed, 97.16%**; registration-service **208 passed, 97.19%**. |
| 5 | Integration test propri per event e registration | ✅ Fatto | `services/event-service`: `pytest tests/integration` → **3 passed**. `services/registration-service`: `pytest tests/integration` → **4 passed** (201/confirmed con `amount==price`, `422 REFERENCE_NOT_FOUND` per user ed event sconosciuti, `503 DEPENDENCY_UNAVAILABLE` con dipendenze spente). |
| 6 | `collaudo.txt` dal run `-m mandatory` (T-16) | ✅ Fatto | `Exam/techconf-exam/collaudo.txt` presente con output reale: **27 passed, 10 deselected** (IT-U01..U08, IT-E01..E08, IT-R01..R10, IT-J01). |
| 7 | `BUGS.md` con ≥2 bug reali chiusi (T-18) | ⚠️ Parziale — richiede azione utente | `Exam/techconf-exam/BUGS.md` documenta **2 bug reali di implementazione** (BUG-001 memory backend senza isolamento; BUG-002 `validate_date` accetta date settimana ISO) con test di regressione già scritti e verdi e fix applicati sul working tree. **Non ancora chiusi formalmente**: `gh` CLI non disponibile (OPEN-REG-02), quindi le issue GitHub reali e i commit `(closes #N)` devono essere creati manualmente dall'utente. I numeri issue sono segnaposto `<ISSUE #TBD by user>`. |
| 8 | README presenti; file protetti non modificati (T-17) | ✅ Fatto | Questo README è presente e completo. Verifica SHA-256 di `CHECKSUMS.sha256`: **17/17 OK, 0 mismatch** — `contracts/`, `tests/integration/` e `CHECKSUMS.sha256` intatti. |

### Voci in sospeso (azione dell'utente richiesta)

- **Chiusura formale dei bug (§9.7):** aprire dal browser le 2 issue GitHub reali (una
  per BUG-001, una per BUG-002), sostituire i segnaposto `<ISSUE #TBD by user>` in
  `BUGS.md` con i numeri reali e creare i commit di fix con i messaggi indicati
  (`... (closes #N)`), quindi merge su `main`. I fix e i test di regressione sono già
  presenti nel working tree; manca solo la tracciatura formale su GitHub.
- **Tag `v1.0.0` (T-20):** da creare solo dopo il completamento reale di tutte le voci,
  incluse le issue chiuse (fuori dallo scope di T-19).

> Nota sull'hook: la validazione automatica (schema, matcher, esecuzione dello script)
> è confermata da terminale. La visualizzazione dello stato "abilitato" nel pannello
> *Agent Hooks* della IDE e l'attivazione al salvataggio interattivo di un `.py`
> restano una verifica manuale nella UI di Kiro.
