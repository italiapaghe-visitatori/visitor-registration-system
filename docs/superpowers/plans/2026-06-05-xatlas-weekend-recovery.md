# XAtlas Weekend Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This is a LIVE RUNBOOK — esecuzione interattiva con l'utente che clicca console XAtl@s + Claude verifica via SSH.

**Goal:** Sbloccare sync NET9x XAtlas affinché i 38 visitor pre-attivati per evento Formazione DM (event_id `450da933-f438-43ed-853f-6ede8ece3659`) vengano pushati ai 4 controller (TORNELLO_IN/OUT, AXG_INGRESSO/PORTELLO).

**Architecture:** Approccio stadiato a rischio crescente. Operatore clicca comandi su client XAtl@s desktop, Claude verifica stato in tempo reale via `ssh srvxatlas` + `psql AXS_DB`. Stop-points oggettivi ad ogni stage.

**Tech Stack:** XAtl@s desktop client (Java), PostgreSQL 13 AXS_DB, SSH ed25519 srvxatlas, comandi consolle XAtlas (03-XXX, 05-XXX, 09-XXX).

**Sicurezza dipendenti:** AXG_INGRESSO e TORNELLO_IN MAI toccati senza prima conferma successo su AXG_PORTELLO / TORNELLO_OUT.

**NEVER-DO:** 05-205 Reinvio tabelle, 03-275 Cancellazione parziale DB, 03-280 Cancellazione completa DB, 03-265 Interrompi azioni.

---

## File Structure

Questo piano modifica SOLO:

- `c:\Users\GaInformatica\.claude\projects\c--Users-GaInformatica-Documents-Progetti-OpenCode-visitor-registration-system\memory\project_session_2026-06-05_xatlas_incident.md` (append outcome notes)

Niente code changes. Esecuzione operativa live.

---

## Task 0: Pre-flight check

**Files:** none

- [ ] **Step 0.1: Conferma orario e finestra notturna**

Verifica orologio: deve essere ≥ 22:00 (finestra a basso traffico).
Se < 22:00 → aspetta.
Se ≥ 22:00 → procedi.

- [ ] **Step 0.2: Conferma client XAtl@s aperto + login ADMIN**

Sul tuo PC: deve essere visibile la finestra "XAtl@s - WSM - Web System Manager - Edizione: C-XAtl@s" con menu Sistema, Regole, Diritti operatori, Analisi, ecc.

Se non aperto → riapri `gui.axslauncher` da Downloads.

- [ ] **Step 0.3: Claude verifica SSH srvxatlas funzionante**

Claude esegue:
```bash
ssh srvxatlas 'powershell -NoProfile -Command "(Get-Service wsm_service_windows).Status"'
```
Expected: `Running`

Se diverso → STOP, segnala.

- [ ] **Step 0.4: Claude verifica AXS_DB raggiungibile**

Claude esegue:
```bash
ssh srvxatlas "psql -U postgres -d AXS_DB -c \"SELECT NOW();\""
```
Expected: timestamp recente, no errori.

Se errore → STOP, segnala.

- [ ] **Step 0.5: Claude snapshot BASELINE pre-test**

Claude esegue:
```bash
ssh srvxatlas "psql -U postgres -d AXS_DB -c \"SELECT 'baseline' AS chk, synchronizing::text, log_update::text FROM field_queue_status UNION ALL SELECT 'dipendenti_hash', md5(string_agg(identifier || ',' || COALESCE(surname,'') || ',' || COALESCE(name,''), '|' ORDER BY identifier)), COUNT(*)::text FROM internal_user UNION ALL SELECT 'visitor_vis_count', COUNT(*)::text, NULL FROM external_user WHERE identifier LIKE 'VIS%' AND log_insert >= NOW() - INTERVAL '24 hours' UNION ALL SELECT 'recent_trans', COUNT(*)::text, COALESCE(MAX(event_timestamp)::text,'none') FROM transaction WHERE event_timestamp >= NOW() - INTERVAL '24 hours';\""
```

