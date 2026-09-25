# Issue draft — da pubblicare su GitHub

> **Repository:** https://github.com/daniel-mittem2/EsameUF16-ML-Daniel-Mittempergher
> **Stato:** da pubblicare manualmente (gh CLI non disponibile)
> **Pubblicazione issue:** IN SOSPESO (vedi nota in fondo)

---

## Issue #1 — spec(user): validation and design defects

**Tipo:** bug di specifica
**Servizio:** user-service
**File coinvolti:** `.kiro/specs/user-service/requirements.md`,
  `.kiro/specs/user-service/design.md`

### Difetti di specifica in requirements.md (corretti in commit 61b1977)

| # | Requisito | Comportamento atteso | Comportamento riscontrato nella spec |
|---|---|---|---|
| 1 | REQ-USR-F12 | `details` sempre presente come `{}` | Dichiarato nullable/omissible |
| 2 | REQ-USR-F03/F04 | Body deve essere JSON object | Nessuna regola esplicita sul tipo del body |
| 3 | REQ-USR-F03/F04 | Tipi dei campi verificati, no conversioni implicite | Nessuna specifica su type coercion |
| 4 | REQ-USR-F06 | 422 per page/page_size vuoti, non numerici, non interi | Mancava questa casistica |
| 5 | REQ-USR-F04/F11 | PATCH `{}`: risorsa e timestamp invariati (scelta unica) | Contraddizione "MAY be refreshed" vs "NON viene aggiornato" |
| 6 | Glossario PUT | Sostituisce campi mutable mantenendo id e created_at | "equivale a cancellare e ricreare" — semanticamente errato |
| 7 | REQ-USR-F07-AC4 | Riferimento a REQ-USR-F03-AC9/AC10 (campi extra) | Riferimento errato a F03-AC4 (riguardava company) |
| 8 | REQ-USR-F10 | Path sconosciuto → 404; metodo non consentito → 405; corpo errore obbligatorio | Non distingueva 404 vs 405; corpo errore era SHOULD |
| 9 | REQ-USR-F12 | DELETE 204 non ha corpo JSON (eccezione esplicita) | Mancava l'eccezione |
| 10 | REQ-USR-T01-AC5 | `responses` non necessario (nessun HTTP dep) | Affermazione errata che serve per Flask test client |
| 10b | REQ-USR-F03-AC3 | Validazione email allineata a `format: email` del contratto | Promessa validazione RFC 5322 completa senza strategia |

### Difetti di design in design.md (corretti in commit — da assegnare)

| # | Sezione | Comportamento atteso | Problema riscontrato |
|---|---|---|---|
| D1 | §11 FlaskResponseAdapter | Usare dict `{status_code, headers, json}` supportato nativamente dal validator | Il wrapper non esponeva `.text`; il validator avrebbe letto il body come None |
| D2 | §10 Concorrenza | Flask usa thread per default; lock condiviso per istanza di repo necessario | Dichiarava memory/json "sicuri" perché "single-threaded" — errato |
| D3 | §3 config.py | `PORT` validata solo all'avvio del server; import del package non richiede PORT | Leggeva PORT all'import — bloccava i test unitari senza variabili d'ambiente |
| D4 | §14 services.yaml | Schema completo `services: > user: > cwd/command`, ambiente preparato, solo user dichiarato | Schema incompleto, nessuna guida preparazione ambiente, servizi multipli presenti |
| D5 | §8 Timestamp | Precisione microsecondaria; test con orologio controllabile via monkeypatch | Solo secondi (`%S`); nessuna strategia per test ravvicinati |
| D6 | §6 PATCH | Cerca risorsa per prima cosa anche per `{}`; rifiuta campi sconosciuti esplicitamente | Cercava risorsa solo dopo validazione; `additionalProperties:false` non si applica automaticamente |
| D7 | §13 Test integrazione | `try/finally` con `proc.kill()` come fallback, anche se health fallisce | Cleanup non garantito in caso di errore durante wait_for_health |
| D8 | §9 SQLite gitignore | L'esclusione è garantita dalla directory `data/` (già in .gitignore) | Nota errata su `*.sqlite` che coprirebbe solo la root |

### Stato delle correzioni

- requirements.md: **corretti** — commit `61b1977`
- design.md: **corretti** — commit da assegnare (spec(user): correct design before tasks)

### Punti ancora aperti (non dimostrati)

1. **Issue GitHub:** questa issue NON è ancora pubblicata. `gh` CLI non disponibile;
   pubblicazione da fare manualmente su GitHub dal browser.
2. **Hook Kiro:** il file `unit-tests-on-save.json` è valido e lo script passa
   6 controlli automatici. La visibilità e abilitazione nel pannello Agent Hooks
   dell'IDE **non è stata verificata** — richede conferma manuale nell'IDE.
3. **Hook eseguito su salvataggio reale:** non verificato (nessun file di servizio
   esiste ancora); verificabile al primo task di implementazione.
