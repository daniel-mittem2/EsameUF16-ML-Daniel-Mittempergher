# TechConf — Struttura del codice e decisioni architetturali

Questo file risponde alle domande guida del §7 di `Exam.MD` e vincola tutte le
generazioni di codice successive. Ogni scelta è motivata. In caso di conflitto con
`design.md` di un singolo servizio, prevale questo file (regola globale).

---

## §7.1 — Repository e confini dei servizi

**Scelta: un unico repository monorepo, un package per servizio.**

```
Exam/techconf-exam/
  services/
    user-service/         ← confine netto di ogni servizio
      app/                ← package Python principale
      tests/              ← test unitari e di integrazione propri
      requirements.txt
    event-service/
      app/
      tests/
      requirements.txt
    registration-service/
      app/
      tests/
      requirements.txt
    feedback-service/       (opzionale)
      ...
    notification-service/   (opzionale)
      ...
  contracts/openapi/      ← non modificabili
  tests/integration/      ← suite del docente, non modificabili
  services.yaml           ← manifest per la suite (committato)
  services.example.yaml
  CHECKSUMS.sha256
```

**Motivazioni:**

- La suite di collaudo del docente risiede nello stesso repo e deve poter trovare i
  servizi con path relativi: un monorepo evita submodule o symlink.
- L'aggiunta dei servizi opzionali (feedback, notification) richiede solo una nuova
  cartella sotto `services/`; nessuna modifica alle cartelle esistenti.
- Guardando le cartelle si vede immediatamente dove finisce un servizio e dove inizia
  l'altro: ogni `services/<nome>/` è un'unità autonoma con il proprio `requirements.txt`
  e il proprio ambiente virtuale.
- Il versionamento rimane lineare e leggibile: ogni commit di spec o task porta il
  prefisso `spec(<svc>):` o `feat(<svc>):`.

**Un servizio NON può importare codice di un altro servizio.**
Questa regola si applica sia in runtime che in test: nessun `from services.user_service`
o path hack. La comunicazione avviene esclusivamente via HTTP. I modelli Python
(dataclass/dict) non sono condivisi. Se si constata un'importazione cross-service
durante la review, è un difetto da correggere prima del merge.

---

## §7.2 — Codice condiviso e duplicazione

**Scelta: duplicazione controllata, nessuna libreria condivisa.**

Le funzioni di utilità (formattazione errori, paginazione, client HTTP) sono
**duplicate** in ogni servizio, non estratte in un package condiviso.

**Motivazioni:**

- Un package condiviso introduce un accoppiamento strutturale: se cambia la firma
  di un'utility, tutti i servizi devono essere aggiornati insieme. Questo contraddice
  il principio di deployabilità indipendente dei microservizi.
- Il codice "duplicato" è effettivamente piccolo (< 50 righe per utility): il costo
  di duplicazione è inferiore al costo di gestire una dipendenza condivisa.
- Se un giorno un servizio viene affidato a un altro team, porta tutto con sé senza
  dipendenze esterne al proprio package.
- La duplicazione è **esplicita e locale**: ogni servizio ha `app/errors.py`,
  `app/pagination.py`, `app/http_client.py`. Cambiare uno non tocca gli altri.

Il pattern da duplicare è sempre lo stesso: le convenzioni sono fissate in
`platform-standards.md` e questo file.

---

## §7.3 — Struttura interna di ogni servizio

Ogni servizio segue questa struttura a quattro livelli:

```
app/
  __init__.py         ← crea l'app Flask (factory function)
  __main__.py         ← entry point: legge PORT da env, avvia Flask
  config.py           ← legge TUTTE le variabili d'ambiente, una sola volta
  routes.py           ← livello HTTP: parsing request, validazione input, serializzazione response
  service.py          ← livello business: regole REQ-*-B*, orchestrazione
  repository.py       ← interfaccia astratta di persistenza (ABC)
  backends/
    memory.py         ← implementazione in-memory
    json_backend.py   ← implementazione JSON su file
    sqlite_backend.py ← implementazione SQLite
  http_client.py      ← chiamate HTTP verso altri servizi (wrappa requests)
  errors.py           ← costanti dei codici errore e helper per costruire le response
  pagination.py       ← helper per paginazione
  models.py           ← dataclass o dict factory per le risorse
```

**Responsabilità dei livelli:**

| Livello | File | Responsabilità |
|---|---|---|
| HTTP | `routes.py` | Parsing JSON, validazione formato, status code, header Location, serializzazione |
| Business | `service.py` | Regole REQ-*-B*, chiamate a `http_client.py`, costruzione degli oggetti dominio |
| Repository | `repository.py` + `backends/` | CRUD sullo storage; nessuna logica di business |
| Client | `http_client.py` | Chiamate HTTP verso altri servizi; gestisce timeout, 404→422, 5xx→503 |

**Le regole `REQ-*-B*` vivono in `service.py`**, mai in `routes.py` o `repository.py`.
Questo facilita la tracciabilità: cercando `REQ-EVT-B02` si trova subito il punto
esatto nel service layer.

**Intercambiabilità dei backend:**

`repository.py` definisce un'interfaccia astratta (`abc.ABC`) con metodi come
`get(id)`, `list(filters)`, `create(data)`, `update(id, data)`, `delete(id)`.
I tre backend (`memory`, `json`, `sqlite`) implementano la stessa interfaccia.
`config.py` istanzia il backend corretto in base a `STORAGE_BACKEND`.
`service.py` riceve il repository per dependency injection (passato al costruttore
o alla factory); non importa mai direttamente i backend.

