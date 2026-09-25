# Esame pratico â€” Spec-Driven Development with Kiro

## Progetto: **TechConf** â€” microservizi per la gestione delle iscrizioni a conferenze tech

> **ModalitÃ :** individuale. Tutti i partecipanti ricevono **la stessa traccia**.
> **Da implementare:** **3 microservizi obbligatori** + **2 opzionali** (bonus)
> **Strumenti:** Kiro IDE Â· Python 3.12 Â· Flask Â· pytest Â· Git (GitHub)
> **Nessun DBMS da installare:** persistenza in memoria o su file (JSON o SQLite con la libreria standard)

---

## 1. Scenario

Una societÃ  organizza conferenze tecniche (cloud, AI, security) e vuole una piattaforma a microservizi per gestire utenti, eventi e iscrizioni.

Il tuo compito Ã¨ costruire, **con Kiro e solo in modalitÃ  Spec-Driven (Requirements-First)**, i microservizi descritti in questa traccia. I servizi devono:

- rispettare i **contratti OpenAPI** giÃ  forniti nel repository;
- **dialogare tra loro** via HTTP (es. l'iscrizione verifica che utente ed evento esistano);
- superare la **suite di collaudo** (test di integrazione giÃ  pronti, forniti dal docente), che simula sia le chiamate di un **client/utente** sia le chiamate **tra microservizi**.

---

## 2. Architettura

```
                      OBBLIGATORI                                 OPZIONALI
   â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”   â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
   â”‚                                                  â”‚   â”‚                          â”‚
   â”‚   â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”        â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”      â”‚   â”‚   â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”   â”‚
   â”‚   â”‚ user-service â”‚â—„â”€â”€â”€â”€â”€â”€â”€â”¤ event-service â”‚      â”‚   â”‚   â”‚ feedback-service â”‚   â”‚
   â”‚   â”‚    :5001     â”‚        â”‚     :5002     â”‚      â”‚   â”‚   â”‚      :5004       â”‚   â”‚
   â”‚   â””â”€â”€â”€â”€â”€â”€â–²â”€â”€â”€â”€â”€â”€â”€â”˜        â””â”€â”€â”€â”€â”€â”€â”€â–²â”€â”€â”€â”€â”€â”€â”€â”˜      â”‚   â”‚   â””â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”˜   â”‚
   â”‚          â”‚                        â”‚              â”‚   â”‚      â”‚           â”‚       â”‚
   â”‚          â”‚   â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”           â”‚   â”‚      â”‚           â”‚       â”‚
   â”‚          â””â”€â”€â”€â”¤ registration-service  â”‚â—„â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”˜           â”‚       â”‚
   â”‚              â”‚        :5003          â”‚â—„â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”          â”‚       â”‚
   â”‚              â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜           â”‚   â”‚       â”‚          â”‚       â”‚
   â”‚                                                  â”‚   â”‚   â”Œâ”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”   â”‚
   â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜   â”‚   â”‚notification-svc  â”‚   â”‚
                                                          â”‚   â”‚      :5005       â”‚   â”‚
                                                          â”‚   â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜   â”‚
                                                          â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
   A â”€â”€â–º B  =  A chiama le API di B
```

| # | Servizio                       | Tipo         | Base path                 | Porta | Chiama              | Chiamato da                       |
| - | ------------------------------ | ------------ | ------------------------- | ----- | ------------------- | --------------------------------- |
| 1 | **user-service**         | Obbligatorio | `/api/v1/users`         | 5001  | â€”                  | event, registration, notification |
| 2 | **event-service**        | Obbligatorio | `/api/v1/events`        | 5002  | user                | registration, feedback            |
| 3 | **registration-service** | Obbligatorio | `/api/v1/registrations` | 5003  | user, event         | feedback, notification            |
| 4 | feedback-service               | Opzionale    | `/api/v1/feedbacks`     | 5004  | registration, event | â€”                                |
| 5 | notification-service           | Opzionale    | `/api/v1/notifications` | 5005  | user, registration  | â€”                                |

**Ordine consigliato:** user â†’ event â†’ registration â†’ (feedback, notification).
Ogni servizio si appoggia ai precedenti, quindi puoi collaudarlo solo dopo averli completati.

---

## 3. Cosa ricevi (repository template)

Fai il **fork** del repository template `techconf-exam` fornito dal docente. Contiene:

| Percorso                     | Contenuto                                                                                                        | Modificabile?                  |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| `contracts/openapi/*.yaml` | Contratti OpenAPI 3.0 dei 5 servizi:**la fonte di veritÃ ** delle interfacce                               | âŒ NO                          |
| `contracts/validator.py`   | Helper`assert_matches_contract(service, method, path, response)` per validare una risposta contro il contratto | âŒ NO                          |
| `tests/integration/`       | **Suite di collaudo** giÃ  implementata (client â†’ servizio, servizio â†’ servizio, end-to-end)             | âŒ NO                          |
| `CHECKSUMS.sha256`         | Impronte dei file non modificabili (`sha256sum -c CHECKSUMS.sha256`)                                           | âŒ NO                          |
| `services.example.yaml`    | Esempio del**manifest** che la suite legge per avviare i tuoi servizi (vedi Â§4)                           | âœ… copialo in`services.yaml` |

Tutto il resto del repository, cioÃ¨ cartelle, moduli, test e configurazione, **lo progetti tu**. L'organizzazione del codice fa parte del lavoro di spec-driven development: le domande guida sono al Â§7.

> I file in `contracts/` e `tests/integration/` sono protetti da checksum: se li modifichi, la penalitÃ  Ã¨ pesante (vedi Â§8). Se pensi che un contratto sia sbagliato, apri una issue: **non** modificarlo.

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
| Date / importi        | Date`YYYY-MM-DD` Â· importi numerici con 2 decimali (`149.00`), valuta implicita EUR                                                                                                                                                                                                                                                                |
| Paginazione           | `?page=1&page_size=20` (max 100) â†’ `{"items": [...], "page": 1, "page_size": 20, "total": 57}`                                                                                                                                                                                                                                                     |
| Errori                | Sempre`{"error": {"code": "UPPER_SNAKE", "message": "...", "details": {...}}}`                                                                                                                                                                                                                                                                        |
| Status code           | 201 creazione (+ header`Location`) Â· 200 lettura/modifica Â· 204 cancellazione Â· 400 JSON malformato Â· 404 `NOT_FOUND` Â· 405 metodo non previsto Â· 409 conflitto Â· 422 `VALIDATION_ERROR` / `REFERENCE_NOT_FOUND` / regole di business Â· 503 `DEPENDENCY_UNAVAILABLE`                                                                  |
| Chiamate tra servizi  | URL solo da variabili d'ambiente (`USER_SERVICE_URL`, `EVENT_SERVICE_URL`, `REGISTRATION_SERVICE_URL`), default `http://localhost:<porta>`. Timeout 2 s. 404 dal servizio chiamato â†’ 422 `REFERENCE_NOT_FOUND`; timeout, connessione rifiutata o 5xx â†’ 503 `DEPENDENCY_UNAVAILABLE`                                                       |
| Health                | `GET /health` â†’ `200 {"status": "ok", "service": "<nome>"}`                                                                                                                                                                                                                                                                                        |
| **Persistenza** | Variabile`STORAGE_BACKEND` = `memory` (default) Â· `json` Â· `sqlite`. Con `json`/`sqlite` i file vanno in `DATA_DIR` (default `./data`, esclusa da git). **Solo librerie standard** (`json`, `sqlite3`): nessun DBMS da installare o configurare. Il cambio di backend non deve richiedere modifiche alla logica di business |
| Dipendenze Python     | `flask`, `requests` (runtime) Â· `pytest`, `pytest-cov`, `responses` (test)                                                                                                                                                                                                                                                                   |

---

## 5. Requisiti dei microservizi

Campi comuni a **tutte** le risorse (non ripetuti sotto): `id` (uuid, read-only), `created_at`, `updated_at` (datetime, read-only).

Gli ID `REQ-â€¦` sono suggeriti: usali in `requirements.md` e nei test per garantire la tracciabilitÃ .

### 5.1 user-service â€” `/api/v1/users` Â· porta 5001 Â· **obbligatorio**

*Anagrafica utenti della piattaforma (partecipanti, speaker, organizzatori).*

| Campo          | Tipo   | Obbl. | Vincoli                                                              |
| -------------- | ------ | ----- | -------------------------------------------------------------------- |
| `first_name` | string | SÃ¬   | 1â€“50 caratteri                                                      |
| `last_name`  | string | SÃ¬   | 1â€“50 caratteri                                                      |
| `email`      | string | SÃ¬   | formato email valido,**univoca** (case-insensitive)            |
| `company`    | string | No    | max 100                                                              |
| `role`       | enum   | No    | `attendee` \| `speaker` \| `organizer` â€” default `attendee` |

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
| REQ-USR-B02 | L'email viene salvata in minuscolo        | â€”                          |
| REQ-USR-B03 | Filtri lista per`role` ed `email`     | â€”                          |

### 5.2 event-service â€” `/api/v1/events` Â· porta 5002 Â· **obbligatorio**

*Conferenze con ciclo di vita e capienza. Chiama **user-service** per validare l'organizzatore.*

| Campo            | Tipo    | Obbl. | Vincoli                                                          |
| ---------------- | ------- | ----- | ---------------------------------------------------------------- |
| `title`        | string  | SÃ¬   | 3â€“120 caratteri                                                 |
| `description`  | string  | No    | max 2000                                                         |
| `organizer_id` | uuid    | SÃ¬   | deve esistere in user-service con`role = organizer`            |
| `venue`        | string  | SÃ¬   | max 100 (es. "Auditorium Roma")                                  |
| `city`         | string  | SÃ¬   | max 60                                                           |
| `start_date`   | date    | SÃ¬   | `YYYY-MM-DD`                                                   |
| `end_date`     | date    | SÃ¬   | â‰¥`start_date`                                                 |
| `capacity`     | integer | SÃ¬   | 1â€“10000                                                         |
| `price`        | decimal | SÃ¬   | â‰¥ 0.00                                                          |
| `status`       | enum    | No    | `draft` \| `published` \| `cancelled` â€” default `draft` |

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
| REQ-EVT-B03 | `end_date` â‰¥ `start_date`                                                           | 422`VALIDATION_ERROR`          |
| REQ-EVT-B04 | Transizioni ammesse:`draftâ†’published`, `draftâ†’cancelled`, `publishedâ†’cancelled` | 422`INVALID_STATUS_TRANSITION` |
| REQ-EVT-B05 | user-service non raggiungibile                                                           | 503`DEPENDENCY_UNAVAILABLE`    |
| REQ-EVT-B06 | Filtri lista per`status` e `city`                                                    | â€”                               |

### 5.3 registration-service â€” `/api/v1/registrations` Â· porta 5003 Â· **obbligatorio**

*Iscrizioni degli utenti agli eventi. Chiama **user-service** ed **event-service**.*

| Campo        | Tipo    | Obbl.             | Vincoli                                                               |
| ------------ | ------- | ----------------- | --------------------------------------------------------------------- |
| `user_id`  | uuid    | SÃ¬               | deve esistere in user-service                                         |
| `event_id` | uuid    | SÃ¬               | deve esistere in event-service con`status = published`              |
| `amount`   | decimal | Read-only         | copiato da`event.price` al momento dell'iscrizione (mai dal client) |
| `status`   | enum    | Read-only in POST | `confirmed` \| `cancelled` â€” alla creazione sempre `confirmed` |

| Metodo | Path                                                                  | Successo | Errori             |
| ------ | --------------------------------------------------------------------- | -------- | ------------------ |
| POST   | `/api/v1/registrations`                                             | 201      | 400, 422, 409, 503 |
| GET    | `/api/v1/registrations?page=&page_size=&user_id=&event_id=&status=` | 200      | 422                |
| GET    | `/api/v1/registrations/{id}`                                        | 200      | 404                |
| PATCH  | `/api/v1/registrations/{id}` (solo `status`)                      | 200      | 404, 422           |
| DELETE | `/api/v1/registrations/{id}`                                        | 204      | 404                |
| GET    | `/api/v1/registrations/stats?event_id=`                             | 200      | 404, 422, 503      |
| PUT    | `/api/v1/registrations/{id}`                                        | â€”       | 405 (non previsto) |

| ID          | Regola di business                                                                                  | Errore                           |
| ----------- | --------------------------------------------------------------------------------------------------- | -------------------------------- |
| REQ-REG-B01 | `user_id` deve esistere                                                                           | 422`REFERENCE_NOT_FOUND`       |
| REQ-REG-B02 | `event_id` deve esistere                                                                          | 422`REFERENCE_NOT_FOUND`       |
| REQ-REG-B03 | L'evento deve essere`published`                                                                   | 422`EVENT_NOT_OPEN`            |
| REQ-REG-B04 | Un utente non puÃ² avere due iscrizioni`confirmed` allo stesso evento                             | 409`ALREADY_REGISTERED`        |
| REQ-REG-B05 | Iscrizioni`confirmed` per l'evento â‰¥ `event.capacity`                                          | 409`EVENT_FULL`                |
| REQ-REG-B06 | `amount` = `event.price` letto da event-service                                                 | â€”                               |
| REQ-REG-B07 | Unica transizione ammessa:`confirmedâ†’cancelled`; un'iscrizione cancellata libera il posto        | 422`INVALID_STATUS_TRANSITION` |
| REQ-REG-B08 | `stats` restituisce `{event_id, capacity, confirmed, available}`; se l'evento non esiste â†’ 404 | 404`NOT_FOUND`                 |
| REQ-REG-B09 | Dipendenza non raggiungibile                                                                        | 503`DEPENDENCY_UNAVAILABLE`    |

### 5.4 feedback-service â€” `/api/v1/feedbacks` Â· porta 5004 Â· *opzionale*

*Valutazioni degli eventi da parte degli iscritti. Chiama **registration-service** ed **event-service**.*

| Campo        | Tipo    | Obbl. | Vincoli                                          |
| ------------ | ------- | ----- | ------------------------------------------------ |
| `user_id`  | uuid    | SÃ¬   | deve avere un'iscrizione`confirmed` all'evento |
| `event_id` | uuid    | SÃ¬   | â€”                                               |
| `rating`   | integer | SÃ¬   | 1â€“5                                             |
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
| REQ-FBK-B03 | `summary` restituisce `{event_id, count, average_rating}` (media a 2 decimali, `null` se `count = 0`); evento inesistente (verifica su event-service) â†’ 404 | 404`NOT_FOUND`               |
| REQ-FBK-B04 | Dipendenza non raggiungibile                                                                                                                                         | 503`DEPENDENCY_UNAVAILABLE`  |

### 5.5 notification-service â€” `/api/v1/notifications` Â· porta 5005 Â· *opzionale*

*Notifiche agli utenti, anche massive verso gli iscritti a un evento. Chiama **user-service** e **registration-service**.*

| Campo       | Tipo     | Obbl.     | Vincoli                                                    |
| ----------- | -------- | --------- | ---------------------------------------------------------- |
| `user_id` | uuid     | SÃ¬       | deve esistere in user-service                              |
| `channel` | enum     | SÃ¬       | `email` \| `sms` \| `push`                           |
| `subject` | string   | SÃ¬       | 1â€“150 caratteri                                           |
| `body`    | string   | SÃ¬       | 1â€“5000 caratteri                                          |
| `status`  | enum     | No        | `queued` \| `sent` \| `failed` â€” default `queued` |
| `sent_at` | datetime | Read-only | valorizzato quando`status â†’ sent`                       |

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
| REQ-NTF-B02 | Transizioni:`queuedâ†’sent`, `queuedâ†’failed`; `sent` e `failed` sono stati finali                                                             | 422`INVALID_STATUS_TRANSITION` |
| REQ-NTF-B03 | `broadcast` crea una notifica per ogni iscrizione `confirmed` all'evento (le `cancelled` sono escluse) e restituisce `{event_id, created: n}` | â€”                               |
| REQ-NTF-B04 | Dipendenza non raggiungibile                                                                                                                          | 503`DEPENDENCY_UNAVAILABLE`    |

---

## 6. Cosa devi fare

### 6.1 Setup Kiro

Apri la **root del repository** come workspace Kiro e crea:

- `.kiro/steering/product.md`: il dominio TechConf e lo scopo dei servizi
- `.kiro/steering/tech.md`: Python 3.12, Flask, requests, pytest, persistenza memory/json/sqlite
- `.kiro/steering/structure.md`: l'organizzazione del codice che **hai scelto tu**, con le motivazioni (vedi Â§7)
- `.kiro/steering/platform-standards.md`: il Â§4 di questa traccia
- almeno **1 Agent Hook** (es. "al salvataggio di un file Python esegui i test unitari del servizio")

### 6.2 Spec-Driven Development â€” solo workflow **Requirements-First**

Per **ogni** microservizio crea una spec `.kiro/specs/<servizio>/` e percorri le tre fasi **in ordine**, con un commit alla fine di ciascuna:

| Fase            | File                                                                                                                                                                                                                                            | Contenuto                                                                                                                                                                                               | Commit                        |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| 1. Requirements | `requirements.md`                                                                                                                                                                                                                             | User story + acceptance criteria in**notazione EARS** (`WHEN â€¦ THE SYSTEM SHALL â€¦`, `IF â€¦ THEN â€¦`). Copre tutti i campi, gli endpoint, le regole e gli errori del Â§5, con ID tracciabili | `spec(<svc>): requirements` |
| 2. Design       | `design.md` Componenti e responsabilitÃ  del servizio, gestione della persistenza (memory/json/sqlite), chiamate agli altri servizi e gestione errori, **riferimento al contratto** `contracts/openapi/<svc>.yaml`, strategia di test | `spec(<svc>): design`                                                                                                                                                                                 |                               |
| 3. Tasks        | `tasks.md`                                                                                                                                                                                                                                    | Task atomici tracciati ai requisiti (`_Requirements: REQ-REG-B05_`), inclusi i task di test                                                                                                           | `spec(<svc>): tasks`        |

Poi esegui i task **da Kiro** ("Start task"), uno alla volta, con un commit per task: `feat(<svc>): <task> [T-04]`.

**Vietato:** scrivere codice applicativo in modalitÃ  Vibe (la Vibe serve solo per i bug, Â§6.4), scrivere codice prima del commit di `tasks.md` (si verifica con `git log`), usare il workflow Design-First.

**Esempio di requisito EARS**

```markdown
### REQ-REG-B05 â€” Capienza evento
**User story:** As an organizer, I want registrations to stop when the event is full,
so that we never exceed the venue capacity.

**Acceptance criteria**
1. WHEN a registration is requested AND the confirmed registrations for the event are fewer
   than event.capacity THE registration-service SHALL create it with status "confirmed"
2. IF the confirmed registrations for the event are equal to event.capacity
   THEN THE registration-service SHALL respond 409 with error code "EVENT_FULL"
3. WHEN a confirmed registration is cancelled THE registration-service SHALL free one seat
```

### 6.3 Testing â€” cosa scrivi tu

Dove mettere i test Ã¨ una tua scelta (vedi Â§7): conta che siano facili da trovare e da lanciare.

| Livello                      | Requisito minimo                                                                                                                                                                                                                                                                                |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Unit**               | pytest, dipendenze HTTP mockate con`responses`, repository testato con **tutti e tre** i backend (memory/json/sqlite, usando `tmp_path`), coverage â‰¥ **80%** (`pytest --cov=app`)                                                                                            |
| **Contratto**          | nei test unit, almeno**1 test per endpoint** che valida la risposta con `contracts/validator.py` (`assert_matches_contract`)                                                                                                                                                          |
| **Integration (tuoi)** | Per ogni servizio che chiama altri servizi: avvia**davvero** i servizi coinvolti (fixture pytest che li lancia in un thread o sottoprocesso su porte libere) e verifica almeno **1 caso positivo**, **1 riferimento inesistente (422)** e **1 dipendenza spenta (503)** |

Ogni test si deve poter ricondurre a un requisito: usa il marker `@pytest.mark.req("REQ-REG-B05")` oppure metti l'ID nel nome o nella docstring.

### 6.4 Collaudo â€” la suite giÃ  pronta

La suite in `tests/integration/` avvia i tuoi servizi e li verifica **dall'esterno**, come farebbe un client reale. **Non la modifichi: la esegui.**

```bash
pip install -r tests/integration/requirements.txt
pytest tests/integration -v                 # tutti i servizi dichiarati in services.yaml
pytest tests/integration -m mandatory -v    # solo i 3 obbligatori
pytest tests/integration -k registration -v # un singolo servizio
```

- Se un servizio non Ã¨ dichiarato in `services.yaml`, i suoi test risultano **skipped** (non falliti).
- Ogni risposta viene validata contro il contratto OpenAPI: un campo in piÃ¹, mancante o di tipo sbagliato fa fallire il test.
- I dati di test sono generati con valori univoci (email e titoli casuali): non serve alcun reset del database tra un'esecuzione e l'altra.
- Per i test di resilienza la suite avvia una seconda istanza del tuo servizio con l'URL della dipendenza puntato a una porta chiusa.
- In collaudo i servizi girano sulle porte **15001â€“15005** (e 15101+ per le istanze di resilienza), non su quelle di sviluppo: puoi lasciare aperti i tuoi servizi mentre lanci la suite. Il servizio deve quindi leggere sempre la porta da `PORT`.
- Nessun container: i servizi sono avviati come normali processi Python. I log finiscono in `.it-logs/<servizio>.log`.
- La suite conta **49 casi di test** (alcuni ID del catalogo hanno piÃ¹ varianti).

**Catalogo dei test di collaudo**

Legenda tipo: **C** = client â†’ servizio Â· **S** = servizio â†’ servizio Â· **R** = resilienza Â· **E2E** = percorso utente completo

| ID     | Servizio      | Tipo | Verifica                                                                                                                                                      |
| ------ | ------------- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| IT-U01 | user          | C    | POST valido â†’ 201, header`Location`, body conforme al contratto                                                                                            |
| IT-U02 | user          | C    | Campo obbligatorio mancante â†’ 422`VALIDATION_ERROR`                                                                                                        |
| IT-U03 | user          | C    | Email duplicata (maiuscole diverse) â†’ 409`EMAIL_ALREADY_EXISTS`                                                                                            |
| IT-U04 | user          | C    | GET per id â†’ 200; id inesistente â†’ 404`NOT_FOUND`                                                                                                         |
| IT-U05 | user          | C    | Lista paginata e filtro`role`                                                                                                                               |
| IT-U06 | user          | C    | PUT e PATCH â†’ 200,`updated_at` aggiornato                                                                                                                  |
| IT-U07 | user          | C    | DELETE â†’ 204, poi GET â†’ 404                                                                                                                                 |
| IT-U08 | user          | C    | JSON malformato â†’ 400 Â·`GET /health` â†’ 200                                                                                                               |
| IT-E01 | event         | S    | Creazione con organizzatore valido â†’ 201,`status = draft`                                                                                                  |
| IT-E02 | event         | S    | `organizer_id` inesistente â†’ 422 `REFERENCE_NOT_FOUND`                                                                                                   |
| IT-E03 | event         | S    | Organizzatore con`role = attendee` â†’ 422 `INVALID_ORGANIZER`                                                                                             |
| IT-E04 | event         | C    | `end_date` < `start_date` â†’ 422                                                                                                                          |
| IT-E05 | event         | C    | `draftâ†’published` â†’ 200; `publishedâ†’draft` â†’ 422 `INVALID_STATUS_TRANSITION`                                                                        |
| IT-E06 | event         | C    | Filtri`status`, `city` e paginazione                                                                                                                      |
| IT-E07 | event         | C    | GET / PUT / PATCH / DELETE e 404                                                                                                                              |
| IT-E08 | event         | R    | user-service non raggiungibile â†’ 503`DEPENDENCY_UNAVAILABLE`                                                                                               |
| IT-R01 | registration  | S    | Iscrizione a evento pubblicato â†’ 201,`status = confirmed`, `amount = event.price`                                                                        |
| IT-R02 | registration  | S    | Utente inesistente â†’ 422`REFERENCE_NOT_FOUND`                                                                                                              |
| IT-R03 | registration  | S    | Evento inesistente â†’ 422`REFERENCE_NOT_FOUND`                                                                                                              |
| IT-R04 | registration  | S    | Evento in`draft` â†’ 422 `EVENT_NOT_OPEN`                                                                                                                  |
| IT-R05 | registration  | C    | Doppia iscrizione â†’ 409`ALREADY_REGISTERED`                                                                                                                |
| IT-R06 | registration  | S    | Evento con capienza 2: terza iscrizione â†’ 409`EVENT_FULL`                                                                                                  |
| IT-R07 | registration  | S    | Cancellazione â†’ 200 e posto liberato;`cancelledâ†’confirmed` â†’ 422                                                                                         |
| IT-R08 | registration  | S    | `stats` â†’ `capacity`, `confirmed`, `available` corretti; evento inesistente â†’ 404                                                                   |
| IT-R09 | registration  | C    | `PUT` â†’ 405                                                                                                                                                |
| IT-R10 | registration  | R    | Dipendenza non raggiungibile â†’ 503                                                                                                                           |
| IT-J01 | tutti (obbl.) | E2E  | Organizzatore e 3 partecipanti â†’ evento (capienza 2) â†’ pubblicazione â†’ 2 iscrizioni â†’ 3Âª rifiutata â†’ 1 cancellazione â†’ 3Âª accettata â†’ stats coerenti |
| IT-F01 | feedback      | S    | Utente iscritto â†’ 201                                                                                                                                        |
| IT-F02 | feedback      | S    | Utente non iscritto (o con iscrizione cancellata) â†’ 422`NOT_REGISTERED`                                                                                    |
| IT-F03 | feedback      | C    | Doppio feedback â†’ 409 Â·`rating = 6` â†’ 422                                                                                                                |
| IT-F04 | feedback      | S    | `summary` â†’ `count` e `average_rating` corretti; evento inesistente â†’ 404                                                                             |
| IT-F05 | feedback      | R    | registration-service non raggiungibile â†’ 503                                                                                                                 |
| IT-N01 | notification  | S    | Creazione per utente esistente â†’ 201,`status = queued`                                                                                                     |
| IT-N02 | notification  | S    | Utente inesistente â†’ 422`REFERENCE_NOT_FOUND`                                                                                                              |
| IT-N03 | notification  | C    | `queuedâ†’sent` valorizza `sent_at`; `sentâ†’queued` â†’ 422                                                                                               |
| IT-N04 | notification  | S    | `broadcast` crea n notifiche solo per gli iscritti `confirmed`                                                                                            |
| IT-J02 | tutti         | E2E  | Come IT-J01 + feedback degli iscritti + broadcast di ringraziamento                                                                                           |

### 6.5 Gestione dei bug â€” approccio Vibe

Ogni test di collaudo fallito, e ogni bug che trovi, segue questo flusso:

1. **Issue GitHub** con: servizio, test fallito (es. `IT-R06`) o passi per riprodurre, comportamento atteso e ottenuto, **requisito violato**.
2. **Classificazione**:
   - **bug di implementazione** (la spec Ã¨ corretta, il codice no) â†’ fix in **Vibe session**;
   - **bug di specifica** (requisito mancante o sbagliato) â†’ **niente Vibe**: aggiorni `requirements.md`, poi design e tasks, ed esegui il nuovo task dalla spec.
3. **Fix in Vibe** su branch `fix/<svc>-<issue#>`: nel prompt metti il testo dell'issue e l'output del test fallito; chiedi a Kiro **prima** un test di regressione che fallisce, **poi** il fix; alla fine devono essere verdi sia i test unit che la suite di collaudo.
4. **Commit** `fix(<svc>): <descrizione> (closes #N)` e merge sul tuo `main`.
5. **Registro** in `BUGS.md`:

| ID     | Issue | Trovato da | Tipo | Requisito   | Causa radice                                               | Test di regressione            | Commit      |
| ------ | ----- | ---------- | ---- | ----------- | ---------------------------------------------------------- | ------------------------------ | ----------- |
| BUG-01 | #3    | IT-R06     | impl | REQ-REG-B05 | Le iscrizioni`cancelled` venivano contate nella capienza | `test_cancelled_not_counted` | `a1b2c3d` |

Minimo richiesto: **2 bug** documentati e chiusi, di cui almeno 1 di implementazione.

### 6.6 Git

- Un repository per partecipante: il **fork** di `techconf-exam`.
- Commit convenzionali: `spec(â€¦)`, `feat(â€¦)`, `test(â€¦)`, `fix(â€¦)`, `docs(â€¦)`, `chore(â€¦)`.
- `data/` nel `.gitignore`.
- Consegna: tag `v1.0.0` sul `main` e link al repository al docente.

---

## 7. Organizzazione del codice â€” domande guida

Non esiste una struttura "giusta" imposta dalla traccia: **decidere come organizzare il codice fa parte della progettazione**. Prima di scrivere il primo `requirements.md`, rispondi a queste domande e scrivi le decisioni, con il loro perchÃ©, in `.kiro/steering/structure.md`. Kiro userÃ  quel file come guida per ogni task: piÃ¹ le scelte sono chiare, piÃ¹ il codice generato sarÃ  coerente.

**Repository e confini dei servizi**

- Un unico repository con tutti i servizi, o un repository per servizio? Cosa cambia per il versionamento, per la suite di collaudo e per l'aggiunta dei due servizi opzionali?
- Come rendi evidente, guardando le cartelle, dove finisce un servizio e dove inizia l'altro?
- Un servizio puÃ² importare codice di un altro servizio? Se no, come lo impedisci o lo rendi visibile?

**Codice condiviso e duplicazione**

- Formato degli errori, paginazione, client HTTP verso gli altri servizi, validazione: libreria condivisa o duplicazione in ogni servizio? Quale accoppiamento introduci in ciascun caso?
- Se un giorno un servizio dovesse essere sviluppato da un altro team, la tua scelta reggerebbe?

**Struttura interna di un servizio**

- Quali responsabilitÃ  separi (gestione HTTP, regole di business, persistenza, chiamate esterne)? Dove vivono le regole `REQ-*-B*`?
- Come fai in modo che il passaggio tra `memory`, `json` e `sqlite` non tocchi le regole di business?
- Come isoli le chiamate agli altri servizi, cosÃ¬ da poterle simulare nei test unitari?

**Configurazione e avvio**

- Dove si leggono `PORT`, `*_SERVICE_URL`, `STORAGE_BACKEND`, `DATA_DIR`? In un solo punto o sparsi nel codice?
- Qual Ã¨ il comando di avvio di ciascun servizio in `services.yaml`? Ãˆ lo stesso per tutti?
- Dipendenze Python: un unico ambiente per tutto o un file di dipendenze per servizio? Cosa succede se due servizi richiedono versioni diverse della stessa libreria?

**Test**

- Dove vivono i test unitari e i tuoi test di integrazione? Vicino al codice del servizio o in una cartella centrale?
- Come avviano i tuoi test di integrazione i servizi reali, e come li spengono?
- Quale singolo comando esegue tutti i test di un servizio? E quale quelli dell'intera piattaforma?

**Spec e tracciabilitÃ **

- Una spec Kiro per servizio, per funzionalitÃ  o per regola di business? Come si riflette questa scelta nelle cartelle?
- Partendo da un requisito `REQ-REG-B05`, quanto tempo serve a un collega per trovare il codice che lo implementa e il test che lo verifica?
- Cosa va in `structure.md` e cosa in `design.md`? Qual Ã¨ la differenza tra una regola valida per tutto il repository e una decisione specifica di un servizio?

**Dati e Git**

- Dove finiscono i file di dati di `json`/`sqlite`? Sono esclusi da git?
- Come organizzi i commit per rendere leggibile la sequenza spec â†’ task â†’ codice?

> Queste risposte sono valutate insieme alla spec: una struttura coerente, motivata e rispettata da tutti i servizi conta quanto una struttura "elegante".

---

## 8. Criteri di valutazione (100 punti + bonus)

**PenalitÃ **

- Modifica di `contracts/` o `tests/integration/`: **âˆ’20**
- Codice applicativo committato prima di `tasks.md`: **âˆ’15** per servizio
- Bug di specifica corretto in Vibe senza aggiornare la spec: **âˆ’5** per bug
- URL di altri servizi scritti nel codice invece che in variabili d'ambiente: **âˆ’5**
- Uso di un DBMS esterno: **âˆ’5**

---

## 9. Checklist di consegna

- [X] `.kiro/steering/` (4 file, con `structure.md` che risponde alle domande del Â§7) e almeno 1 hook
- [X] `.kiro/specs/<svc>/` con requirements, design e tasks (tutti spuntati) per i 3 servizi obbligatori
- [X] `services.yaml` compilato; servizi avviabili, backend `memory` / `json` / `sqlite` funzionanti
- [X] Unit test con coverage â‰¥ 80% per ogni servizio
- [X] Integration test propri per event-service e registration-service
- [X] `pytest tests/integration -m mandatory` eseguito, output salvato in `collaudo.txt`
- [ ] `BUGS.md` con almeno 2 bug chiusi — bug documentati e corretti (test di regressione verdi), ma issue GitHub non ancora pubblicate: chiusura formale in sospeso
- [X] `README.md` (avvio, variabili d'ambiente, comandi di test)
- [X] File in `contracts/` e `tests/integration/` **non modificati**
- [X] Tag `v1.0.0` sul `main`
