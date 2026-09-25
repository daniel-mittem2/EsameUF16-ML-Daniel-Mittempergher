# TechConf — Product Context

## Dominio

TechConf è una piattaforma a microservizi per la gestione delle iscrizioni a conferenze
tecnologiche (cloud, AI, security). La società organizza eventi con capienza limitata e
ha bisogno di tenere traccia di utenti, eventi e iscrizioni, con la possibilità futura
di raccogliere feedback e inviare notifiche.

## Servizi e responsabilità

| Servizio | Porta | Tipo | Responsabilità |
|---|---|---|---|
| **user-service** | 5001 | Obbligatorio | Anagrafica utenti (attendee, speaker, organizer). Fonte di verità per l'identità. |
| **event-service** | 5002 | Obbligatorio | Conferenze con ciclo di vita (draft→published→cancelled) e capienza. Valida l'organizzatore su user-service. |
| **registration-service** | 5003 | Obbligatorio | Iscrizioni utenti-evento. Verifica utente su user-service ed evento su event-service. Gestisce la capienza. |
| feedback-service | 5004 | Opzionale | Valutazioni degli eventi da parte degli iscritti. |
| notification-service | 5005 | Opzionale | Notifiche agli utenti, singole e massive (broadcast). |

## Dipendenze tra servizi

```
user-service  ◄──  event-service
user-service  ◄──  registration-service  ◄──  feedback-service
event-service ◄──  registration-service  ◄──  notification-service (broadcast)
event-service ◄──  feedback-service (summary)
user-service  ◄──  notification-service
```

## Principi di dominio rilevanti per la progettazione

- Un **utente** ha un ruolo (`attendee`, `speaker`, `organizer`); solo gli organizzatori
  possono creare eventi.
- Un **evento** nasce come `draft`; deve essere `published` per accettare iscrizioni.
- Un'**iscrizione** è sempre `confirmed` alla creazione; può essere cancellata (liberando
  un posto). Il prezzo viene copiato dall'evento al momento dell'iscrizione.
- Un **feedback** richiede un'iscrizione `confirmed` attiva; uno per coppia
  `(user_id, event_id)`.
- Le **notifiche** sono in coda (`queued`) e transitano verso `sent` o `failed`; un
  broadcast crea una notifica per ogni iscritto `confirmed` all'evento.

## Fonte di verità dei contratti

I contratti OpenAPI in `Exam/techconf-exam/contracts/openapi/*.yaml` sono la fonte
autoritativa delle interfacce HTTP. Non si modificano. Ogni implementazione deve
conformarsi al contratto prima di essere considerata completa.