In questo modo cambiare backend non tocca né `service.py` né `routes.py`.

**Isolamento delle chiamate esterne:**

`http_client.py` wrappa `requests.get/post/put/patch/delete` con timeout di 2 s.
Traduce le risposte in eccezioni interne (`ReferenceNotFoundError`,
`DependencyUnavailableError`). Nei test unitari si usa `responses` per mockare
`requests` a livello di libreria: `http_client.py` viene chiamato normalmente,
ma le richieste HTTP non escono mai dalla rete.

---

## §7.4 — Configurazione e avvio

- **Tutte** le variabili d'ambiente sono lette in `app/config.py`, in un solo posto,
  all'avvio. Nessuna chiamata a `os.environ` in altri moduli.
- Default: `PORT` non ha default (errore esplicito se mancante).
  `STORAGE_BACKEND=memory`, `DATA_DIR=./data`. Gli URL dei servizi hanno default
  `http://localhost:<porta_dev>`.
- Il comando di avvio è `python -m app` per tutti i servizi. `__main__.py` **non legge
  direttamente** `os.environ`: importa `app.config` e legge `config.PORT`. In questo
  modo tutta la logica di lettura delle variabili d'ambiente rimane in un unico posto.
- **Dipendenze Python**: un file `requirements.txt` per servizio (non un unico
  ambiente condiviso). La suite lancia ogni servizio nel suo `cwd`, quindi può
  usare ambienti separati. In sviluppo è accettabile un unico venv che installi
  tutte le dipendenze (sono le stesse: flask, requests, pytest, pytest-cov,
  responses).

---

## §7.5 — Test

**Posizione:** `services/<nome>-service/tests/` — vicino al codice del servizio.

```
tests/
  unit/
    test_routes.py          ← test HTTP (Flask test client)
    test_service.py         ← test business logic (repository mockato)
    test_repository.py      ← test dei tre backend (memory/json/sqlite con tmp_path)
    test_contracts.py       ← test di contratto (assert_matches_contract per ogni endpoint)
  integration/
    test_<svc>_integration.py  ← avvia i servizi reali su porte libere
```

**Comando singolo per un servizio:**

```bash
# dalla directory del servizio
py -3.12 -m pytest tests/unit -v --cov=app --cov-report=term-missing
```

**Comando per tutti i test unitari della piattaforma:**

```bash
# dalla root del repo — ogni servizio gira in un processo separato per evitare
# collisioni tra i package `app/` omonimi e wildcard non portabili su Windows.
for svc in user-service event-service registration-service; do
    py -3.12 -m pytest Exam/techconf-exam/services/$svc/tests/unit -v \
        --cov=app --rootdir=Exam/techconf-exam/services/$svc
done
```

Su **Windows PowerShell** equivalente:

```powershell
foreach ($svc in @("user-service","event-service","registration-service")) {
    py -3.12 -m pytest "Exam/techconf-exam/services/$svc/tests/unit" -v `
        --cov=app "--rootdir=Exam/techconf-exam/services/$svc"
}
```

Oppure usare lo script di utilità `scripts/run_all_unit_tests.ps1` (creato al
primo task di ogni servizio). Ogni servizio **deve** essere testato nel suo `cwd`
(`--rootdir` o `cwd` del subprocess) in modo che l'import `from app import ...`
risolva il package locale e non un altro servizio nel path.

**Test di integrazione propri:**

La fixture pytest avvia il servizio (e le sue dipendenze) in sottoprocesso su una
porta libera (`port=0` o range 19001+), aspetta `/health`, esegue i test, poi
termina i processi. Questo garantisce test reali senza mock HTTP.

**Tracciabilità requisiti:**

Ogni test usa `@pytest.mark.req("REQ-USR-B01")` oppure include l'ID nel nome della
funzione (`test_req_usr_b01_email_unique`). Partendo da `REQ-REG-B05`:
1. `grep -r REQ-REG-B05 services/registration-service/` → trova `service.py` (codice)
   e `tests/unit/test_service.py` (test).
2. Tempo stimato: < 30 secondi.

---

## §7.6 — Spec e tracciabilità

**Una spec Kiro per servizio**, in `.kiro/specs/<svc>/`:

```
.kiro/specs/
  user-service/
    requirements.md
    design.md
    tasks.md
  event-service/
    ...
  registration-service/
    ...
```

`structure.md` (questo file) contiene decisioni valide per **tutto il repository**.
`design.md` di ogni servizio contiene decisioni **specifiche di quel servizio**
(schema delle tabelle SQLite, dettaglio delle rotte Flask, strategia di mock nei test).

---

## §7.7 — Dati e Git

- `data/` è in `.gitignore` (già presente nel template).
- I file SQLite (`*.sqlite`, `*.sqlite3`) sono in `.gitignore`.
- `.it-logs/` (log della suite) è in `.gitignore`.
- `services.yaml` **è committato** (non è in `.gitignore`).

**Sequenza leggibile dei commit:**

```
chore(setup): steering files, hook, CRLF fix
spec(user): requirements
spec(user): design
spec(user): tasks
feat(user): T-01 — scaffold app package  [T-01]
feat(user): T-02 — config e health endpoint  [T-02]
...
spec(event): requirements
...
```

Ogni commit di task porta l'ID del task tra parentesi quadre per rintracciabilità.
