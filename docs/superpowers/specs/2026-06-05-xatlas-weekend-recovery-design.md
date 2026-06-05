# XAtlas Weekend Recovery — Staged Approach Design

**Data:** 2026-06-05 sera
**Eventi imminenti:** 2 eventi Martedì 9/6 + Formazione DM 10-11/6
**Vincolo critico:** badge dipendenti SACRI, non toccare
**Esecuzione:** stasera dalle 22:00 — finestra a basso traffico tornelli

## Goal

Sbloccare la sync NET9x bloccata dal 26/05 affinché i 38 utenti VIS pre-attivati per Formazione DM (event_id `450da933-f438-43ed-853f-6ede8ece3659`) vengano spinti ai 4 controller (TORNELLO_IN/OUT, AXG_INGRESSO/PORTELLO) e i loro badge fisici funzionino al tornello.

## Architettura della soluzione

**Approccio stadiato a rischio crescente con stop-points.** Cinque stage sequenziali, ognuno con pass/fail criteria oggettivi via SSH/console. Se uno stage low-risk risolve, si ferma lì. Lo stage 4 (per-tornello, rischio medio) viene eseguito solo se Stage 1-3 non bastano.

**Componenti:**
- **Console XAtlas web** (192.168.2.196:8080, admin/admin) — esecuzione comandi su LocalFM e tornelli
- **SSH srvxatlas** — verifica stato AXS_DB tra uno stage e l'altro
- **psql -U postgres -d AXS_DB** — query read-only su `field_queue_status`, `transaction`, `external_user`
- **Operator umano (Antonio)** — esegue clic console + decide GO/STOP ad ogni stage
- **Claude** — guida step-by-step, esegue verifiche SSH, fornisce decisione GO/STOP

## Tech stack

- XAtlas SuperTRAX (Zucchetti) — web UI console
- PostgreSQL 13 (AXS_DB) — query verifica
- SSH + chiave ed25519 — accesso server
- Browser Chrome via VPN — accesso console da casa

---

## Stages

### Stage 1 — Information Gathering (rischio: ZERO)

**Scopo:** stato di ogni controller via 09-005 prima di toccare nulla. Baseline.

**Azioni operatore:**
1. Console XAtlas web → DISPOSITIVI HARDWARE
2. Per ciascuno dei 4 tornelli (TORNELLO_IN id=202, TORNELLO_OUT id=205, AXG_INGRESSO id=240, AXG_PORTELLO id=242):
   - Click sulla riga
   - Click su comando `09-005 Richiesta stato corrente`
   - Screenshot della risposta in "Eventi recenti" / "Stato attuale"
3. Per LocalFM (id=195):
   - Click sulla riga
   - Click su `09-005 Richiesta stato corrente`
   - Screenshot

**Verifiche Claude via SSH:**
```sql
SELECT 'queue' AS chk, synchronizing::text, log_update::text FROM field_queue_status;
SELECT COUNT(*) FROM transaction WHERE event_timestamp >= NOW() - INTERVAL '5 minutes';
```

**Pass criteria:** screenshot raccolti, baseline documentato.
**Fail criteria:** console non risponde, comando 09-005 dà errore.
**Decision GO/STOP:** Stage 1 SEMPRE eseguito; STOP solo se console down.

### Stage 2 — Push Centralizzato via LocalFM (rischio: BASSO)

**Scopo:** comando master di Field Manager per ridistribuire config a tutti i field controllers, senza toccare i singoli tornelli.

**Comando candidato:** `03-315 Configura Field Controllers` su LocalFM (id=195).

**Semantica analizzata (workflow 360):**
- Comando di alto livello sul FM master
- Push incrementale della config corrente verso i field controllers
- Documentazione Zucchetti suggerisce uso normale durante config changes
- Rischio cache wipe: BASSO (<5%) perché operatore master, non distruttivo per design

**Azioni operatore:**
1. Console XAtlas web → LocalFM (riga rossa "allarme")
2. Click comando `03-315 Configura Field Controllers`
3. Aspetta conferma esecuzione comando

