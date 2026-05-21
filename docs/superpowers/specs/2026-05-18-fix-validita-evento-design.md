# B1 — Fix validità utente XAtlas legata alla data evento

**Data:** 2026-05-18  
**Stato:** Design da approvare  
**Autore:** Sessione brainstorming + 3 agenti specializzati (architettura, adversarial, test/deploy)  
**Riferimento incidente:** [project_session_2026-05-15](../../../../.claude/projects/c--Users-GaInformatica-Documents-Progetti-OpenCode-visitor-registration-system/memory/project_session_2026-05-15.md)  
**Obiettivo evento:** 1ª settimana giugno 2026, fino a 100 ospiti

---

## Sintesi per utente non tecnico

**Cosa risolve:** il bug del 15/05 (badge "tessera scaduta" all'arrivo). Oggi l'agente assegna ai badge una validità di un solo giorno → se prepari i badge anche solo 2 giorni prima dell'evento, scadono prima.

**Cosa cambia (in italiano normale):** d'ora in avanti la validità del badge sarà legata alla **data dell'evento**, non al giorno in cui lo prepari. Concretamente: dal momento in cui creo l'utente fino a **7 giorni dopo la fine dell'evento**. Margine generoso, copre uscite tardive, riconciliazioni, dimenticanze. Quando l'evento si chiude correttamente, l'utente viene comunque cancellato (come oggi), quindi il margine lungo non lascia in giro permessi inutili.

**Garanzie:**
- **Dipendenti zero impatto** — il codice agente lavora solo nel namespace `VIS{badge}`, mai dipendenti. Lo blindo con un'asserzione esplicita.
- **Badge degli ospiti**: funzionano dall'arrivo all'uscita, sempre. Il disastro del 15/05 strutturalmente non può ripetersi.
- **Walk-in fuori da evento**: continuano a funzionare come oggi.
- **Eventi già chiusi**: l'agente si rifiuta esplicitamente di provisionare.

**Cosa NON cambia:** frontend, database Supabase (zero migration), tornelli, consolle Zucchetti. Solo il codice Python dell'agente.

---

## Problema (causa del 15/05)

Il file `zucchetti_agent.py` contiene la funzione `_today_ms()` (righe 303-309) che restituisce la finestra `(oggi 00:00, oggi 23:59:59)` in millisecondi epoch. Questa finestra viene applicata come `validityStart/validityEnd` a ogni nuovo utente XAtlas creato (riga 545 dentro `create_xatlas_user`).

**Conseguenza:** badge preparato il 13/05 per evento del 15/05 → utente XAtlas con validità 13/05→14/05 23:59 → scaduto la mattina dell'evento → tornello dice "tessera scaduta" → fallimento totale ingressi 15/05.

**Indipendente da:** timezone (validità in ms epoch, ok), NET9x (propagazione corretta), card validity (1900-2100, ok), policy (corrette).

---

## Soluzione: validità legata all'evento

### Formula

Nuova funzione `event_window_ms(event_id: str | None) -> tuple[int, int]`:

```
SE event_id is None:
    -> _today_ms()  # SOLO fallback walk-in legacy (visitor senza evento), invariato

altrimenti (event_id valorizzato):
    event = sb_get(events, id=event_id, select=event_end_date,closed_at)
    
    SE event non trovato:
        raise RuntimeError "event_id <X> non trovato"  # fail-fast (retry al prossimo ciclo)
    
    SE event.closed_at IS NOT NULL:
        raise RuntimeError "evento chiuso, no provisioning"  # fail-fast
    
    today_local   = oggi @ Europe/Rome (data, ore 00:00:00)
    event_end     = event.event_end_date @ Europe/Rome (data, ore 00:00:00)
    
    SE event_end < today_local:
        raise RuntimeError "evento già scaduto (event_end_date nel passato)"  # fail-fast
    
    # Calcolo finale (entrambi i bound a fine giornata 23:59:59 locale)
    validity_start = today_local con ora 00:00:00
    candidate_end  = max(event_end + 7 giorni, today_local + 1 giorno)
    validity_end   = candidate_end con ora 23:59:59
    
    return (epoch_ms(validity_start), epoch_ms(validity_end))
```

**Importante — politica fail-fast unitaria:** ogni anomalia su `event_id` valorizzato (non trovato, chiuso, scaduto) **solleva eccezione**. Il chiamante (`process_pending_badges`/`process_pool_preparation`/`process_pool_walkin_recreate`) la cattura nel suo `try/except` esistente, logga l'errore, e il visitor resta in stato `pending`/`renamed=false` per essere ritentato al ciclo successivo. **Nessun fallback silenzioso** che maschera anomalie e ricrea il 15/05. `_today_ms()` resta utilizzato SOLO quando `event_id is None` (walk-in legacy senza evento, comportamento storicamente corretto).

**Razionale scelte:**
- **Start = today, non event_start**: stiamo creando l'utente *ora*, non possiamo dargli validità nel passato. Se l'evento è fra 5 giorni, l'utente è valido dal momento della creazione (così è testabile pre-evento). Se l'evento è oggi, start = oggi.
- **End = event_end + 7 giorni**: copre uscite tardive, riconciliazioni, eventi che sforano. Il cleanup notturno e la chiusura evento liberano comunque gli utenti checked_out → il margine lungo non è un leak operativo.
- **Clamp `max(..., today+1)`**: se per qualche ragione end risulta nel passato (date errate), garantisce almeno validità di un giorno → fallisce nelle query di provisioning successive (non crea badge scaduti subito).
- **Fail-fast su evento chiuso o passato**: meglio errore esplicito che provisionare badge zombie.

### Timezone esplicito

Tutta la logica usa **`zoneinfo.ZoneInfo("Europe/Rome")`** esplicito — niente `datetime.now()` naive. Se domani il server cambia fuso, il calcolo resta corretto.

### Logging strutturato

Ogni `create_xatlas_user` aggiunge log INFO con:
- `identifier`
- `validity_start_iso` (Europe/Rome)
- `validity_end_iso` (Europe/Rome)
- `event_id` (o "WALK-IN" se None)
- `source_function` (pending / pool_prep / recreate)

Così in caso di anomalia futura, in 30 secondi si ricostruisce cosa è stato scritto.

---

## Modifiche al codice (zucchetti_agent.py)

### 1) Nuova funzione `event_window_ms(event_id)`

Posizione: subito sotto `_today_ms()` (riga 309 attuale). Implementa la formula sopra. ~40 righe.

### 2) Funzione esistente `create_xatlas_user(badge_number, first_name, last_name)` (riga 524)

**Nuova firma:** `create_xatlas_user(badge_number, first_name, last_name, event_id=None)`. Default `None` per backward compatibility.

**Modifica riga 545:** sostituire `start_ms, end_ms = _today_ms()` con `start_ms, end_ms = event_window_ms(event_id)`.

**Nuova asserzione (subito prima del POST /create, ~riga 590):**
```python
assert identifier.startswith("VIS"), f"REFUSED non-VIS identifier: {identifier!r}"
```

Difesa in profondità contro modifiche future.

**Nuovo log INFO** dopo il calcolo `event_window_ms`:
```python
log.info(f"create_xatlas_user: identifier={identifier} validity={start_iso}..{end_iso} event_id={event_id or 'WALK-IN'}")
```

### 3) Aggiornare i 3 call site

#### 3a) `process_pending_badges` (riga 749)
- **Riga 754** (select): aggiungere `event_id` ai campi → `"select": "id,first_name,last_name,badge_number,event_id"`
- **Riga 772** (call): `create_xatlas_user(badge, fn, ln, event_id=v.get("event_id"))`

#### 3b) `process_pool_preparation` (riga 786)
- **Riga 793** (select): già contiene `event_id` ✓ niente da modificare nel SELECT
- **Riga 811** (call): `create_xatlas_user(badge, "Pool", f"Badge{badge}", event_id=p.get("event_id"))`

#### 3c) `process_pool_walkin_recreate` (riga 1126)
- **Riga 1146** (select): aggiungere `event_id` → `"select": "id,first_name,last_name,xatlas_user_id,badge_number,event_id"`
- **Riga 1200** (call): `create_xatlas_user(badge, fn, ln, event_id=v.get("event_id"))`

### 4) Nessun'altra modifica

`_today_ms()` resta invariato (fallback). `midnight_cleanup_stale_visitors`, `cleanup_archived_visitors`, `process_active_transactions`, `record_movement`: non toccati (out-of-scope B1, alcuni nel mirino di B2/B3).

---

## Asserzioni e vincoli di sicurezza

### Dipendenti — non impattabili strutturalmente

1. L'agente legge esclusivamente Supabase `visitors` e `badge_pool`. I dipendenti **non esistono in queste tabelle**. Impossibile leggerli.
2. L'identifier generato è hardcoded `f"VIS{badge_number}"` (riga 547). Asserzione esplicita prima del POST (modifica 2 sopra).
3. `delete_xatlas_user` opera solo su `xatlas_user_id` letto da record visitor → mai un dipendente.
4. AUTH_GROUP_ID = 249 (gruppo VISITATORI, riga 104) — gli utenti creati appartengono solo a quel gruppo.

### Out-of-scope (vincoli espliciti)

Cosa **NON** fa B1 (per evitare scope creep):
- Non rinfresca utenti già esistenti pre-fix (per quelli c'è il flusso recreate, da gestire operativamente).
- Non modifica `record_movement` (timezone timbrature — B2).
- Non crea funzione ufficiale `repropagate_event_validity` (B3).
- Non modifica frontend kiosk (C1 — QR mis-aggancio).
- Non tocca lo schema DB.
- Non interviene sul `closed_at` lifecycle (chiusura evento → bulk checked_out — è una raccomandazione operativa separata).

---

## Test plan (sommario)

Il dettaglio dei test va nel piano di implementazione separato. Sommario:

1. **Unit test locali (pytest, no produzione):** 10 casi su `event_window_ms` (evento futuro, oggi, multi-giorno, passato, chiuso, walk-in None, DST, anno bisestile, fuso forzato UTC, identifier non-VIS rigetto).
2. **Pre-deploy snapshot dipendenti AXS_DB:** hash dei loro `validity_end` PRIMA del deploy, da confrontare DOPO. Differenza → STOP + rollback.
3. **Canary in produzione:** 1 visitor reale (analogo a D'ORTA del 15/05). Verifica `validity_end` in AXS_DB combaci con event_end+7 e badge funzioni al tornello.
4. **Smoke test post-deploy:** primi 5 minuti — log agente senza ERROR, heartbeat verde, canary OK.

---

## Deploy plan (sommario)

Il dettaglio operativo va nel piano di implementazione. Sommario:

1. **Finestra:** feriale 12:30-13:30 oppure 19:00-20:00, **mai** nei 3 giorni precedenti l'evento giugno. Downtime ~15-25 secondi.
2. **Procedura:** branch git separato → commit firmato su master → SSH al server → script esistente `scripts/aggiorna_agente.bat` (fa già stop → backup .bak → download GitHub → start). Service Windows: **`ZucchettiAgent`** (nome reale verificato).
3. **Rollback:** restore del `.bak_YYYYMMDD_HHmm` automatico via script + restart, <20 secondi.
4. **Refresh utenti pre-deploy per evento giugno — usando il MECCANISMO PROVATO IL 15/05:**

   Il 15/05 il salvataggio in extremis è avvenuto attivando il flusso `process_pool_walkin_recreate` già esistente nell'agente: setting `xatlas_renamed=false` sui visitor target → al ciclo successivo l'agente fa `delete_xatlas_user` del vecchio + `create_xatlas_user` del nuovo via API XAtlas → NET9x propaga automaticamente a tutti i controller. **VIS-only, zero impatto dipendenti, no wipe controller, idempotente, reversibile.** È la canale ufficiale di propagazione validità.

   Per il refresh post-deploy si riusa quel meccanismo, con la differenza che l'agente ora gira col CODICE NUOVO → la `create_xatlas_user` userà `event_window_ms(event_id)` invece di `_today_ms()` → utenti ricreati con validità CORRETTA legata all'evento.
   
   Procedura post-deploy per visitor/pool dell'evento giugno già esistenti pre-fix:
   ```sql
   -- Supabase
   UPDATE visitors
     SET xatlas_renamed = false
     WHERE event_id = '<event_id_giugno>'
       AND xatlas_status = 'active'
       AND xatlas_user_id IS NOT NULL
       AND lower(first_name) <> 'pool';
   ```
   Tempo: ~5 sec/badge × N badge ÷ 5 per ciclo (rate-limit). Per 100 badge ≈ 10-15 minuti. L'agente smaltisce in background mentre il sistema continua a funzionare. Verifica post-run: query AXS_DB su `validity_end` dei VIS dell'evento (devono essere `event_end + 7gg`).
   
   In alternativa (se il pool non era ancora stato preparato pre-deploy): basta lasciar girare `process_pool_preparation` sul pool draft del nuovo evento, l'agente li pre-attiva da zero con la validità corretta. Nessun refresh necessario.

5. **Codifica futura del meccanismo (out-of-scope B1, scope B3):** la procedura del punto 4 funziona ma è un "hack ufficioso" (l'UPDATE `xatlas_renamed=false` non è documentato come API). Il sotto-progetto **B3** trasformerà quel flusso in una funzione ufficiale `repropagate_event_validity(event_id)` con logging strutturato e idempotenza esplicita, sostituendo l'UPDATE manuale con una chiamata RPC documentata. **B1 NON deve dipendere da B3 per funzionare** — il punto 4 funziona già con quello che c'è oggi.

---

## Pre-evento GO/NO-GO check (consegna separata, Phase D)

Non è scope B1, ma B1 lo prepara. Sarà uno script `scripts/pre_event_check.py` (Phase D) che T-24h e T-2h prima dell'evento verifica:
- Tutti i VIS dell'evento hanno `validity_end >= event_end_date`?
- Conteggio VIS attivi == conteggio visitors Supabase active?
- Nessun VIS scaduto residuo per l'evento corrente?

Output: `OK` (verde) o `STOP` (rosso, con motivo).

---

## Edge case noti, copertura del design

| Scenario | Probabilità | Gravità | Come B1 lo gestisce |
|---|---|---|---|
| Provisioning prima di mezzanotte | Media | Alta | Coperto da TZ esplicito Europe/Rome |
| Pool pre-creato per evento futuro | **Alta** | **Critica** | **Risolto — è il bug del 15/05** |
| `process_pending_badges` senza event_id | **Alta** | **Critica** | **Risolto — SELECT aggiornato** |
| `process_pool_walkin_recreate` senza event_id | **Alta** | **Critica** | **Risolto — SELECT aggiornato** |
| event_end_date nel passato | Media | Alta | Fail-fast (raise), clamp `max(today+1)` |
| Evento chiuso prematuramente | Media | Media | Fail-fast su `closed_at NOT NULL` |
| Multi-event concorrenti | Bassa | Media | Ognuno usa il suo `event_id`, OK |
| XAtlas API rifiuta validità lunga | Media | Alta | Test pre-deploy POST con 7gg margine |
| Validità +7gg = leak sicurezza | Bassa | Media | Cleanup `checked_out` libera comunque |
| Utenti pre-fix da rinfrescare | Alta (in deploy) | Media | Procedura operativa: regenerate pool giugno |
| event_id NULL su walk-in dentro evento | Media | Alta | Fuori scope B1 — guard server-side futura |
| DST ottobre | Bassa (giugno) | Bassa | Coperto da `ZoneInfo("Europe/Rome")` |
| Race deploy mid-cycle | Bassa | Alta | Restart pulito + idempotenza esistente |
| Tracciabilità post-mortem | Alta | Media | Log INFO strutturato a ogni create |

---

## File e righe interessate

**Modifiche (solo `zucchetti_agent.py`):**
- Nuova funzione `event_window_ms`, dopo riga 309 (~40 righe)
- `create_xatlas_user` (riga 524-651): firma + riga 545 + asserzione + log
- `process_pending_badges` riga 754 (SELECT) + riga 772 (call)
- `process_pool_preparation` riga 811 (call)
- `process_pool_walkin_recreate` riga 1146 (SELECT) + riga 1200 (call)

**Non modificati (per chiarezza):**
- Tutto il frontend (`frontend/`, `admin/`)
- Tutto lo schema DB (`supabase/schema.sql`, edge functions)
- Tutti gli altri file (test, scripts, docs)

**Test (nuovi):**
- `tests/test_validity_window.py` (sarà creato — vedi piano implementazione)

---

## Cosa serve dopo questa spec

1. ✅ Spec scritta (questo documento)
2. **Self-review** (sto per farla)
3. **OK dell'utente** su questo design
4. **Piano di implementazione** dettagliato (file separato, prodotto da skill `writing-plans` su questa spec)
5. Implementazione su branch git separato
6. Test locali verdi
7. Canary in produzione + verifica vs AXS_DB
8. OK utente al deploy finale
9. Deploy in finestra concordata
10. Smoke test post-deploy
11. (Quando arriva l'evento di giugno) check pre-evento GO/NO-GO

---

## Note di responsabilità

- **Carta bianca dell'utente:** approvata, ma applicata con disciplina (spec → plan → test → canary → deploy graduale).
- **"Magia" del 15/05:** era metodo, non magia. Stesso metodo qui: canarino, verifica vs Zucchetti, fermarsi se i dati sono sporchi.
- **Stop condition:** se in qualsiasi punto (test, canary, smoke test) emerge anche un solo dubbio non risolto sulla sicurezza dipendenti o sulla correttezza del fix, **fermarsi e segnalare**, non procedere.
