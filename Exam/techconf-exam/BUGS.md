# BUGS.md — Bug reali documentati e chiusi

Workflow di riferimento: **§6.4 / §6.5** (gestione bug). Questo file registra
**solo difetti realmente riscontrati** durante l'investigazione del task T-18
(nessun bug inventato). Per ciascun bug: servizio, come è stato trovato,
tipo (implementazione/spec), requisito violato, atteso vs ottenuto, causa radice,
test di regressione e commit di fix.

> **Nota su issue e commit.** In questo ambiente la CLI `gh` **non è disponibile**,
> quindi le issue GitHub reali vanno aperte manualmente dal browser (OPEN-REG-02).
> I numeri di issue qui sotto sono **segnaposto** (`<ISSUE #TBD by user>`): l'utente
> apre l'issue e sostituisce il numero, poi il commit di fix va creato con il
> messaggio indicato — che include `(closes #N)` con lo stesso numero. I test di
> regressione sono già scritti e verdi; i fix sono già applicati sul working tree.

---

## Riepilogo

| ID | Servizio | Tipo | Requisito | Stato |
|----|----------|------|-----------|-------|
| BUG-001 | registration-service | **implementazione** | REQ-REG-F13-AC4, REQ-REG-F10-AC5 | Fix applicato, test di regressione verde |
| BUG-002 | event-service | **implementazione** | REQ-EVT-F03-AC5 | Fix applicato, test di regressione verde |

Consegna §6.5: **2 bug reali**, entrambi di **implementazione** (requisito: ≥2 bug,
≥1 impl → soddisfatto).

---

## BUG-001 — Il backend `memory` restituisce riferimenti interni (nessun isolamento)

- **Servizio:** registration-service (difetto di classe presente anche in
  event-service e user-service — vedi *Note*).