**Wait time:** 60 secondi.

**Pass criteria:** comando esegue senza errori in "Eventi recenti".
**Fail criteria:** errore esecuzione, console non risponde, allarmi nuovi.

### Stage 3 — Verifica Remota Post Stage 2 (rischio: ZERO)

**Scopo:** capire se Stage 2 ha fatto effetto senza badge fisico.

**Azioni operatore:**
1. Console XAtlas web → torna a TORNELLO_IN (o un altro tornello)
2. Click `09-005 Richiesta stato corrente`
3. Confronta con Stage 1 baseline

**Verifiche Claude via SSH:**
```sql
SELECT 'queue' AS chk, synchronizing::text, log_update::text FROM field_queue_status;
SELECT COUNT(*) FROM transaction WHERE event_timestamp >= NOW() - INTERVAL '10 minutes';
SELECT identifier, name, surname FROM external_user WHERE identifier = 'VIS257802';
```

**Pass criteria (GO STOP HERE, SUCCESS):**
- `field_queue_status.log_update` aggiornato (data recente, non più 15/05)
- Stato 09-005 cambiato da "CONFIGURAZIONE NECESSARIA" a normale
- Eventuali nuove transazioni in transaction table

**Fail criteria (procedi a Stage 4):**
- log_update ancora vecchio
- Stato 09-005 immutato

**Decision GO/STOP:** se PASS → spec completato, scrivi outcome doc e prepara conferma per canary fisico lunedì mattina. Se FAIL → procedi Stage 4.

### Stage 3.5 — Discovery comandi AXG_PORTELLO (rischio: ZERO)

**ESEGUI SOLO SE STAGE 3 FAIL e si vuole procedere.**

**Scopo:** AXG_PORTELLO è AXGATE (hardware diverso da SUPERTRAX dei TORNELLO_IN/OUT), set comandi non ancora mappato. Verifica se esiste comando equivalente a "Invia configurazione".

**Azioni operatore:**
1. Console XAtlas → DISPOSITIVI HARDWARE → click su `AXG_PORTELLO` (riga verde "normale")
2. Scorri tutta la lista "Comandi" disponibili
3. Screenshot di TUTTI i comandi disponibili (~10-20 voci, devi scrollare)
4. Manda screenshot a Claude

**Verifica Claude:**
- Cerca comando con descrizione simile a: "Invia configurazione", "Aggiorna configurazione", "Allinea", "Configura", "Sincronizza database"
- Cerca anche `04-XXX`, `05-125` (se esiste anche qui), `06-XXX` che potrebbero essere "push config"
- Identifica anche eventuali "Reinvio" / "Cancella" equivalenti distruttivi VIETATI

**Outcome:**
- **TROVATO comando "push config" sicuro** → Stage 4 esegue su AXG_PORTELLO (preferito, basso rischio)
- **NON trovato o solo equivalenti distruttivi** → Stage 4 fallback su TORNELLO_OUT come originale

### Stage 4 — Per-Tornello Invia Configurazione (rischio: MEDIO)

**ESEGUI SOLO SE STAGE 3 FAIL.**

**Target preferito:** AXG_PORTELLO (id=242) — basso traffico dipendenti, occasionale.
**Target fallback:** TORNELLO_OUT (id=205) — uscita principale, alto traffico ma se cache wiped i dipendenti possono entrare da TORNELLO_IN.

**Comando:**
- Se Stage 3.5 ha trovato equivalente su AXG_PORTELLO: usa quello su AXG_PORTELLO
- Altrimenti: `05-125 Invia configurazione` su TORNELLO_OUT

**Semantica 05-125 analizzata:**
- "Invia" ≠ "Reinvio": invia config incrementale, NON distruttiva per design
- Distinguersi da 05-205 "Reinvio tabelle" (distruttore atomico VIETATO)
- Rischio cache wipe: 15-20% (incertezza)

