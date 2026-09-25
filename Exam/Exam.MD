# Esame pratico — Spec-Driven Development with Kiro

## Progetto: **TechConf** — microservizi per la gestione delle iscrizioni a conferenze tech

> **Modalità:** individuale. Tutti i partecipanti ricevono **la stessa traccia**.
> **Da implementare:** **3 microservizi obbligatori** + **2 opzionali** (bonus)
> **Strumenti:** Kiro IDE · Python 3.12 · Flask · pytest · Git (GitHub)
> **Nessun DBMS da installare:** persistenza in memoria o su file (JSON o SQLite con la libreria standard)

---

## 1. Scenario

Una società organizza conferenze tecniche (cloud, AI, security) e vuole una piattaforma a microservizi per gestire utenti, eventi e iscrizioni.

Il tuo compito è costruire, **con Kiro e solo in modalità Spec-Driven (Requirements-First)**, i microservizi descritti in questa traccia. I servizi devono:

- rispettare i **contratti OpenAPI** già forniti nel repository;
- **dialogare tra loro** via HTTP (es. l'iscrizione verifica che utente ed evento esistano);
- superare la **suite di collaudo** (test di integrazione già pronti, forniti dal docente), che simula sia le chiamate di un **client/utente** sia le chiamate **tra microservizi**.

---

## 2. Architettura

```
                      OBBLIGATORI                                 OPZIONALI
   ┌──────────────────────────────────────────────────┐   ┌──────────────────────────┐
   │                                                  │   │                          │
   │   ┌──────────────┐        ┌───────────────┐      │   │   ┌──────────────────┐   │
   │   │ user-service │◄───────┤ event-service │      │   │   │ feedback-service │   │
   │   │    :5001     │        │     :5002     │      │   │   │      :5004       │   │
   │   └──────▲───────┘        └───────▲───────┘      │   │   └──┬───────────┬───┘   │
   │          │                        │              │   │      │           │       │
   │          │   ┌────────────────────┴──┐           │   │      │           │       │
   │          └───┤ registration-service  │◄──────────┼───┼──────┘           │       │
   │              │        :5003          │◄──────────┼───┼───────┐          │       │
   │              └───────────────────────┘           │   │       │          │       │
   │                                                  │   │   ┌───┴──────────▼───┐   │
   └──────────────────────────────────────────────────┘   │   │notification-svc  │   │
                                                          │   │      :5005       │   │
                                                          │   └──────────────────┘   │
                                                          └──────────────────────────┘
   A ──► B  =  A chiama le API di B
```

| # | Servizio                       | Tipo         | Base path                 | Porta | Chiama              | Chiamato da                       |
| - | ------------------------------ | ------------ | ------------------------- | ----- | ------------------- | --------------------------------- |
| 1 | **user-service**         | Obbligatorio | `/api/v1/users`         | 5001  | —                  | event, registration, notification |
| 2 | **event-service**        | Obbligatorio | `/api/v1/events`        | 5002  | user                | registration, feedback            |
| 3 | **registration-service** | Obbligatorio | `/api/v1/registrations` | 5003  | user, event         | feedback, notification            |
| 4 | feedback-service               | Opzionale    | `/api/v1/feedbacks`     | 5004  | registration, event | —                                |
| 5 | notification-service           | Opzionale    | `/api/v1/notifications` | 5005  | user, registration  | —                                |

**Ordine consigliato:** user → event → registration → (feedback, notification).
Ogni servizio si appoggia ai precedenti, quindi puoi collaudarlo solo dopo averli completati.

---

## 3. Cosa ricevi (repository template)

Fai il **fork** del repository template `techconf-exam` fornito dal docente. Contiene:

| Percorso                     | Contenuto                                                                                                        | Modificabile?                  |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| `contracts/openapi/*.yaml` | Contratti OpenAPI 3.0 dei 5 servizi:**la fonte di verità** delle interfacce                               | ❌ NO                          |
| `contracts/validator.py`   | Helper`assert_matches_contract(service, method, path, response)` per validare una risposta contro il contratto | ❌ NO                          |
| `tests/integration/`       | **Suite di collaudo** già implementata (client → servizio, servizio → servizio, end-to-end)             | ❌ NO                          |
| `CHECKSUMS.sha256`         | Impronte dei file non modificabili (`sha256sum -c CHECKSUMS.sha256`)                                           | ❌ NO                          |
| `services.example.yaml`    | Esempio del**manifest** che la suite legge per avviare i tuoi servizi (vedi §4)                           | ✅ copialo in`services.yaml` |

Tutto il resto del repository, cioè cartelle, moduli, test e configurazione, **lo progetti tu**. L'organizzazione del codice fa parte del lavoro di spec-driven development: le domande guida sono al §7.

> I file in `contracts/` e `tests/integration/` sono protetti da checksum: se li modifichi, la penalità è pesante (vedi §8). Se pensi che un contratto sia sbagliato, apri una issue: **non** modificarlo.

---

## 4. Platform Standards (vincolanti per tutti i servizi)

Da inserire in Kiro come **steering file** (`.kiro/steering/platform-standards.md`).

| Tema                  | Regola                                                                                                                                                                                                                                                                                                                                                  |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Avvio dei servizi     | Un file`services.yaml` nella root dichiara, per ogni servizio implementato, la cartella di lavoro (`cwd`) e il comando di avvio (`command`). La suite di collaudo lo legge e passa a ogni servizio le variabili `PORT` e `*_SERVICE_URL`. Ogni servizio **deve** ascoltare sulla porta indicata da `PORT`                             |
| Base path             | `/api/v1/<risorsa>`                                                                                                                                                                                                                                                                                                                                   |
| Formato               | JSON, campi in`snake_case`                                                                                                                                                                                                                                                                                                                            |
| Identificativi        | `id` UUID v4 generato dal server, mai accettato in input                                                                                                                                                                                                                                                                                              |
| Timestamp             | ISO 8601 UTC (`2026-10-15T09:30:00Z`); ogni risorsa ha `created_at` e `updated_at`                                                                                                                                                                                                                                                                |
| Date / importi        | Date`YYYY-MM-DD` · importi numerici con 2 decimali (`149.00`), valuta implicita EUR                                                                                                                                                                                                                                                                |
| Paginazione           | `?page=1&page_size=20` (max 100) → `{"items": [...], "page": 1, "page_size": 20, "total": 57}`                                                                                                                                                                                                                                                     |
| Errori                | Sempre`{"error": {"code": "UPPER_SNAKE", "message": "...", "details": {...}}}`                                                                                                                                                                                                                                                                        |
| Status code           | 201 creazione (+ header`Location`) · 200 lettura/modifica · 204 cancellazione · 400 JSON malformato · 404 `NOT_FOUND` · 405 metodo non previsto · 409 conflitto · 422 `VALIDATION_ERROR` / `REFERENCE_NOT_FOUND` / regole di business · 503 `DEPENDENCY_UNAVAILABLE`                                                                  |
| Chiamate tra servizi  | URL solo da variabili d'ambiente (`USER_SERVICE_URL`, `EVENT_SERVICE_URL`, `REGISTRATION_SERVICE_URL`), default `http://localhost:<porta>`. Timeout 2 s. 404 dal servizio chiamato → 422 `REFERENCE_NOT_FOUND`; timeout, connessione rifiutata o 5xx → 503 `DEPENDENCY_UNAVAILABLE`                                                       |
| Health                | `GET /health` → `200 {"status": "ok", "service": "<nome>"}`                                                                                                                                                                                                                                                                                        |
| **Persistenza** | Variabile`STORAGE_BACKEND` = `memory` (default) · `json` · `sqlite`. Con `json`/`sqlite` i file vanno in `DATA_DIR` (default `./data`, esclusa da git). **Solo librerie standard** (`json`, `sqlite3`): nessun DBMS da installare o configurare. Il cambio di backend non deve richiedere modifiche alla logica di business |
| Dipendenze Python     | `flask`, `requests` (runtime) · `pytest`, `pytest-cov`, `responses` (test)                                                                                                                                                                                                                                                                   |

---

## 5. Requisiti dei microservizi

Campi comuni a **tutte** le risorse (non ripetuti sotto): `id` (uuid, read-only), `created_at`, `updated_at` (datetime, read-only).

Gli ID `REQ-…` sono suggeriti: usali in `requirements.md` e nei test per garantire la tracciabilità.

### 5.1 user-service — `/api/v1/users` · porta 5001 · **obbligatorio**

*Anagrafica utenti della piattaforma (partecipanti, speaker, organizzatori).*

| Campo          | Tipo   | Obbl. | Vincoli                                                              |
| -------------- | ------ | ----- | -------------------------------------------------------------------- |
| `first_name` | string | Sì   | 1–50 caratteri                                                      |
| `last_name`  | string | Sì   | 1–50 caratteri                                                      |
| `email`      | string | Sì   | formato email valido,**univoca** (case-insensitive)            |
| `company`    | string | No    | max 100                                                              |
| `role`       | enum   | No    | `attendee` \| `speaker` \| `organizer` — default `attendee` |

| Metodo | Path                                            | Successo | Errori        |
| ------ | ----------------------------------------------- | -------- | ------------- |
| POST   | `/api/v1/users`                               | 201      | 400, 422, 409 |
| GET    | `/api/v1/users?page=&page_size=&role=&email=` | 200      | 422           |
| GET    | `/api/v1/users/{id}`                          | 200      | 404           |
| PUT    | `/api/v1/users/{id}`                          | 200      | 404, 422, 409 |
| PATCH  | `/api/v1/users/{id}`                          | 200      | 404, 422, 409 |
| DELETE | `/api/v1/users/{id}`                          | 204      | 404           |

| ID          | Regola di business                        | Errore                      |
| ----------- | ----------------------------------------- | --------------------------- |
| REQ-USR-B01 | Email univoca, confronto case-insensitive | 409`EMAIL_ALREADY_EXISTS` |
| REQ-USR-B02 | L'email viene salvata in minuscolo        | —                          |
| REQ-USR-B03 | Filtri lista per`role` ed `email`     | —                          |

### 5.2 event-service — `/api/v1/events` · porta 5002 · **obbligatorio**

*Conferenze con ciclo di vita e capienza. Chiama **user-service** per validare l'organizzatore.*

| Campo            | Tipo    | Obbl. | Vincoli                                                          |
| ---------------- | ------- | ----- | ---------------------------------------------------------------- |
| `title`        | string  | Sì   | 3–120 caratteri                                                 |
| `description`  | string  | No    | max 2000                                                         |
| `organizer_id` | uuid    | Sì   | deve esistere in user-service con`role = organizer`            |
| `venue`        | string  | Sì   | max 100 (es. "Auditorium Roma")                                  |
| `city`         | string  | Sì   | max 60                                                           |
| `start_date`   | date    | Sì   | `YYYY-MM-DD`                                                   |
| `end_date`     | date    | Sì   | ≥`start_date`                                                 |
| `capacity`     | integer | Sì   | 1–10000                                                         |
| `price`        | decimal | Sì   | ≥ 0.00                                                          |
| `status`       | enum    | No    | `draft` \| `published` \| `cancelled` — default `draft` |

| Metodo | Path                                              | Successo | Errori        |
| ------ | ------------------------------------------------- | -------- | ------------- |
| POST   | `/api/v1/events`                                | 201      | 400, 422, 503 |
| GET    | `/api/v1/events?page=&page_size=&status=&city=` | 200      | 422           |
| GET    | `/api/v1/events/{id}`                           | 200      | 404           |
| PUT    | `/api/v1/events/{id}`                           | 200      | 404, 422, 503 |
| PATCH  | `/api/v1/events/{id}`                           | 200      | 404, 422, 503 |
| DELETE | `/api/v1/events/{id}`                           | 204      | 404           |

| ID          | Regola di business                                                                       | Errore                           |
| ----------- | ---------------------------------------------------------------------------------------- | -------------------------------- |
| REQ-EVT-B01 | `organizer_id` deve esistere (chiamata `GET /api/v1/users/{id}`)                     | 422`REFERENCE_NOT_FOUND`       |
| REQ-EVT-B02 | L'utente organizzatore deve avere`role = organizer`                                    | 422`INVALID_ORGANIZER`         |
| REQ-EVT-B03 | `end_date` ≥ `start_date`                                                           | 422`VALIDATION_ERROR`          |
| REQ-EVT-B04 | Transizioni ammesse:`draft→published`, `draft→cancelled`, `published→cancelled` | 422`INVALID_STATUS_TRANSITION` |
| REQ-EVT-B05 | user-service non raggiungibile                                                           | 503`DEPENDENCY_UNAVAILABLE`    |
| REQ-EVT-B06 | Filtri lista per`status` e `city`                                                    | —                               |

### 5.3 registration-service — `/api/v1/registrations` · porta 5003 · **obbligatorio**

*Iscrizioni degli utenti agli eventi. Chiama **user-service** ed **event-service**.*

| Campo        | Tipo    | Obbl.             | Vincoli                                                               |
| ------------ | ------- | ----------------- | --------------------------------------------------------------------- |
| `user_id`  | uuid    | Sì               | deve esistere in user-service                                         |
| `event_id` | uuid    | Sì               | deve esistere in event-service con`status = published`              |
| `amount`   | decimal | Read-only         | copiato da`event.price` al momento dell'iscrizione (mai dal client) |
| `status`   | enum    | Read-only in POST | `confirmed` \| `cancelled` — alla creazione sempre `confirmed` |

| Metodo | Path                                                                  | Successo | Errori             |
| ------ | --------------------------------------------------------------------- | -------- | ------------------ |
| POST   | `/api/v1/registrations`                                             | 201      | 400, 422, 409, 503 |
| GET    | `/api/v1/registrations?page=&page_size=&user_id=&event_id=&status=` | 200      | 422                |
| GET    | `/api/v1/registrations/{id}`                                        | 200      | 404                |
| PATCH  | `/api/v1/registrations/{id}` (solo `status`)                      | 200      | 404, 422           |
| DELETE | `/api/v1/registrations/{id}`                                        | 204      | 404                |
| GET    | `/api/v1/registrations/stats?event_id=`                             | 200      | 404, 422, 503      |
| PUT    | `/api/v1/registrations/{id}`                                        | —       | 405 (non previsto) |

| ID          | Regola di business                                                                                  | Errore                           |
| ----------- | --------------------------------------------------------------------------------------------------- | -------------------------------- |
| REQ-REG-B01 | `user_id` deve esistere                                                                           | 422`REFERENCE_NOT_FOUND`       |
| REQ-REG-B02 | `event_id` deve esistere                                                                          | 422`REFERENCE_NOT_FOUND`       |
| REQ-REG-B03 | L'evento deve essere`published`                                                                   | 422`EVENT_NOT_OPEN`            |
| REQ-REG-B04 | Un utente non può avere due iscrizioni`confirmed` allo stesso evento                             | 409`ALREADY_REGISTERED`        |
| REQ-REG-B05 | Iscrizioni`confirmed` per l'evento ≥ `event.capacity`                                          | 409`EVENT_FULL`                |
| REQ-REG-B06 | `amount` = `event.price` letto da event-service                                                 | —                               |
| REQ-REG-B07 | Unica transizione ammessa:`confirmed→cancelled`; un'iscrizione cancellata libera il posto        | 422`INVALID_STATUS_TRANSITION` |
| REQ-REG-B08 | `stats` restituisce `{event_id, capacity, confirmed, available}`; se l'evento non esiste → 404 | 404`NOT_FOUND`                 |
| REQ-REG-B09 | Dipendenza non raggiungibile                                                                        | 503`DEPENDENCY_UNAVAILABLE`    |

### 5.4 feedback-service — `/api/v1/feedbacks` · porta 5004 · *opzionale*

*Valutazioni degli eventi da parte degli iscritti. Chiama **registration-service** ed **event-service**.*

| Campo        | Tipo    | Obbl. | Vincoli                                          |
| ------------ | ------- | ----- | ------------------------------------------------ |
| `user_id`  | uuid    | Sì   | deve avere un'iscrizione`confirmed` all'evento |
| `event_id` | uuid    | Sì   | —                                               |
| `rating`   | integer | Sì   | 1–5                                             |
| `comment`  | string  | No    | max 500                                          |

| Metodo | Path                                                      | Successo | Errori             |
| ------ | --------------------------------------------------------- | -------- | ------------------ |
| POST   | `/api/v1/feedbacks`                                     | 201      | 400, 422, 409, 503 |
| GET    | `/api/v1/feedbacks?page=&page_size=&event_id=&user_id=` | 200      | 422                |
| GET    | `/api/v1/feedbacks/{id}`                                | 200      | 404                |
| PATCH  | `/api/v1/feedbacks/{id}` (`rating`, `comment`)      | 200      | 404, 422           |
| DELETE | `/api/v1/feedbacks/{id}`                                | 204      | 404                |
| GET    | `/api/v1/feedbacks/summary?event_id=`                   | 200      | 404, 422, 503      |

| ID          | Regola di business                                                                                                                                                   | Errore                         |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| REQ-FBK-B01 | Deve esistere un'iscrizione`confirmed` per `(user_id, event_id)` (chiamata `GET /api/v1/registrations?user_id=&event_id=&status=confirmed`)                    | 422`NOT_REGISTERED`          |
| REQ-FBK-B02 | Un solo feedback per`(user_id, event_id)`                                                                                                                          | 409`FEEDBACK_ALREADY_EXISTS` |
| REQ-FBK-B03 | `summary` restituisce `{event_id, count, average_rating}` (media a 2 decimali, `null` se `count = 0`); evento inesistente (verifica su event-service) → 404 | 404`NOT_FOUND`               |
| REQ-FBK-B04 | Dipendenza non raggiungibile                                                                                                                                         | 503`DEPENDENCY_UNAVAILABLE`  |

### 5.5 notification-service — `/api/v1/notifications` · porta 5005 · *opzionale*

*Notifiche agli utenti, anche massive verso gli iscritti a un evento. Chiama **user-service** e **registration-service**.*

| Campo       | Tipo     | Obbl.     | Vincoli                                                    |
| ----------- | -------- | --------- | ---------------------------------------------------------- |
| `user_id` | uuid     | Sì       | deve esistere in user-service                              |
| `channel` | enum     | Sì       | `email` \| `sms` \| `push`                           |
| `subject` | string   | Sì       | 1–150 caratteri                                           |
| `body`    | string   | Sì       | 1–5000 caratteri                                          |
| `status`  | enum     | No        | `queued` \| `sent` \| `failed` — default `queued` |
| `sent_at` | datetime | Read-only | valorizzato quando`status → sent`                       |

| Metodo | Path                                                                       | Successo | Errori        |
| ------ | -------------------------------------------------------------------------- | -------- | ------------- |
| POST   | `/api/v1/notifications`                                                  | 201      | 400, 422, 503 |
| GET    | `/api/v1/notifications?page=&page_size=&user_id=&status=`                | 200      | 422           |
| GET    | `/api/v1/notifications/{id}`                                             | 200      | 404           |
| PATCH  | `/api/v1/notifications/{id}` (solo `status`)                           | 200      | 404, 422      |
| DELETE | `/api/v1/notifications/{id}`                                             | 204      | 404           |
| POST   | `/api/v1/notifications/broadcast` `{event_id, channel, subject, body}` | 201      | 422, 503      |

| ID          | Regola di business                                                                                                                                    | Errore                           |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------- |
| REQ-NTF-B01 | `user_id` deve esistere                                                                                                                             | 422`REFERENCE_NOT_FOUND`       |
| REQ-NTF-B02 | Transizioni:`queued→sent`, `queued→failed`; `sent` e `failed` sono stati finali                                                             | 422`INVALID_STATUS_TRANSITION` |
| REQ-NTF-B03 | `broadcast` crea una notifica per ogni iscrizione `confirmed` all'evento (le `cancelled` sono escluse) e restituisce `{event_id, created: n}` | —                               |
| REQ-NTF-B04 | Dipendenza non raggiungibile                                                                                                                          | 503`DEPENDENCY_UNAVAILABLE`    |

---

## 6. Cosa devi fare

### 6.1 Setup Kiro

Apri la **root del repository** come workspace Kiro e crea:

- `.kiro/steering/product.md`: il dominio TechConf e lo scopo dei servizi
- `.kiro/steering/tech.md`: Python 3.12, Flask, requests, pytest, persistenza memory/json/sqlite
- `.kiro/steering/structure.md`: l'organizzazione del codice che **hai scelto tu**, con le motivazioni (vedi §7)
- `.kiro/steering/platform-standards.md`: il §4 di questa traccia
- almeno **1 Agent Hook** (es. "al salvataggio di un file Python esegui i test unitari del servizio")

### 6.2 Spec-Driven Development — solo workflow **Requirements-First**

Per **ogni** microservizio crea una spec `.kiro/specs/<servizio>/` e percorri le tre fasi **in ordine**, con un commit alla fine di ciascuna:

| Fase            | File                                                                                                                                                                                                                                            | Contenuto                                                                                                                                                                                               | Commit                        |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| 1. Requirements | `requirements.md`                                                                                                                                                                                                                             | User story + acceptance criteria in**notazione EARS** (`WHEN … THE SYSTEM SHALL …`, `IF … THEN …`). Copre tutti i campi, gli endpoint, le regole e gli errori del §5, con ID tracciabili | `spec(<svc>): requirements` |
| 2. Design       | `design.md` Componenti e responsabilità del servizio, gestione della persistenza (memory/json/sqlite), chiamate agli altri servizi e gestione errori, **riferimento al contratto** `contracts/openapi/<svc>.yaml`, strategia di test | `spec(<svc>): design`                                                                                                                                                                                 |                               |
| 3. Tasks        | `tasks.md`                                                                                                                                                                                                                                    | Task atomici tracciati ai requisiti (`_Requirements: REQ-REG-B05_`), inclusi i task di test                                                                                                           | `spec(<svc>): tasks`        |

Poi esegui i task **da Kiro** ("Start task"), uno alla volta, con un commit per task: `feat(<svc>): <task> [T-04]`.

**Vietato:** scrivere codice applicativo in modalità Vibe (la Vibe serve solo per i bug, §6.4), scrivere codice prima del commit di `tasks.md` (si verifica con `git log`), usare il workflow Design-First.

**Esempio di requisito EARS**

```markdown
### REQ-REG-B05 — Capienza evento
**User story:** As an organizer, I want registrations to stop when the event is full,
so that we never exceed the venue capacity.

**Acceptance criteria**
1. WHEN a registration is requested AND the confirmed registrations for the event are fewer
   than event.capacity THE registration-service SHALL create it with status "confirmed"
2. IF the confirmed registrations for the event are equal to event.capacity
   THEN THE registration-service SHALL respond 409 with error code "EVENT_FULL"
3. WHEN a confirmed registration is cancelled THE registration-service SHALL free one seat
```

### 6.3 Testing — cosa scrivi tu

Dove mettere i test è una tua scelta (vedi §7): conta che siano facili da trovare e da lanciare.

| Livello                      | Requisito minimo                                                                                                                                                                                                                                                                                |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Unit**               | pytest, dipendenze HTTP mockate con`responses`, repository testato con **tutti e tre** i backend (memory/json/sqlite, usando `tmp_path`), coverage ≥ **80%** (`pytest --cov=app`)                                                                                            |
| **Contratto**          | nei test unit, almeno**1 test per endpoint** che valida la risposta con `contracts/validator.py` (`assert_matches_contract`)                                                                                                                                                          |
| **Integration (tuoi)** | Per ogni servizio che chiama altri servizi: avvia**davvero** i servizi coinvolti (fixture pytest che li lancia in un thread o sottoprocesso su porte libere) e verifica almeno **1 caso positivo**, **1 riferimento inesistente (422)** e **1 dipendenza spenta (503)** |

Ogni test si deve poter ricondurre a un requisito: usa il marker `@pytest.mark.req("REQ-REG-B05")` oppure metti l'ID nel nome o nella docstring.

### 6.4 Collaudo — la suite già pronta

La suite in `tests/integration/` avvia i tuoi servizi e li verifica **dall'esterno**, come farebbe un client reale. **Non la modifichi: la esegui.**

```bash
pip install -r tests/integration/requirements.txt
pytest tests/integration -v                 # tutti i servizi dichiarati in services.yaml
pytest tests/integration -m mandatory -v    # solo i 3 obbligatori
pytest tests/integration -k registration -v # un singolo servizio
```

- Se un servizio non è dichiarato in `services.yaml`, i suoi test risultano **skipped** (non falliti).
- Ogni risposta viene validata contro il contratto OpenAPI: un campo in più, mancante o di tipo sbagliato fa fallire il test.
- I dati di test sono generati con valori univoci (email e titoli casuali): non serve alcun reset del database tra un'esecuzione e l'altra.
- Per i test di resilienza la suite avvia una seconda istanza del tuo servizio con l'URL della dipendenza puntato a una porta chiusa.
- In collaudo i servizi girano sulle porte **15001–15005** (e 15101+ per le istanze di resilienza), non su quelle di sviluppo: puoi lasciare aperti i tuoi servizi mentre lanci la suite. Il servizio deve quindi leggere sempre la porta da `PORT`.
- Nessun container: i servizi sono avviati come normali processi Python. I log finiscono in `.it-logs/<servizio>.log`.
- La suite conta **49 casi di test** (alcuni ID del catalogo hanno più varianti).

**Catalogo dei test di collaudo**

Legenda tipo: **C** = client → servizio · **S** = servizio → servizio · **R** = resilienza · **E2E** = percorso utente completo

| ID     | Servizio      | Tipo | Verifica                                                                                                                                                      |
| ------ | ------------- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| IT-U01 | user          | C    | POST valido → 201, header`Location`, body conforme al contratto                                                                                            |
| IT-U02 | user          | C    | Campo obbligatorio mancante → 422`VALIDATION_ERROR`                                                                                                        |
| IT-U03 | user          | C    | Email duplicata (maiuscole diverse) → 409`EMAIL_ALREADY_EXISTS`                                                                                            |
| IT-U04 | user          | C    | GET per id → 200; id inesistente → 404`NOT_FOUND`                                                                                                         |
| IT-U05 | user          | C    | Lista paginata e filtro`role`                                                                                                                               |
| IT-U06 | user          | C    | PUT e PATCH → 200,`updated_at` aggiornato                                                                                                                  |
| IT-U07 | user          | C    | DELETE → 204, poi GET → 404                                                                                                                                 |
| IT-U08 | user          | C    | JSON malformato → 400 ·`GET /health` → 200                                                                                                               |
| IT-E01 | event         | S    | Creazione con organizzatore valido → 201,`status = draft`                                                                                                  |
| IT-E02 | event         | S    | `organizer_id` inesistente → 422 `REFERENCE_NOT_FOUND`                                                                                                   |
| IT-E03 | event         | S    | Organizzatore con`role = attendee` → 422 `INVALID_ORGANIZER`                                                                                             |
| IT-E04 | event         | C    | `end_date` < `start_date` → 422                                                                                                                          |
| IT-E05 | event         | C    | `draft→published` → 200; `published→draft` → 422 `INVALID_STATUS_TRANSITION`                                                                        |
| IT-E06 | event         | C    | Filtri`status`, `city` e paginazione                                                                                                                      |
| IT-E07 | event         | C    | GET / PUT / PATCH / DELETE e 404                                                                                                                              |
| IT-E08 | event         | R    | user-service non raggiungibile → 503`DEPENDENCY_UNAVAILABLE`                                                                                               |
| IT-R01 | registration  | S    | Iscrizione a evento pubblicato → 201,`status = confirmed`, `amount = event.price`                                                                        |
| IT-R02 | registration  | S    | Utente inesistente → 422`REFERENCE_NOT_FOUND`                                                                                                              |
| IT-R03 | registration  | S    | Evento inesistente → 422`REFERENCE_NOT_FOUND`                                                                                                              |
| IT-R04 | registration  | S    | Evento in`draft` → 422 `EVENT_NOT_OPEN`                                                                                                                  |
| IT-R05 | registration  | C    | Doppia iscrizione → 409`ALREADY_REGISTERED`                                                                                                                |
| IT-R06 | registration  | S    | Evento con capienza 2: terza iscrizione → 409`EVENT_FULL`                                                                                                  |
| IT-R07 | registration  | S    | Cancellazione → 200 e posto liberato;`cancelled→confirmed` → 422                                                                                         |
| IT-R08 | registration  | S    | `stats` → `capacity`, `confirmed`, `available` corretti; evento inesistente → 404                                                                   |
| IT-R09 | registration  | C    | `PUT` → 405                                                                                                                                                |
| IT-R10 | registration  | R    | Dipendenza non raggiungibile → 503                                                                                                                           |
| IT-J01 | tutti (obbl.) | E2E  | Organizzatore e 3 partecipanti → evento (capienza 2) → pubblicazione → 2 iscrizioni → 3ª rifiutata → 1 cancellazione → 3ª accettata → stats coerenti |
| IT-F01 | feedback      | S    | Utente iscritto → 201                                                                                                                                        |
| IT-F02 | feedback      | S    | Utente non iscritto (o con iscrizione cancellata) → 422`NOT_REGISTERED`                                                                                    |
| IT-F03 | feedback      | C    | Doppio feedback → 409 ·`rating = 6` → 422                                                                                                                |
| IT-F04 | feedback      | S    | `summary` → `count` e `average_rating` corretti; evento inesistente → 404                                                                             |
| IT-F05 | feedback      | R    | registration-service non raggiungibile → 503                                                                                                                 |
| IT-N01 | notification  | S    | Creazione per utente esistente → 201,`status = queued`                                                                                                     |
| IT-N02 | notification  | S    | Utente inesistente → 422`REFERENCE_NOT_FOUND`                                                                                                              |
| IT-N03 | notification  | C    | `queued→sent` valorizza `sent_at`; `sent→queued` → 422                                                                                               |
| IT-N04 | notification  | S    | `broadcast` crea n notifiche solo per gli iscritti `confirmed`                                                                                            |
| IT-J02 | tutti         | E2E  | Come IT-J01 + feedback degli iscritti + broadcast di ringraziamento                                                                                           |

### 6.5 Gestione dei bug — approccio Vibe

Ogni test di collaudo fallito, e ogni bug che trovi, segue questo flusso:

1. **Issue GitHub** con: servizio, test fallito (es. `IT-R06`) o passi per riprodurre, comportamento atteso e ottenuto, **requisito violato**.
2. **Classificazione**:
   - **bug di implementazione** (la spec è corretta, il codice no) → fix in **Vibe session**;
   - **bug di specifica** (requisito mancante o sbagliato) → **niente Vibe**: aggiorni `requirements.md`, poi design e tasks, ed esegui il nuovo task dalla spec.
3. **Fix in Vibe** su branch `fix/<svc>-<issue#>`: nel prompt metti il testo dell'issue e l'output del test fallito; chiedi a Kiro **prima** un test di regressione che fallisce, **poi** il fix; alla fine devono essere verdi sia i test unit che la suite di collaudo.
4. **Commit** `fix(<svc>): <descrizione> (closes #N)` e merge sul tuo `main`.
5. **Registro** in `BUGS.md`:

| ID     | Issue | Trovato da | Tipo | Requisito   | Causa radice                                               | Test di regressione            | Commit      |
| ------ | ----- | ---------- | ---- | ----------- | ---------------------------------------------------------- | ------------------------------ | ----------- |
| BUG-01 | #3    | IT-R06     | impl | REQ-REG-B05 | Le iscrizioni`cancelled` venivano contate nella capienza | `test_cancelled_not_counted` | `a1b2c3d` |

Minimo richiesto: **2 bug** documentati e chiusi, di cui almeno 1 di implementazione.

### 6.6 Git

- Un repository per partecipante: il **fork** di `techconf-exam`.
- Commit convenzionali: `spec(…)`, `feat(…)`, `test(…)`, `fix(…)`, `docs(…)`, `chore(…)`.
- `data/` nel `.gitignore`.
- Consegna: tag `v1.0.0` sul `main` e link al repository al docente.

---

## 7. Organizzazione del codice — domande guida

Non esiste una struttura "giusta" imposta dalla traccia: **decidere come organizzare il codice fa parte della progettazione**. Prima di scrivere il primo `requirements.md`, rispondi a queste domande e scrivi le decisioni, con il loro perché, in `.kiro/steering/structure.md`. Kiro userà quel file come guida per ogni task: più le scelte sono chiare, più il codice generato sarà coerente.

**Repository e confini dei servizi**

- Un unico repository con tutti i servizi, o un repository per servizio? Cosa cambia per il versionamento, per la suite di collaudo e per l'aggiunta dei due servizi opzionali?
- Come rendi evidente, guardando le cartelle, dove finisce un servizio e dove inizia l'altro?
- Un servizio può importare codice di un altro servizio? Se no, come lo impedisci o lo rendi visibile?

**Codice condiviso e duplicazione**

- Formato degli errori, paginazione, client HTTP verso gli altri servizi, validazione: libreria condivisa o duplicazione in ogni servizio? Quale accoppiamento introduci in ciascun caso?
- Se un giorno un servizio dovesse essere sviluppato da un altro team, la tua scelta reggerebbe?

**Struttura interna di un servizio**

- Quali responsabilità separi (gestione HTTP, regole di business, persistenza, chiamate esterne)? Dove vivono le regole `REQ-*-B*`?
- Come fai in modo che il passaggio tra `memory`, `json` e `sqlite` non tocchi le regole di business?
- Come isoli le chiamate agli altri servizi, così da poterle simulare nei test unitari?

**Configurazione e avvio**

- Dove si leggono `PORT`, `*_SERVICE_URL`, `STORAGE_BACKEND`, `DATA_DIR`? In un solo punto o sparsi nel codice?
- Qual è il comando di avvio di ciascun servizio in `services.yaml`? È lo stesso per tutti?
- Dipendenze Python: un unico ambiente per tutto o un file di dipendenze per servizio? Cosa succede se due servizi richiedono versioni diverse della stessa libreria?

**Test**

- Dove vivono i test unitari e i tuoi test di integrazione? Vicino al codice del servizio o in una cartella centrale?
- Come avviano i tuoi test di integrazione i servizi reali, e come li spengono?
- Quale singolo comando esegue tutti i test di un servizio? E quale quelli dell'intera piattaforma?

**Spec e tracciabilità**

- Una spec Kiro per servizio, per funzionalità o per regola di business? Come si riflette questa scelta nelle cartelle?
- Partendo da un requisito `REQ-REG-B05`, quanto tempo serve a un collega per trovare il codice che lo implementa e il test che lo verifica?
- Cosa va in `structure.md` e cosa in `design.md`? Qual è la differenza tra una regola valida per tutto il repository e una decisione specifica di un servizio?

**Dati e Git**

- Dove finiscono i file di dati di `json`/`sqlite`? Sono esclusi da git?
- Come organizzi i commit per rendere leggibile la sequenza spec → task → codice?

> Queste risposte sono valutate insieme alla spec: una struttura coerente, motivata e rispettata da tutti i servizi conta quanto una struttura "elegante".

---

## 8. Criteri di valutazione (100 punti + bonus)

**Penalità**

- Modifica di `contracts/` o `tests/integration/`: **−20**
- Codice applicativo committato prima di `tasks.md`: **−15** per servizio
- Bug di specifica corretto in Vibe senza aggiornare la spec: **−5** per bug
- URL di altri servizi scritti nel codice invece che in variabili d'ambiente: **−5**
- Uso di un DBMS esterno: **−5**

---

## 9. Checklist di consegna

- [X] `.kiro/steering/` (4 file, con `structure.md` che risponde alle domande del §7) e almeno 1 hook
- [X] `.kiro/specs/<svc>/` con requirements, design e tasks (tutti spuntati) per i 3 servizi obbligatori
- [X] `services.yaml` compilato; servizi avviabili, backend `memory` / `json` / `sqlite` funzionanti
- [X] Unit test con coverage ≥ 80% per ogni servizio
- [X] Integration test propri per event-service e registration-service
- [X] `pytest tests/integration -m mandatory` eseguito, output salvato in `collaudo.txt`
- [X] `BUGS.md` con almeno 2 bug chiusi
- [X] `README.md` (avvio, variabili d'ambiente, comandi di test)
- [X] File in `contracts/` e `tests/integration/` **non modificati**
- [X] Tag `v1.0.0` sul `main`