- **Tipo:** implementazione.
- **Issue GitHub:** `<ISSUE #TBD by user>` — aprire dal browser
  (titolo suggerito: *"MemoryRegistrationRepository returns internal references
  instead of isolated copies"*).
- **Trovato da:** investigazione T-18 (test esplorativi sui tre backend); i backend
  `json` e `sqlite` restituiscono copie isolate (`copy.deepcopy` / righe SQLite
  ricostruite), il backend `memory` restituiva l'oggetto interno.
- **Requisito violato:** REQ-REG-F13-AC4 (la logica di business e il layer HTTP
  devono essere **identici** sui tre backend) e REQ-REG-F10-AC5 (i campi memorizzati
  sono read-only dal punto di vista del chiamante; l'immutabilità va preservata).
- **Atteso:** mutando un record restituito da `get`, `list_all`, `create_if_allowed`
  o `set_status`, lo stato memorizzato **non** deve cambiare (come per json/sqlite).
- **Ottenuto (prima del fix):** i metodi del backend `memory` restituivano il
  medesimo `dict` conservato nel dizionario interno; una mutazione esterna del record
  restituito **corrompeva silenziosamente** lo store (es. `status` → `"HACKED"`,
  `amount` → `-999`), con comportamento **divergente** dagli altri due backend.
- **Causa radice:** in `app/backends/memory.py` i metodi restituivano il riferimento
  diretto (`return record` / `results.append(record)` / `self._data.get(...)`) senza
  copiare, a differenza di `JsonRegistrationRepository` che usa `copy.deepcopy`.
- **Fix:** allineare il backend `memory` a json/sqlite restituendo copie isolate
  (`copy.deepcopy`) da `create_if_allowed`, `get`, `list_all` e `set_status`.
  File: `services/registration-service/app/backends/memory.py`.
- **Test di regressione** (falliscono prima del fix, verdi dopo):
  `services/registration-service/tests/unit/test_regression_bugs.py`
  - `test_memory_get_returns_isolated_copy`
  - `test_memory_create_returns_isolated_copy`
  - `test_memory_list_all_returns_isolated_copies`
  - `test_memory_set_status_returns_isolated_copy`
- **Commit di fix (da creare con il numero issue reale):**
  `fix(registration): isolate memory backend records via deepcopy (closes #N)`
- **Note:** lo stesso pattern (backend `memory` che restituisce riferimenti mentre
  `json`/`sqlite` copiano) è presente anche in `event-service` e `user-service`.
  Nel percorso HTTP attuale la serializzazione avviene sempre tramite
  `*_to_dict`, quindi la corruzione non è direttamente sfruttabile via API, ma la
  **violazione del contratto del repository** e la **divergenza tra backend** sono
  reali e verificate. Il fix qui riguarda registration-service (oggetto della spec
  T-18); l'estensione a event/user può essere tracciata in issue separate.

---

## BUG-002 — `validate_date` accetta date in formato settimana ISO (`YYYY-Www-D`)

- **Servizio:** event-service.
- **Tipo:** implementazione.
- **Issue GitHub:** `<ISSUE #TBD by user>` — aprire dal browser
  (titolo suggerito: *"validate_date accepts ISO week dates like 2026-W40-1"*).
- **Trovato da:** investigazione T-18 (test esplorativi sulla validazione delle date).
- **Requisito violato:** REQ-EVT-F03-AC5 (solo stringhe ben formate `YYYY-MM-DD` sono
  date valide). Il contratto dichiara `start_date`/`end_date` come OpenAPI
  `format: date` (RFC 3339 full-date = `YYYY-MM-DD`).
- **Atteso:** `validate_date("2026-W40-1")` → `False`; un `POST /api/v1/events` con
  `start_date: "2026-W40-1"` → **422 VALIDATION_ERROR**.
- **Ottenuto (prima del fix):** `validate_date("2026-W40-1")` → `True` e la POST
  passava la validazione, perché `datetime.date.fromisoformat` (Python 3.11+) parsa
  anche le **date in formato settimana ISO**, che sono lunghe esattamente 10
  caratteri; la guardia `len(value) == 10` non era quindi sufficiente a scartarle
  (contraddicendo anche il commento del codice, che affermava "accepts exactly
  YYYY-MM-DD").
- **Causa radice:** in `app/validators.py`, `validate_date` verificava solo che
  `date.fromisoformat` non sollevasse eccezioni e che `len == 10`, senza garantire
  la forma canonica `YYYY-MM-DD`.
- **Fix:** dopo il parsing, richiedere il **round-trip canonico**
  `parsed.isoformat() == value`, così solo una stringa `YYYY-MM-DD` (che re-formatta
  in sé stessa) è accettata; le forme settimana/ordinali vengono rifiutate.
  File: `services/event-service/app/validators.py`.
- **Test di regressione** (falliscono prima del fix, verdi dopo):
  `services/event-service/tests/unit/test_regression_bugs.py`
  - `test_validate_date_rejects_iso_week_dates` (parametrizzato: `2026-W40-1`, `2026-W01-7`)
  - `test_validate_event_create_rejects_iso_week_date`
- **Commit di fix (da creare con il numero issue reale):**
  `fix(event): reject ISO week dates in validate_date, require YYYY-MM-DD (closes #N)`

---

## Verifiche eseguite

- **Test di regressione**: entrambe le batterie falliscono sul codice non corretto e
  passano dopo il fix (verificato).
- **Suite unit dei servizi toccati** (nessuna regressione):
  - event-service: `py -3.12 -m pytest tests/unit --cov=app --cov-fail-under=80`
    → 222 passed, coverage 97%.
  - registration-service: `py -3.12 -m pytest tests/unit --cov=app --cov-fail-under=80`
    → 208 passed, coverage 97%.
- **Collaudo obbligatorio** (deve restare verde): dalla root `Exam/techconf-exam/`
  `py -3.12 -m pytest tests/integration -m mandatory` → **27 passed** (invariato dopo i fix).

## Azioni residue per l'utente (gh non disponibile)

1. Aprire dal browser le due issue GitHub reali (una per BUG-001, una per BUG-002).
2. Sostituire `<ISSUE #TBD by user>` con i numeri reali qui sopra.
3. Creare i commit di fix con i messaggi indicati, includendo `(closes #N)` con il
   numero di issue corrispondente; poi merge su `main`.