**Mitigazione rischio (AXG_PORTELLO preferito):**
- Bassa frequenza uso dipendenti → impatto minimale anche se cache wiped
- AXG_PORTELLO down: dipendenti continuano da TORNELLO_IN e TORNELLO_OUT (principali)
- Eseguito di notte (post 22:00) — fascia minima passaggi
- 60+ ore buffer fino a lunedì mattina per recovery

**Mitigazione rischio (TORNELLO_OUT fallback):**
- Uscita: se cache wiped, dipendenti possono ENTRARE da TORNELLO_IN normalmente
- Notte (post 22:00) — dipendenti non al lavoro
- Stesso buffer 60+ ore

**Azioni operatore:**
1. Console XAtlas → DISPOSITIVI HARDWARE → click sul tornello scelto (AXG_PORTELLO preferito)
2. Click comando determinato in Stage 3.5
3. Aspetta 60 sec

**Pass criteria:** comando esegue senza errori.
**Fail criteria:** errori, allarmi nuovi, stato 09-005 peggiora.

### Stage 5 — Verifica Post Stage 4 + Rollback Opzionale (rischio: ZERO)

**Azioni operatore:**
1. Console → TORNELLO_OUT → click `09-005 Richiesta stato corrente`
2. Screenshot risposta

**Verifiche Claude via SSH:**
```sql
SELECT * FROM field_queue_status;
SELECT MAX(event_timestamp) FROM transaction;
```

**Outcome possibili:**
- **GO (sync OK)**: stato 09-005 mostra normale, log_update recente. Allora ripeti Stage 4 su TORNELLO_IN e AXG_INGRESSO (NON AXG_PORTELLO per ora, vincolo dipendenti). Dopo, attendi conferma lunedì canary fisico.
- **STAY (no change)**: stato uguale, push fallito ma nessun danno. Procedi Plan B.
- **WIPE (cache compromessa)**: se stato TORNELLO_OUT mostra "0 utenti" o errori → ROLLBACK immediato.

**Rollback procedure (se WIPE):**
1. Console → TORNELLO_OUT → click `05-085 Ripristina normalità`
2. Aspetta 60 sec
3. Console → LocalFM → click `03-320 Riavvia applicazione`
4. Aspetta 2-3 min per ripartenza
5. Verifica via SSH che field_queue_status sia in stato non-allarme
6. Se dipendenti devono uscire e TORNELLO_OUT non risponde: usa porta fisica laterale (chiave operatrice) come emergency exit fino a recovery

## Data Flow

```
Stage 1 (info, 09-005 su tutti)
    ↓
Stage 2 (03-315 LocalFM)
    ↓
Stage 3 (verifica)
    ↓
  ┌─PASS → STOP, success → canary fisico lunedi
  ↓ FAIL
Stage 3.5 (discovery comandi AXG_PORTELLO)
    ↓
  ┌──────────────────────┐
  ↓                       ↓
  Trovato push config     Non trovato
  AXG_PORTELLO            ↓
  ↓                       Stage 4 fallback su TORNELLO_OUT
  Stage 4 preferito su AXG_PORTELLO
    ↓
Stage 5 (verifica post Stage 4)
    ↓
  ┌─────┬─────┐
  ↓     ↓     ↓
  GO   STAY  WIPE
   |    |     |
   |    |     └→ Rollback (05-085 + 03-320)
   |    └→ Plan B totale
   └→ Espandi Stage 4 a TORNELLO_OUT poi TORNELLO_IN
```

## Error Handling

| Scenario | Azione |
|---|---|
| Console XAtlas non risponde | STOP, attendi mattina, prova restart sshd via SSH |
| Comando dà errore | Screenshot errore, mandalo a Claude, valuta |
| Verifica SSH fallisce (no connection) | Retry 3 volte, se persiste STOP |
| Allarme nuovo appare in console | STOP, screenshot, valuta con Claude prima di proseguire |
| Cache wipe rilevato (stato 0 utenti) | Rollback immediato (Stage 5 procedure) |
| 03-315 dà "Comando già in coda" | Aspetta 2 min, retry una volta sola |