Claude salva output come BASELINE (servirà per confronto post-test).

---

## Task 1: Stage 1 — Info Gathering (rischio ZERO)

**Files:** none

- [ ] **Step 1.1: Naviga ad Analisi Hardware sul client**

Sul client XAtl@s desktop:
1. Click sulla tab **Analisi** in alto
2. Nel menu laterale, click su **Dispositivi hardware**
3. Click sul bottone **Ricerca** (lente blu)

Expected: lista 6 dispositivi (AXG_INGRESSO, AXG_PORTELLO, LOCALFM, TORNELLO_IN, TORNELLO_OUT, WSM)

- [ ] **Step 1.2: Esegui 09-005 su LocalFM**

1. Doppio click sulla riga **LOCALFM** (pallino rosso)
2. Si apre il dettaglio
3. Nella sezione "Comandi", scorri e trova **09-005 Richiesta stato corrente**
4. Click su **09-005 Richiesta stato corrente**
5. Aspetta 5-10 sec, dovrebbe apparire un evento nella sezione "Eventi recenti"
6. **Screenshot di "Eventi recenti" + "Stato attuale"**

Mandami screenshot.

- [ ] **Step 1.3: Esegui 09-005 su TORNELLO_IN**

1. Chiudi il dettaglio LOCALFM (X in alto)
2. Doppio click su **TORNELLO_IN**
3. Click su **09-005 Richiesta stato corrente**
4. **Screenshot di "Eventi recenti" + "Stato attuale"**

- [ ] **Step 1.4: Esegui 09-005 su TORNELLO_OUT**

1. Chiudi dettaglio
2. Doppio click su **TORNELLO_OUT**
3. Click su **09-005 Richiesta stato corrente**
4. **Screenshot**

- [ ] **Step 1.5: Esegui 09-005 su AXG_INGRESSO**

1. Chiudi dettaglio
2. Doppio click su **AXG_INGRESSO**
3. Click su **09-005 Richiesta stato corrente**
4. **Screenshot**

- [ ] **Step 1.6: Esegui 09-005 su AXG_PORTELLO**

1. Chiudi dettaglio
2. Doppio click su **AXG_PORTELLO**
3. Click su **09-005 Richiesta stato corrente**
4. **Screenshot**

- [ ] **Step 1.7: Claude analizza screenshot Stage 1**

Claude riceve i 5 screenshot e analizza:
- Quali device hanno "CONFIGURAZIONE NECESSARIA" come evento recente
- Quali device hanno "AGGIORNAMENTI IN CODA"
- Stato di ciascuno

Output: tabella riassuntiva 5 device + diagnosi.

---

## Task 2: Stage 2 — Push centralizzato 03-315 LocalFM (rischio BASSO)

**Files:** none

- [ ] **Step 2.1: Apri dettaglio LOCALFM**

Sul client XAtl@s:
1. Da Dispositivi Hardware, doppio click su **LOCALFM**

- [ ] **Step 2.2: Esegui comando 03-315**

1. Nella lista "Comandi", scorri fino a trovare **03-315 Configura Field Controllers**
2. **STOP — conferma a Claude prima di cliccare**: "sto per cliccare 03-315 su LocalFM"
3. Claude conferma GO
4. Click su **03-315 Configura Field Controllers**

- [ ] **Step 2.3: Aspetta 60 secondi**

Conta a mente o usa timer. NON cliccare altro.

- [ ] **Step 2.4: Screenshot eventi recenti LocalFM post comando**

Mandami screenshot di "Eventi recenti" su LOCALFM.

---

## Task 3: Stage 3 — Verifica post Stage 2 (rischio ZERO)

**Files:** none

- [ ] **Step 3.1: Claude verifica field_queue_status**

Claude esegue:
```bash
ssh srvxatlas "psql -U postgres -d AXS_DB -c \"SELECT synchronizing::text AS s, log_update::text AS u, log_insert::text AS i FROM field_queue_status;\""
```

