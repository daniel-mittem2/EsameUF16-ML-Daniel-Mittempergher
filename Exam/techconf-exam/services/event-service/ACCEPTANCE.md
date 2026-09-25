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