## Testing

**Non c'è test pre-deploy possibile** (sistema live, nessun staging environment).

**Verifica successo finale:**
- Lunedì mattina presto (prima delle 8) in laboratorio
- Operatore prende badge fisico 257802 (DANIELA ABBRUZZESE)
- Avvicina al TORNELLO_OUT
- Risultato atteso: tornello apre + display "ABBRUZZESE DANIELA"

**Se canary lunedì fallisce nonostante test stasera OK:**
- Plan B totale per i 3 eventi

## Sicurezza dipendenti — Garanzie

1. **Mai eseguire comandi su tornelli ad uso dipendenti durante orario lavoro** — finestra ammessa: ven 22:00 → lun 6:00
2. **TORNELLO_IN** (ingresso dipendenti la mattina): test solo se Stage 4 su TORNELLO_OUT è SUCCESS
3. **AXG_PORTELLO** (anche usato da dipendenti): SKIP del tutto, non toccato in questo design
4. **Rollback sempre disponibile** — comandi 05-085 (ripristina normalità) e 03-320 (riavvia app) sono per design non distruttivi

## NEVER-DO durante questa procedura

❌ `05-205 Reinvio tabelle` — CONFERMATO distruttore atomico
❌ `03-275 Cancellazione parziale database` — distruttivo
❌ `03-280 Cancellazione completa database` — distruttivo, è quello che ha causato l'incidente del 26/05
❌ `03-265 Interrompi tutte le azioni in corso` — cancellerebbe i nostri 38 visitor in coda
❌ Modifiche dirette ad AXS_DB (UPDATE/DELETE/INSERT)
❌ Eseguire qualsiasi cosa su TORNELLO_IN o AXG_INGRESSO senza prima aver verificato successo TORNELLO_OUT
❌ Continuare se Claude o operatore in dubbio — sempre fermarsi e valutare

## Out of scope

- Fixing license keys "InstallKeys mac check failed!" — non bloccante per oggi
- Restaurare tabella `terminal` (vuota) — PITR PostgreSQL non disponibile
- Implementare polling agent Python (hardening) — post-evento
- Configurare backup automatici PostgreSQL — post-evento
- Coordinamento con Zucchetti — esplicitamente escluso dall'utente

## Plan B Fallback (se questo design fallisce)

Procedura desk manuale (vedi `XAtlas_Recovery_360_2026-06-05.md` sezione Plan B Dual Event):
- 2 operator desk per i 2 eventi paralleli martedì
- 1 operator alla console XAtlas web
- Ospite arriva → identifica → marca presenza su admin → console XAtlas comando `05-045 Apertura singola in entrata` su tornello → ospite passa
- Lo stesso per uscita con `05-065 Apertura singola in uscita`
- Probabilità successo Plan B: 95%

## Success Metrics

- **Stage 2-3 SUCCESS (best case)**: visitor sync ripristinata stasera, lunedì solo canary, eventi automatici → confidence 95%
- **Stage 4-5 SUCCESS (medium case)**: stesso outcome ma 1 stage più rischioso, confidence 85%
- **Failure + rollback OK**: stato attuale invariato, Plan B per eventi → confidence 95% (Plan B robusto)
- **Failure + cache wipe + no rollback**: catastrofico, ma molto improbabile dato il design conservativo

## Self-Review

**Placeholder scan:** nessuno (controllato).
**Consistency:** flow stages → verifiche → outcome coerenti.
**Scope:** focused su recovery weekend, non include hardening post-evento (giustamente fuori scope).
**Ambiguity:** "stato 09-005 normale" potrebbe essere interpretato in 2 modi — clarification: il testo cambia da "CONFIGURAZIONE NECESSARIA" a vuoto / "OK" / "normale" / nessun allarme.

---

**Approvazione utente richiesta prima di procedere all'implementazione (writing-plans skill).**
