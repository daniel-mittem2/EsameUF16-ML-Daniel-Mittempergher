# event-service — Note di collaudo (T-16)

Collaudo con la suite del docente filtrata su `event` e verifica dell'integrità
dei file protetti.

## Comando eseguito

Dalla root `Exam/techconf-exam/`:

```powershell
py -3.12 -m pytest tests/integration -k event -v
```

## Esito (IT-E01..IT-E08 — tutti verdi)

| Test | Nome | Requisiti | Esito |
|---|---|---|---|
| IT-E01 | `test_it_e01_create_with_valid_organizer` | REQ-EVT-F02, B01, B02 | PASSED |
| IT-E02 | `test_it_e02_organizer_not_found` | REQ-EVT-B01 (`REFERENCE_NOT_FOUND`, 422) | PASSED |
| IT-E03 | `test_it_e03_organizer_wrong_role` | REQ-EVT-B02 (`INVALID_ORGANIZER`, 422) | PASSED |
| IT-E04 | `test_it_e04_end_before_start` | REQ-EVT-B03 (`VALIDATION_ERROR`, 422) | PASSED |
| IT-E05 | `test_it_e05_status_transitions` | REQ-EVT-B04 (`draft→published` 200; `published→draft` 422) | PASSED |
| IT-E06 | `test_it_e06_filters_and_pagination` | REQ-EVT-F06, B06 | PASSED |
| IT-E07 | `test_it_e07_crud_and_404` | REQ-EVT-F05, F07, F08, F09, F11 | PASSED |
| IT-E08 | `test_it_e08_user_service_unreachable` | REQ-EVT-B05 (`DEPENDENCY_UNAVAILABLE`, 503) | PASSED |

Risultato pytest: **8 passed, 4 skipped, 25 deselected**.

I 4 test `test_registration.py` intercettati dal filtro `-k event` risultano
`SKIPPED` perché il servizio `registration` non è dichiarato in `services.yaml`
(comportamento atteso: i servizi non dichiarati sono saltati, non falliti).
`user` ed `event` sono entrambi dichiarati in `services.yaml`.

## Verifica checksum (file protetti invariati)

`Get-FileHash -Algorithm SHA256` confrontato con `CHECKSUMS.sha256` **prima e dopo**
l'esecuzione della suite: tutte le fingerprint corrispondono. Nessun file protetto
è stato modificato:

- `contracts/openapi/*.yaml` (5 contratti) — OK
- `contracts/validator.py` — OK
- `tests/integration/conftest.py`, `harness.py`, `pytest.ini`, `requirements.txt` — OK
- `tests/integration/test_*.py` (7 file) — OK
- `CHECKSUMS.sha256` — invariato

## Conclusione

IT-E01..IT-E08 verdi; checksum invariati. Nessun bug rilevato: non è stato necessario
aprire alcuna issue né applicare il workflow §6.4/§6.5 di `Exam.MD`.

---

# event-service — Verifica finale di coerenza (T-18)

Rilettura completa prima di iniziare `registration-service`. Tutte le verifiche
rieseguite da zero, con pulizia dei processi orfani sulle porte di collaudo.

## 1. Unit test + coverage (dalla dir del servizio)

```powershell
py -3.12 -m pytest tests/unit -v --cov=app --cov-report=term-missing --cov-fail-under=80
```

Esito: **219 passed**. Coverage totale **97.01%** (gate `--cov-fail-under=80`
superato). `app/__main__.py` escluso dalla copertura effettiva via
`# pragma: no cover` sull'entrypoint. _Requisito: REQ-EVT-T01._

## 2. Test di integrazione propri (dalla dir del servizio)

```powershell
py -3.12 -m pytest tests/integration -v
```

Esito: **3 passed** — caso positivo (201 `draft`), riferimento inesistente
(422 `REFERENCE_NOT_FOUND`), dipendenza spenta (503 `DEPENDENCY_UNAVAILABLE`),
con user-service ed event-service reali come sottoprocessi. _Requisito: REQ-EVT-T02._

## 3. Collaudo docente `-k event` (dalla root `Exam/techconf-exam/`)

```powershell
py -3.12 -m pytest tests/integration -k event -q
```

Esito: **8 passed, 4 skipped, 25 deselected**. IT-E01..IT-E08 verdi con `user` ed
`event` dichiarati in `services.yaml`; i 4 `test_registration.py` intercettati dal
filtro restano `SKIPPED` (servizio `registration` non ancora dichiarato — atteso).

> Nota operativa: una prima esecuzione è fallita con `RuntimeError: Acceptance port
> 15001/15002/15102 ... already in use` a causa di processi `py -3.12 -m app`
> orfani rimasti da una sessione precedente (non un difetto del servizio). Dopo
> `Stop-Process` di quei PID e liberazione delle porte, la suite è tornata verde.

## 4. Configurazione centralizzata e nessun import cross-service (REQ-EVT-F13)

- **Env vars:** `PORT`, `STORAGE_BACKEND`, `DATA_DIR`, `USER_SERVICE_URL` sono lette
  in `app/config.py::load_config`. L'URL di default `http://localhost:5001` è quello
  imposto dal contratto (REQ-EVT-F13-AC2) e non è un endpoint hard-coded arbitrario.
- **Nessun import applicativo da user-service:** l'unica comunicazione è HTTP via
  `app/http_client.py` (`import requests`). Nessun `from user_service` / `import
  user_service` / import relativo verso `services/user-service`. I riscontri testuali
  "user-service" nel sorgente sono solo docstring/commenti.
- **Osservazione (fallback in `create_app`):** `app/__init__.py` legge `os.environ`
  (`STORAGE_BACKEND`, `DATA_DIR`, `USER_SERVICE_URL`) e definisce
  `_DEFAULT_USER_SERVICE_URL = "http://localhost:5001"` come *fallback* per il percorso
  di dependency-injection dei test (quando `create_app` è invocata senza `config`).
  Questo è esattamente il comportamento prescritto da `design.md §3` e accettato in
  T-03/T-08. In produzione `__main__.py` passa sempre `config=load_config()`, quindi
  quei rami non vengono percorsi. È una lettura d'ambiente al di fuori di `config.py`
  in senso stretto: annotata qui per trasparenza; non modificata in T-18 perché è
  codice di un task già accettato e coperto dai test, e la modifica esulerebbe dallo
  scope di questa verifica.

## Verifica file protetti

`git status` pulito lato codice; `CHECKSUMS.sha256` verificato: tutte le fingerprint
corrispondono (`contracts/`, `tests/integration/`, `CHECKSUMS.sha256` invariati).

## Conclusione

Tutte le verifiche verdi (unit+coverage, integrazione propria, collaudo `-k event`),
configurazione centralizzata, nessun import applicativo da user-service, file protetti
invariati. **event-service pronto: si può iniziare `registration-service`.**
