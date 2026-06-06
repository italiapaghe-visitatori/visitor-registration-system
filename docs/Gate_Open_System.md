# 🚪 Sistema Apertura Tornelli Manuale

> **Workaround sync XAtlas rotto dal 15/05/2026** — bottoni nell'admin platform per aprire i tornelli senza dipendere dalla console XAtlas.

**Build admin**: `2026-06-06 · gate-open + voice`
**Agent**: `1.6.0-gate-open`
**Migration Supabase**: `v25`

---

## Architettura

```
┌──────────────────────┐         ┌─────────────────────┐
│  Admin (browser)     │         │ Supabase             │
│  click 🚪 IN / OUT   │ ──POST→ │ gate_open_queue      │
│  oppure voce         │         │ (status=pending)     │
└──────────────────────┘         └──────────┬──────────┘
                                            │ polling 1s
                                            ▼
                                  ┌─────────────────────┐
                                  │  Zucchetti Agent    │
                                  │  (srvxatlas)        │
                                  │  send_fmc_command   │
                                  └──────────┬──────────┘
                                             │ telnet 8189
                                             ▼
                                  ┌─────────────────────┐
                                  │  FMC (LocalFM 195)  │
                                  │  EXEC <id> openEntry│
                                  └──────────┬──────────┘
                                             │
                                             ▼
                                  ┌─────────────────────┐
                                  │ Tornello → APRE     │
                                  │ (300-800 ms total)  │
                                  └─────────────────────┘
```

## Mapping tornelli → ID

| ID | Nome | Tipo | Metodo entry | Metodo exit |
|---|---|---|---|---|
| 202 | TORNELLO_IN | SuperTraxLite | `openEntryOneShot` | (rev) |
| 205 | TORNELLO_OUT | SuperTraxLite | (rev) | `openExitOneShot` |
| 240 | AXG_INGRESSO | X0 | `openEntryOneShot` | — |
| 242 | AXG_PORTELLO | X0 | — | `openExitOneShot` |

Default UI:
- `🚪 IN`  → gate 202 (TORNELLO_IN), direction=entry
- `🚪 OUT` → gate 205 (TORNELLO_OUT), direction=exit

---

## Procedura installazione

### 1. Apply migration su Supabase (dashboard SQL Editor)

Esegui contenuto di `supabase/migration_v25_gate_open_queue.sql`. Crea:
- Tabella `gate_open_queue` + 4 indici
- 2 policy RLS (select+insert per authenticated)
- Trigger `gate_open_audit` (popola `audit_log` automatic)
- Function `gate_open_audit_trigger()`

Verifica:
```sql
SELECT COUNT(*) FROM gate_open_queue;
-- expected: 0
\d gate_open_queue
-- expected: 13 columns + 1 UNIQUE constraint
```

### 2. Deploy agente Python aggiornato su srvxatlas

```powershell
# Su srvxatlas (RDP o tramite tu admin remoto via Tailscale)
cd C:\zucchetti_agent
# Backup vecchio
copy zucchetti_agent.py zucchetti_agent.py.bak_2026-06-06
# Sostituisci con nuovo file (copy da workstation)
# Riavvia service
sc.exe stop ZucchettiAgent
sc.exe start ZucchettiAgent
sc.exe query ZucchettiAgent | findstr STATE
# expected: STATE: 4 RUNNING
```

Verifica log:
```powershell
Get-Content -Tail 30 logs\agent.log
# Cerca: "Zucchetti Bridge Agent avviato (v1.6.0-gate-open)"
```

### 3. Deploy admin

Push admin/index.html aggiornato. Il banner deve mostrare:
`build 2026-06-06 · gate-open + voice`

---

## Test in lab (Lunedì 9/6 mattina)

### Test 1: bottone manuale (canary)

