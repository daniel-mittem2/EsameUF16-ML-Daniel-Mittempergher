# TechConf — Platform Standards

> Trascrizione vincolante del §4 di `Exam.MD`. Valida per tutti i servizi senza eccezioni.

## Avvio dei servizi

Un file `services.yaml` nella root di `Exam/techconf-exam/` dichiara, per ogni servizio
implementato, la cartella di lavoro (`cwd`) e il comando di avvio (`command`).
La suite di collaudo lo legge e passa a ogni servizio le variabili `PORT` e
`*_SERVICE_URL`. Ogni servizio **deve** ascoltare sulla porta indicata da `PORT`.

## Base path

`/api/v1/<risorsa>`

## Formato

- Corpo JSON in tutte le request e response.
- Campi in `snake_case`.
- Content-Type `application/json`.

## Identificativi

- `id` UUID v4 generato dal server.
- L'`id` **non è mai accettato in input** (ignorato se presente, o 422 se indesiderato).

## Timestamp

- ISO 8601 UTC: `2026-10-15T09:30:00Z`.
- Ogni risorsa ha `created_at` e `updated_at` (aggiornato ad ogni modifica).

## Date e importi

- Date: `YYYY-MM-DD`.
- Importi numerici con 2 decimali (`149.00`), valuta implicita EUR.

## Paginazione

Request: `?page=1&page_size=20` (page_size max 100).

Response:
```json
{"items": [...], "page": 1, "page_size": 20, "total": 57}
```

## Errori

Formato sempre:
```json
{"error": {"code": "UPPER_SNAKE", "message": "...", "details": {}}}
```
`details` può essere omesso o `null` se non necessario.

## Status code

| Caso | Codice |
|---|---|
| Creazione riuscita | 201 (+ header `Location: /api/v1/<risorsa>/<id>`) |
| Lettura / modifica riuscita | 200 |
| Cancellazione riuscita | 204 (nessun body) |
| JSON malformato | 400 |
| Risorsa non trovata | 404 `NOT_FOUND` |
| Metodo HTTP non previsto | 405 |
| Conflitto | 409 (es. `EMAIL_ALREADY_EXISTS`, `ALREADY_REGISTERED`) |
| Errore di validazione / riferimento mancante / regola di business | 422 (`VALIDATION_ERROR`, `REFERENCE_NOT_FOUND`, ecc.) |
| Dipendenza non raggiungibile | 503 `DEPENDENCY_UNAVAILABLE` |

## Chiamate tra servizi

- URL letti **esclusivamente** da variabili d'ambiente (`USER_SERVICE_URL`,
  `EVENT_SERVICE_URL`, `REGISTRATION_SERVICE_URL`, `FEEDBACK_SERVICE_URL`,
  `NOTIFICATION_SERVICE_URL`).
- Default: `http://localhost:<porta_dev>` (5001–5005).
- Timeout: **2 secondi**.
- Se il servizio chiamato risponde 404 → 422 `REFERENCE_NOT_FOUND`.
- Se il servizio chiamato va in timeout, rifiuta la connessione o risponde 5xx → 503 `DEPENDENCY_UNAVAILABLE`.

## Health check

```
GET /health → 200 {"status": "ok", "service": "<nome-servizio>"}
```

Deve rispondere sempre, indipendentemente dallo stato delle dipendenze.

## Persistenza

| Variabile | Valori | Note |
|---|---|---|
| `STORAGE_BACKEND` | `memory` (default) · `json` · `sqlite` | Seleziona il backend |
| `DATA_DIR` | `./data` (default) | Directory per file json/sqlite |

- Solo librerie standard: `json`, `sqlite3`. Nessun ORM, nessun DBMS da installare.
- Il cambio di backend **non richiede modifiche alla logica di business**.
- `data/` è esclusa da git.

## Dipendenze Python (per ogni servizio)

```
# requirements.txt
flask
requests

# requirements-dev.txt (o sezione separata)
pytest
pytest-cov
responses
```
