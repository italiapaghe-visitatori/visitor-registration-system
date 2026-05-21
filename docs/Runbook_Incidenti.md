# Runbook Incidenti — Sistema controllo accessi visitatori

**Audience:** Operatrici desk, tecnico responsabile (Antonio).
**Versione:** 1.0 — 2026-05-21 (post-incidente MD 15/05).
**Quando consultarlo:** durante o appena prima di un evento, **se qualcosa non va**.

---

## ⛔ Cose da NON fare MAI durante un evento live

Queste azioni hanno causato l'incidente del 15/05/2026 o sono ad alto rischio. **Mai durante un evento attivo:**

1. **Mai eseguire `05-205 Reinvio tabelle`** dalla consolle Zucchetti WSM/XAtlas su un controller dei tornelli. Questo comando svuota completamente il database locale del tornello (`CANCELLAZIONE COMPLETA DATABASE`) e il tornello smette di riconoscere chiunque finché non viene ricaricato. Il 15/05/2026 ha causato 30+ minuti di panico. **Solo a impianto scarico** con tecnico Zucchetti in supporto.

2. **Mai modificare la fascia oraria `VISITATORI-CORSISTI` (time_period 244)** durante un evento — la modifica non si propaga ai tornelli in tempo reale e può lasciare il sistema in uno stato incoerente.

3. **Mai eseguire `UPDATE` diretti su AXS_DB** aspettandosi che si propaghino ai tornelli. La sincronizzazione NET9x sui controller avviene **solo da chiamate API XAtlas (create/assign)**, non da SQL diretto.

4. **Mai cancellare un visitor in Supabase** mentre è ancora `xatlas_status='active'`. La sequenza corretta è "Concludi visita" → status `checked_out` → l'agente libera il badge → poi (se serve) elimina.

5. **Mai forzare `git push origin master --force`** o fare rebase su master. Il `aggiorna_agente.bat` scarica da `master` e una corruzione di master rompe l'agente in produzione.

---

## ⚠️ Cose da fare PRIMA di ogni evento

### T-72 ore (3 giorni prima)
- [ ] Verifica che la lista ospiti sia importata in Supabase (`guest_list` con event_id corretto).
- [ ] Pre-assegnazione badge (admin → tab Pre-assegnazione → assegna badge dal pool).
- [ ] Invio QR personali (tab Ospiti Attesi → "📧 Invia QR a tutti").
- [ ] Verifica pool badge fisici: numero corretto, sono nella scatola, etichette stampate.

### T-24 ore (1 giorno prima)
- [ ] **Lanciare `python scripts/pre_event_check.py --event-id <UUID>` su srvxatlas**.
- [ ] Verdetto STOP → risolvere e ripetere. Verdetto GO o WARN → procedere.
- [ ] Verifica heartbeat agente: admin → header "Agente" pill verde + heartbeat < 60s.
- [ ] Controllo 3 badge spare fisicamente presenti al desk.

### T-2 ore (2 ore prima)
- [ ] Rilanciare `pre_event_check.py` per ultima conferma.
- [ ] Hard refresh (Ctrl+Shift+R) dei tablet operatrici.
- [ ] Test 1 badge fisico (canary) al tornello → entrata + uscita → display mostra nome + apre.

### T-15 minuti (apertura desk)
- [ ] Apertura evento se non già attivo (tab Eventi → Avvia).
- [ ] Hard refresh ultima volta tablet.
- [ ] Operatrici in posizione, posta scatola badge fisici al desk.

---

## 🚨 Procedure incidenti — Cosa fare se...

### "Tutti i badge visitatori dicono TESSERA SCADUTA"

**Sintomo:** ogni badge VIS al tornello dà denied result=95 ("scaduta"). Dipendenti continuano a passare normali.

**Causa probabile:** validità utenti XAtlas scaduta (bug fix B1 dovrebbe averlo eliminato, ma se ricapita per qualche edge case).

**Procedura (in ordine, fermati al primo che risolve):**

1. **Subito:** abbassa fisicamente il tornello (manuale) → fai entrare gli ospiti. Chiedi alle operatrici di **comunque passare il badge** al lettore (la timbratura si registra anche se denied: result=95 è loggato).

2. **Diagnosi rapida** (read-only, 30 secondi):
   ```bash
   ssh srvxatlas "psql -U postgres -d AXS_DB -c \"SELECT identifier, validity_start::date, validity_end::date FROM external_user WHERE identifier LIKE 'VIS%' ORDER BY validity_end LIMIT 5;\""
   ```
   Se `validity_end < oggi` per tutti i VIS → confermato bug validità.

3. **Fix tramite agente (canale ufficiale, propaga via NET9x):**
   Lancia in Supabase SQL Editor:
   ```sql
   UPDATE visitors
      SET xatlas_renamed = false
    WHERE event_id = '<UUID-EVENTO>'
      AND xatlas_status = 'active'
      AND xatlas_user_id IS NOT NULL
      AND lower(first_name) <> 'pool'
      AND first_name IS NOT NULL AND last_name IS NOT NULL AND badge_number IS NOT NULL;
   ```
   L'agente, al prossimo ciclo, ricreerà gli utenti VIS via API XAtlas (5/ciclo, ~10-15 min per 100 ospiti). NET9x propagherà ai tornelli.

4. **Verifica progressi:**
   ```bash
   ssh srvxatlas "psql -U postgres -d AXS_DB -c \"SELECT count(*) FROM external_user WHERE identifier LIKE 'VIS%' AND validity_start::date = current_date;\""
   ```
   Dovrebbe crescere progressivamente verso il totale.