1. Apri admin, vai tab "Ospiti Attesi"
2. Verifica presenza Gate Bar in cima (sfondo azzurro)
3. Click **🚪 IN al volo** → tornello TORNELLO_IN deve aprirsi in 1-2 sec
4. Verifica toast "✓ Tornello aperto — INGRESSO"
5. Verifica row in `gate_open_queue` con status='opened'
6. Verifica row in `audit_log` con action='gate_open_request' + action='gate_open_success'

### Test 2: bottone per ospite specifico

1. Crea un guest test (Mario Rossi)
2. Vai tab "Ospiti Attesi", riga Mario Rossi
3. Click **🚪 IN** nella riga
4. Tornello apre + toast "✓ Tornello aperto — INGRESSO" + nome
5. Verifica `visitor_movements` ha riga con direction='IN', source='manual_gate_open:TORNELLO_IN'
6. Verifica `visitors.entry_time` aggiornato a NOW

### Test 3: voice mode (browser Chrome/Edge)

1. Click **🎤 Voce** nel Gate Bar
2. Accetta permesso microfono
3. Status: "🎤 In ascolto..."
4. Dì: *"Apri Rossi"* chiaramente
5. Verifica trascrizione live: "💬 Sento: Apri Rossi (XX%)"
6. Match → fire automatico → toast "✓ Mario Rossi → INGRESSO"
7. Test casi:
   - *"Apri Mario Rossi"* (nome+cognome) → ok
   - *"Esci Rossi"* → uscita
   - *"Apri xxx"* (cognome inesistente) → toast "Non trovo xxx"
   - *"Apri Rossi"* con 2 Rossi → modal disambigua (prompt)

### Test 4: multi-operatore

1. Apri admin da 2 browser diversi (o 2 PC)
2. Login con 2 operatori
3. Click contemporaneo "🚪 IN" su DIVERSI ospiti
4. Verifica entrambi processati
5. Click contemporaneo sullo STESSO ospite (race) → 1 fired, 1 fallisce silenzioso (constraint UNIQUE idempotency_key)

### Test 5: failure recovery

1. Stop agente (`sc.exe stop ZucchettiAgent`)
2. Click "🚪 IN" → riga pending in queue, btn resta giallo
3. UI timeout dopo 12s → btn diventa rosso "timeout"
4. Riavvia agente → row viene processata, ma UI ha già dato up
5. Manual recovery: ricliccare il bottone

---

## Operativa eventi 9-11 giugno

### Setup desk (mattina evento)

1. Aprire admin su PC desk
2. Login come operatore
3. Andare tab "Ospiti Attesi"
4. Verificare Gate Bar visibile + bottoni in ogni riga
5. **Opzionale**: attivare 🎤 Voce (se microfono buono e ambiente non rumoroso)

### Procedura standard per ospite

**Con bottone (manuale)**:
1. Ospite arriva
2. Operatore cerca nella lista (auto-sort cognome) o usa search 🔍
3. Verifica documento mostrato dall'ospite
4. Click **🚪 IN** sulla riga dell'ospite
5. Tornello apre (~1 sec)
6. Ospite passa (può tenere il badge con sé per uso futuro/uscita)

**Con voce**:
1. 🎤 Voce attivata, status "In ascolto"
2. Ospite arriva, dice il proprio nome
3. Operatore dice: *"Apri Rossi"* (o *"Apri Mario Rossi"* se ambiguità)
4. Sistema mostra: "Sento: Apri Rossi" → "Mario Rossi → IN"
5. Tornello apre

### Uscita ospite

- Tab "Visitatori" → ospite con stato "Dentro"
- Click **🚪 OUT** nella riga
- (oppure voice: *"Esci Rossi"*)

### Walk-in al volo (fornitore non in lista, emergenza)

- Gate Bar → **🚪 IN al volo**
- Conferma popup
- Tornello apre
- (registrato in audit_log come walk-in al volo + operatore)

---

## Troubleshooting

### Bottone resta giallo per 12 sec → rosso