Expected change: `log_update` recente (dopo Stage 2), non più `2026-05-15 19:07:11.01`.

- [ ] **Step 3.2: Claude verifica nuove transazioni**

Claude esegue:
```bash
ssh srvxatlas "psql -U postgres -d AXS_DB -c \"SELECT COUNT(*) AS recent_trans, COALESCE(MAX(event_timestamp)::text, 'none') AS latest FROM transaction WHERE event_timestamp >= NOW() - INTERVAL '5 minutes';\""
```

- [ ] **Step 3.3: Click 09-005 su TORNELLO_IN per verifica device-side**

Sul client XAtl@s:
1. Chiudi dettaglio LOCALFM
2. Doppio click su **TORNELLO_IN**
3. Click su **09-005 Richiesta stato corrente**
4. **Screenshot "Stato attuale"**: confronta con baseline Step 1.3
   - Se "CONFIGURAZIONE NECESSARIA" è SCOMPARSO → SUCCESS
   - Se ancora presente → procedi Stage 4

- [ ] **Step 3.4: DECISIONE GO/STOP**

Claude valuta combinando:
- log_update di field_queue_status (recente o no)
- Stato 09-005 TORNELLO_IN (cambiato o no)

**Se PASS (entrambi cambiati):**
- → Procedi a Task 8 (post-execution snapshot)
- Salta Task 4, 5, 6, 7

**Se FAIL (almeno uno invariato):**
- → Procedi a Task 4 (Stage 3.5)

---

## Task 4: Stage 3.5 — Discovery comandi AXG_PORTELLO (rischio ZERO)

**Files:** none

ESEGUI SOLO SE Task 3 Step 3.4 = FAIL.

- [ ] **Step 4.1: Apri dettaglio AXG_PORTELLO**

Sul client XAtl@s:
1. Chiudi dettaglio precedente
2. Doppio click su **AXG_PORTELLO**

- [ ] **Step 4.2: Scorri TUTTA la lista comandi**

Nella sezione "Comandi", scorri dall'alto al basso per vedere TUTTI i comandi.

**Screenshot di ogni schermata mentre scorri** (probabilmente 3-4 screenshot perché la lista è lunga).

- [ ] **Step 4.3: Claude analizza lista comandi AXG_PORTELLO**

Claude cerca:
- Comando con descrizione "Invia configurazione" o simile (push config sicuro)
- Codici `04-XXX`, `05-XXX`, `06-XXX` con semantica push/sync/allinea
- Esclude qualsiasi "Reinvio", "Cancellazione", "Azzera", "Blocca", "Apertura incondizionata"

Output: comando candidato per Stage 4 (preferito) o "non trovato".

---

## Task 5: Stage 4 — Push per-tornello (rischio MEDIO)

**Files:** none

ESEGUI SOLO SE Task 3 FAIL.

- [ ] **Step 5.1: DECISIONE target Stage 4**

Basato su Step 4.3:
- Se Claude ha trovato comando push config su AXG_PORTELLO → **target = AXG_PORTELLO** (preferito, basso impatto dipendenti)
- Se NON trovato → **target = TORNELLO_OUT** (fallback)

Claude comunica esplicitamente: "target Stage 4 = X, comando = Y".

- [ ] **Step 5.2: Apri dettaglio del target**

Sul client XAtl@s:
1. Chiudi dettaglio precedente
2. Doppio click sul target (AXG_PORTELLO o TORNELLO_OUT)

- [ ] **Step 5.3: STOP — conferma esplicita Claude prima del click**

Operatore: "sto per cliccare [comando] su [target]"
Claude conferma: "GO".

- [ ] **Step 5.4: Click comando**

Click sul comando identificato in Step 5.1 (`05-125 Invia configurazione` su TORNELLO_OUT, oppure equivalente su AXG_PORTELLO).

- [ ] **Step 5.5: Aspetta 60 secondi**

NON cliccare altro.

- [ ] **Step 5.6: Screenshot eventi recenti post Stage 4**

Mandami screenshot.

