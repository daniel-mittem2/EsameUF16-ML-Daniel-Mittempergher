# Verifica obbligatoria — 25 settembre 2026

Esecuzione effettiva con Python 3.12.14; tutti i codici di uscita in
`results.json` sono zero.

| Verifica | Risultato |
|---|---|
| Unit user | 168 superati, coverage 95,33% |
| Unit event | 222 superati, coverage 97,16% |
| Unit registration | 208 superati, coverage 97,19% |
| Integrazione propria event | 3 superati |
| Integrazione propria registration | 4 superati |
| Collaudo obbligatorio docente | 27 superati, 10 esclusi dal marker |
| Checksum protetti | 17 corrispondenti |
| Script hook | Configurazione valida; payload simulati per i 3 servizi superati |

I log omonimi contengono gli output completi. `mandatory.txt` è l’output
del collaudo, copiato anche in `../collaudo.txt` dopo l’esito positivo.
L’esecuzione dell’hook al salvataggio nell’IDE non è stata osservata.
Le issue GitHub e il tag finale non sono completati da questi test.

Le dipendenze di verifica sono state installate in un ambiente separato dalla
cartella del progetto. I test hanno usato una directory temporanea accessibile;
i primi tentativi interrotti dai permessi di Windows e dalle porte già occupate
sono stati rieseguiti integralmente dopo la risoluzione dei problemi ambientali.
I processi del collaudo sono stati chiusi al termine.
