# TechConf — Tech Stack

## Runtime

| Componente | Versione / Note |
|---|---|
| Python | **3.12** (`py -3.12` su Windows, `python3.12` su Linux/macOS) |
| Flask | ultima stabile — framework HTTP, nessuna estensione aggiuntiva |
| requests | ultima stabile — chiamate HTTP tra servizi |
| uuid | stdlib — generazione UUID v4 |
| json | stdlib — backend JSON per la persistenza |
| sqlite3 | stdlib — backend SQLite per la persistenza |
| datetime / zoneinfo | stdlib — timestamp ISO 8601 UTC |

## Dipendenze di test

| Pacchetto | Uso |
|---|---|
| pytest | runner di test |
| pytest-cov | coverage report (`pytest --cov=app`) |
| responses | mock delle chiamate HTTP verso altri servizi nei test unitari |

Dipendenze dichiarate in `requirements.txt` per ogni servizio.
Nessun DBMS esterno: tutto con librerie standard Python.

## Comandi di avvio

Ogni servizio si avvia con:

```bash
py -3.12 -m app          # Windows (sviluppo)
python -m app            # in services.yaml (la suite inietta il PATH corretto)
```

Il modulo `app` è il package principale del servizio (contiene `__main__.py`).

## Variabili d'ambiente obbligatorie

| Variabile | Default | Uso |
|---|---|---|
| `PORT` | — | Porta di ascolto (obbligatoria, iniettata dalla suite) |
| `USER_SERVICE_URL` | `http://localhost:5001` | URL di user-service |
| `EVENT_SERVICE_URL` | `http://localhost:5002` | URL di event-service |
| `REGISTRATION_SERVICE_URL` | `http://localhost:5003` | URL di registration-service |
| `FEEDBACK_SERVICE_URL` | `http://localhost:5004` | URL di feedback-service |
| `NOTIFICATION_SERVICE_URL` | `http://localhost:5005` | URL di notification-service |
| `STORAGE_BACKEND` | `memory` | Backend di persistenza: `memory`, `json`, `sqlite` |
| `DATA_DIR` | `./data` | Directory per file json/sqlite (esclusa da git) |

Tutte le variabili sono lette **in un solo punto** (modulo `app/config.py`) e mai
hard-codate nel codice.

## Regole di codice

- Nessun DBMS esterno; solo librerie standard per la persistenza.
- Nessun import applicativo tra servizi (ogni servizio è autonomo).
- Flask development server (`app.run`) solo per sviluppo; in produzione usare
  `waitress` o simile (fuori scope dell'esame, ma il codice deve funzionare con
  `flask run` o `python -m app`).
- Type hints dove aumentano la leggibilità (non obbligatori ovunque).
- `snake_case` per tutti i campi JSON e i nomi Python.

## Testing

```bash
# Test unitari di un singolo servizio (dalla directory del servizio)
py -3.12 -m pytest tests/ -v --cov=app --cov-report=term-missing

# Tutti i test unitari della piattaforma
# (script top-level, vedi structure.md)

# Suite di collaudo del docente
py -3.12 -m pytest Exam/techconf-exam/tests/integration -m mandatory -v
```

Coverage minima: **80%** per servizio (`--cov=app`).