---

## Task 6: Stage 5 — Verifica post Stage 4 + Rollback decision

**Files:** none

ESEGUI SOLO SE Task 5 eseguito.

- [ ] **Step 6.1: Click 09-005 su target Stage 4**

Sul client XAtl@s, sullo stesso device target:
1. Click su **09-005 Richiesta stato corrente**
2. **Screenshot**

- [ ] **Step 6.2: Claude verifica AXS_DB post Stage 4**

Claude esegue:
```bash
ssh srvxatlas "psql -U postgres -d AXS_DB -c \"SELECT 'queue' AS chk, synchronizing::text AS s, log_update::text AS u FROM field_queue_status UNION ALL SELECT 'recent_trans', COUNT(*)::text, COALESCE(MAX(event_timestamp)::text,'none') FROM transaction WHERE event_timestamp >= NOW() - INTERVAL '10 minutes' UNION ALL SELECT 'dipendenti_hash', md5(string_agg(identifier || ',' || COALESCE(surname,'') || ',' || COALESCE(name,''), '|' ORDER BY identifier)), COUNT(*)::text FROM internal_user;\""
```

- [ ] **Step 6.3: Claude confronta con BASELINE Task 0.5**

Outcome possibili:
- **GO (sync ripristinata)**: log_update aggiornato + nuove transazioni + dipendenti_hash invariato + stato 09-005 OK → SUCCESS
- **STAY (no change)**: log_update invariato + dipendenti_hash invariato + stato 09-005 invariato → nessun danno ma push fallito → Plan B
- **WIPE (cache compromessa)**: dipendenti_hash CAMBIATO oppure stato 09-005 mostra errori → ROLLBACK IMMEDIATO

- [ ] **Step 6.4: Esegui rollback SE WIPE rilevato**

ESEGUI SOLO SE Step 6.3 = WIPE.

Sul client XAtl@s, sul target Stage 4:
1. Click su **05-085 Ripristina normalità**
2. Aspetta 60 sec
3. Apri dettaglio **LOCALFM**
4. Click su **03-320 Riavvia applicazione**
5. Aspetta 2-3 minuti per ripartenza
6. Claude verifica via SSH: `field_queue_status` non in stato allarme, dipendenti hash tornato al baseline

Se dipendenti hash NON torna al baseline dopo rollback → STOP, situazione critica, chiama supporto.

---

## Task 7: Stage 4 espanso (solo se GO Task 6)

**Files:** none

ESEGUI SOLO SE Task 6 Step 6.3 = GO.

Stage 4 ha funzionato sul primo target. Espandi agli altri tornelli **uno alla volta**:

- [ ] **Step 7.1: Stage 4 su secondo tornello (preferito TORNELLO_OUT se prima era AXG_PORTELLO)**

Sul client XAtl@s:
1. Chiudi dettaglio precedente
2. Doppio click sul secondo target
3. STOP — conferma Claude
4. Click `05-125 Invia configurazione`
5. Aspetta 60 sec
6. Click 09-005 per verifica
7. Screenshot
8. Claude verifica AXS_DB (stesso comando Step 6.2)

- [ ] **Step 7.2: Decisione GO/STOP**

Se Step 7.1 = GO → espandi a TORNELLO_IN (Step 7.3)
Se Step 7.1 = WIPE → ROLLBACK come Step 6.4, NON continuare

- [ ] **Step 7.3: Stage 4 su TORNELLO_IN**

ATTENZIONE: tornello principale dipendenti.

Solo se Step 7.1 GO + tutti i target precedenti GO senza problemi.

Procedura identica a Step 7.1, target = TORNELLO_IN.

- [ ] **Step 7.4: AXG_INGRESSO ultimo per ridondanza**

Stessa procedura su AXG_INGRESSO.

---

## Task 8: Post-execution snapshot + memoria

**Files:**
- Modify: `c:\Users\GaInformatica\.claude\projects\c--Users-GaInformatica-Documents-Progetti-OpenCode-visitor-registration-system\memory\project_session_2026-06-05_xatlas_incident.md`