5. **Test canary:** quando ~10 sono ricreati, prova 1 badge al tornello. Se passa → continua a aspettare il batch. Se ancora "scaduta" → chiamare Antonio.

6. **DA NON FARE:** mai `05-205 Reinvio tabelle` (vedi sezione cose da non fare).

### "Tornello rosso lampeggiante / CONFIGURAZIONE NECESSARIA"

**Sintomo:** spia rossa sul tornello, su WSM evento `RIENTRO CONFIGURAZIONE NECESSARIA`.

**Causa:** comando consolle Zucchetti distruttivo già eseguito (es. `05-205`). Il controller ha svuotato il DB locale.

**Procedura:**

1. **Subito:** tieni tornello abbassato. Nessuno entra al badge, solo manuale.
2. **Non lanciare altri comandi consolle.** Ogni comando aggiuntivo può aggravare.
3. **Chiamare assistenza Zucchetti / integratore.** È loro lavoro riallineare il controller propriamente.
4. **In attesa:** il sistema gestisce manualmente per il resto dell'evento. Tutti i passaggi badge vengono comunque registrati nel log (anche denied).

### "Agente Python fermo (pill rossa)"

**Sintomo:** admin → header pill "Agente" rossa, ultimo heartbeat > 60s.

**Procedura:**

1. **SSH a srvxatlas:**
   ```bash
   ssh srvxatlas "sc.exe query ZucchettiAgent"
   ```
   Se `STATO: STOPPED` → servizio fermo.

2. **Restart:**
   ```bash
   ssh srvxatlas "sc.exe start ZucchettiAgent"
   ```
   Attendi 8-10 secondi e ripeti `sc.exe query` → deve essere `RUNNING`.

3. **Se non parte:**
   - Probabile errore modulo Python (es. `tzdata` post-fix B1).
   - Lancia `cmd /c "cd C:\zucchetti-agent && aggiorna_agente.bat"` → fa pip install requirements + restart.
   - Se ancora non parte: ssh srvxatlas e leggi gli errori Python (`python C:\zucchetti-agent\zucchetti_agent.py debug` per output verbose).

4. **Mentre l'agente è fermo:** i tornelli **continuano a funzionare per gli utenti già provisionati**. Solo le nuove pre-attivazioni/timbrature non vengono processate. Niente disastro immediato.

### "Visitor mismatch (la sua firma è sullo slot di un altro)"

**Sintomo:** visitor mostra nome/email errati, oppure non compare in "da firmare" anche se sai che non ha firmato.

**Pattern noto:** QR generico → ospite seleziona/scrive nome sbagliato dalla lista → la sua firma viene agganciata a un altro guest_id.

**Procedura:**

1. **Identifica i due record** in Supabase:
   - quello con la firma ma con nome storpiato (es. `SIMONE TPOLVERINO` su slot `4adb1484` di TREVISONE)
   - quello con il nome giusto ma senza firma (es. POLVERINO own stub)

2. **Lancia il blocco SQL di swap** (vedi memoria `project_session_2026-05-15.md` sezione mismatch — pattern stessa procedura ripetuta per POLVERINO/TREVISONE, FRANCO/LUCIANI):
   ```sql
   -- Copia firma+consensi dal record sbagliato a quello giusto, poi resetta il sbagliato
   -- Vedi project_session_2026-05-15 per template completo
   ```

3. **Verifica:** dopo lo swap, in `visitors`:
   - record stub vero del visitor con firma = SI
   - record sullo slot sbagliato resettato (firma = NULL, nome corretto del proprietario slot)

---

## 📞 Escalation — chi chiamare

- **Antonio Gelormini** — `tecnico.gelormini@gmail.com` — fix tecnici sistema (Supabase, agente, admin).
- **Assistenza Zucchetti / integratore** — incidenti consolle WSM / controller tornelli (es. dopo `05-205`, rosso lampeggiante).
- **Per problemi dei badge fisici** (chip rotti, perso) → gestione operativa al desk con badge spare.

---

## 🧰 Comandi utili (cheat sheet)

| Cosa | Comando |
|---|---|
| Stato servizio agente | `ssh srvxatlas "sc.exe query ZucchettiAgent"` |
| Restart agente | `ssh srvxatlas "sc.exe stop ZucchettiAgent"` poi `sc.exe start` |
| Aggiornare agente da GitHub | `ssh srvxatlas 'cmd /c "cd C:\zucchetti-agent && aggiorna_agente.bat"'` |
| Check pre-evento | `ssh srvxatlas "python C:\zucchetti-agent\pre_event_check.py --event-id <UUID>"` (richiede deploy script su server) |
| Forzare recreate VIS visitor | `UPDATE visitors SET xatlas_renamed=false WHERE id='...';` |
| Snapshot dipendenti AXS | `ssh srvxatlas "psql -U postgres -d AXS_DB -c 'SELECT count(*), md5(string_agg(id::text, '','' ORDER BY id)) FROM internal_user;'"` |

---

## 📚 Riferimenti

- **Incidente 15/05/2026:** [`project_session_2026-05-15`](../../.claude/projects/c--Users-GaInformatica-Documents-Progetti-OpenCode-visitor-registration-system/memory/project_session_2026-05-15.md) (memoria privata)
- **TODO hardening post-MD:** [`project_todo_fix_agente_post_md`](../../.claude/projects/c--Users-GaInformatica-Documents-Progetti-OpenCode-visitor-registration-system/memory/project_todo_fix_agente_post_md.md)
- **Spec fix validità (B1):** [`docs/superpowers/specs/2026-05-18-fix-validita-evento-design.md`](superpowers/specs/2026-05-18-fix-validita-evento-design.md)