**Causa**: agente offline o telnet 8189 down.
**Fix**:
```powershell
sc.exe query ZucchettiAgent
# Se non RUNNING: sc.exe start ZucchettiAgent

# Test telnet manuale
Test-NetConnection localhost -Port 8189
# expected: TcpTestSucceeded: True
```

### Voice mode non parte → "Permesso microfono negato"

**Causa**: browser non ha permesso microfono.
**Fix**: Chrome → impostazioni → privacy → microfono → autorizza il dominio admin.

### Voice mode parte ma non capisce niente

**Possibili cause**:
1. **Rumore tornello/motore alto** → considerare microfono USB direzionale (Logitech €30)
2. **Operatore parla troppo veloce** → scandire chiaramente "A-pri Ros-si"
3. **Accento forte** → fallback: usa bottoni manuali (sempre disponibili)

### Falsi positivi vocali

**Sintomo**: tornello apre senza che l'operatore abbia parlato.
**Causa**: confidence sotto 0.55 viene ignorato; ma se passa il filtro, può capitare.
**Mitigazione**:
- Disattivare voice mode in pause/silenzio
- Aumentare confidence threshold (edit `_voiceProcessCommand` linea `if (confidence >= 0.55)` → portare a 0.7)

### Doppi click → doppia apertura?

**No**. Idempotency key UNIQUE in DB. Riclick prima della risposta = 409 conflict ignorato silenzioso. Riclick DOPO risposta = nuovo idempotency key = nuova riga = nuova apertura (corretto).

---

## Audit + Compliance

Ogni apertura genera **2 righe in `audit_log`**:
1. `gate_open_request` (al click) — operatore, gate, direction, visitor associato
2. `gate_open_success` o `gate_open_failed` (al completamento) — latency_ms, agent_response

Query verifica audit:
```sql
SELECT user_email, action, details->>'gate_name' AS gate, details->>'direction' AS dir,
       details->>'latency_ms' AS lat, created_at
FROM audit_log
WHERE action LIKE 'gate_open%'
  AND created_at > NOW() - INTERVAL '1 day'
ORDER BY created_at DESC;
```

GDPR: nessun dato biometrico audio salvato. La voce è transient nel browser (Web Speech API non invia audio a server Anthropic/Google in modalità continuous — il riconoscimento è on-device su Chrome desktop).

---

## Limiti noti

1. **Non sostituisce sync XAtlas**: i tornelli aperti non registrano transito su AXS_DB Zucchetti. Workaround: noi salviamo movimento in Supabase `visitor_movements` (source='manual_gate_open').
2. **Voce richiede Chrome/Edge**: Safari/Firefox no Web Speech API stabile.
3. **Latenza 300-800ms**: dipende da carico FMC + telnet. Su WSM degradato può essere 1-2s.
4. **Microfono ambiente rumoroso**: confidence cala, falsi positivi possibili. Usare push-to-talk se serve (TODO futuro: tasto Space).

---

## Rollback emergency

Se il sistema malfunziona durante evento:

```sql
-- 1. Disabilita temporaneamente la coda (impedisce nuove insert)
ALTER TABLE gate_open_queue ADD CONSTRAINT temp_disabled CHECK (false) NOT VALID;
```

UI continua a mostrare i bottoni ma POST fallisce 400. Operatore torna a XAtlas console manuale (05-045 / 05-065).

Re-enable:
```sql
ALTER TABLE gate_open_queue DROP CONSTRAINT temp_disabled;
```

---

## File toccati in questa feature

- `supabase/schema.sql` (+aggiunta sezione v25)
- `supabase/migration_v25_gate_open_queue.sql` (NEW)
- `zucchetti_agent.py` (v1.6.0: send_fmc_command, process_gate_open_queue, run_loop split)
- `admin/index.html` (CSS gate buttons + JS triggerGateOpen + voice mode + Gate Bar + buttons in tables)
- `docs/Gate_Open_System.md` (questo file)