- [ ] **Step 8.1: Claude snapshot finale AXS_DB**

Stesso comando di Step 0.5. Salva output come SNAPSHOT_FINALE.

- [ ] **Step 8.2: Claude confronta BASELINE vs SNAPSHOT_FINALE**

Diff:
- dipendenti_hash: deve essere INVARIATO
- field_queue_status.log_update: dovrebbe essere RECENTE
- recent_trans: dovrebbe essere > 0
- visitor_vis_count: invariato (38)

- [ ] **Step 8.3: Claude appende outcome al memory file**

Append a `project_session_2026-06-05_xatlas_incident.md` sezione:
```markdown
## Aggiornamento esecuzione Plan A — 05-06/06/2026 notte

### Stages eseguiti
- Stage 1: [outcome screenshot]
- Stage 2: [outcome]
- Stage 3: [GO/FAIL]
[...]

### Outcome finale
- [SUCCESS / PARTIAL / FAILED]
- Sync ripristinata: [yes/no]
- Dipendenti impattati: [yes/no]
- Plan B necessario per eventi: [yes/no]

### Verifica canary lunedi
- Badge 257802 (DANIELA ABBRUZZESE) test fisico AXG_PORTELLO o TORNELLO_OUT alle 7:00
```

- [ ] **Step 8.4: Commit memoria + log esecuzione**

Claude esegue:
```bash
cd "c:\Users\GaInformatica\Documents\Progetti_OpenCode\visitor-registration-system"
git add docs/superpowers/plans/2026-06-05-xatlas-weekend-recovery.md
git commit -m "Plan: XAtlas Weekend Recovery executed $(date +%Y-%m-%d)"
```

---

## Decisioni Stop-Point riassuntive

| Stage | PASS → STOP qui | FAIL → Procedi |
|---|---|---|
| Stage 2-3 | Task 8 (success) | Task 4 (Stage 3.5) |
| Stage 4-5 (GO) | Task 7 (espandi tornelli) | --- |
| Stage 4-5 (STAY) | Task 8 (no danno, Plan B per eventi) | --- |
| Stage 4-5 (WIPE) | Task 6 Step 6.4 (rollback) | Task 8 con flag CRITICAL |
| Rollback failed | STOP CRITICO | Contatta supporto Zucchetti (eccezione mandato) |

---

## NEVER-DO list (riassunto)

Durante TUTTI gli stage:

❌ **05-205 Reinvio tabelle** — distruttore atomico, cancella DB locale tornello
❌ **03-275 Cancellazione parziale database**
❌ **03-280 Cancellazione completa database** — questo è quello che ha causato l'incidente del 26/05
❌ **03-265 Interrompi tutte le azioni in corso** — cancellerebbe i 38 visitor in coda
❌ Eseguire qualsiasi comando su TORNELLO_IN senza prima confermare successo su altri 2 tornelli
❌ UPDATE/DELETE/INSERT diretto su AXS_DB (anche da Claude)
❌ Restart servizi (wsm_service_windows, ecc) senza esplicita autorizzazione utente

---

## Self-Review check

**Spec coverage:** ✅
- Stage 1 → Task 1
- Stage 2 → Task 2
- Stage 3 → Task 3
- Stage 3.5 → Task 4
- Stage 4 → Task 5
- Stage 5 → Task 6 (verifica + rollback)
- Espansione Stage 4 → Task 7
- Rollback → Task 6 Step 6.4
- Memoria → Task 8

**Placeholder scan:** ✅ nessun TBD/TODO. Tutti i comandi shell sono completi.

**Type consistency:** ✅ Naming coerente (TORNELLO_OUT, AXG_PORTELLO, ecc).

**Ambiguity check:** ✅ Stop-points oggettivi (hash, log_update timestamp, stato 09-005 testo).

---

## Execution

Pronto per esecuzione live alle 22:00+. Stima durata totale: 30-60 min (dipende da quanti stage servono).
