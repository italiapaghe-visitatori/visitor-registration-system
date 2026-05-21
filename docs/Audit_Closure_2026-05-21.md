# Audit Closure — 2026-05-21

**Scope:** verifica che non ci siano findings di audit pendenti dai cicli precedenti, non già coperti dal piano di hardening post-MD.

## Audit pregressi

### Audit 2026-05-09 (pre-evento originale Call Reference)

**Status: CHIUSO.** Riferimento: `project_audit_20260509_pre_evento_15maggio.md` (memoria privata).

- 4 agenti specializzati → 14 issue identificati.
- **12 fix applicati** in 5 batch (commit `a1576d2`, `a84f6aa`, `33f710f`, `781c3b5`). Build finale `2026-05-10g · all-fixes`.
- **3 skip motivati** (non bug ma trade-off consapevoli):
  - RLS strict guest_list — la anon-key è pubblica per design JAMstack del kiosk, stringere romperebbe il flusso.
  - UNIQUE constraint user_identifier su AXS_DB — schema proprietario Zucchetti, alterarlo è rischioso. L'idempotenza nell'agente copre il caso pratico.
  - Drag-drop listener leak — audit aveva overstimato il problema, listener su elementi dinamici sono GC-ed dal browser.

Nessun residuo.

### Audit 2026-05-14 (vigilia evento MD)

**Status: CHIUSO.** Riferimento: commit `7877e1c` ("Pre-evento MD: 3 fix conservativi").

3 fix conservativi applicati prima dell'evento del 15/05:
1. Commit migration v22+v23 (anti-duplicato firme + RLS anon SELECT visitors) come backup DR.
2. Frontend kiosk: aggiunto `handoff_requested_at` al SELECT `guest_list`.
3. Frontend kiosk: null guard su `g.last_name` / `g.first_name` (3 occorrenze).
4. `.gitignore` cleanup.

Le altre raccomandazioni del audit pre-15/05 (3 agenti durante il brainstorming pre-evento) erano "conservative wins" sicure da non applicare durante l'evento. Quelle che sono diventate critiche dopo l'incidente sono ora coperte da B1/A1/B2/B3/C1/D del piano hardening 2026-05-21.

### Findings emersi durante e dopo l'incidente 15/05/2026

**Tutti coperti dal piano hardening post-MD.** Mapping:

| Finding (15/05) | Sotto-progetto piano | Status (2026-05-21) |
|---|---|---|
| Validità XAtlas legata a creazione+1gg (causa "scaduta") | **B1** | ✅ DEPLOYATO |
| Vista `app_users` esposta (Supabase advisor) | **A1** | ✅ DEPLOYATO |
| Timezone +2h nelle timbrature `visitor_movements` | **B2** | 🔲 In piano (bundle B3+B2) |
| Mis-aggancio QR generico (firma su slot sbagliato) | **C1** | 🔲 In piano |
| Mancanza funzione ufficiale di re-propagazione validità | **B3** | 🔲 In piano (bundle B3+B2) |
| Casi dati `759039` (Siciliano↔Romano Elisa) + `238623` (D'Alonzo) | **A3** | 🔲 In piano |
| Reti di sicurezza pre-evento + runbook incidenti | **D** | ✅ PUSHATO (attesa merge) |
| Esecuzione comando consolle distruttivo `05-205` durante evento live | runbook D | ✅ Documentato come "MAI" |
| `tzdata` mancante su srvxatlas (incident hotfix 21/05) | requirements.txt + .bat | ✅ DEPLOYATO |

## Conclusione A2

**Nessun audit finding residuo non indirizzato.** Tutti i cicli di audit chiusi o coperti. Il piano hardening attivo è completo rispetto agli audit pregressi.

Eventuali nuove issue emergeranno da:
- Esecuzione canary pre-evento di giugno con `scripts/pre_event_check.py`
- Esperienza operativa al prossimo evento
- Nuovi alert Supabase advisor o GitHub Dependabot

Quelle saranno catturate in un audit futuro a sé.
