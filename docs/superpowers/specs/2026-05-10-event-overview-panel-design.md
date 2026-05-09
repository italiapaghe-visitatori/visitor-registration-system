# Spec: Pannello "Panoramica Visitatori Evento" globale

**Data**: 2026-05-10
**Stato**: approvato dall'utente — pronto per implementazione
**Scope**: visitor-registration-system, file `admin/index.html`

## Context (problema risolto)

L'utente ha riportato ripetutamente la sensazione di "blocchi invertiti" nel layout dell'admin. Dopo brainstorming guidato (skill `superpowers:brainstorming` + visual companion con mockup side-by-side), il problema reale emerso è:

- L'utente vuole avere SEMPRE sotto mano la tabella dei visitatori dell'evento attivo come "panoramica live" — anche quando si trova in tab che non sono Visitatori (es. Acquisizione, Pre-assegnazione, Audit, Eventi, Ospiti Attesi).
- Il design attuale "ogni tab solo con il suo contenuto" lo costringe a saltare avanti e indietro con la tab Visitatori per vedere chi è dentro/fuori, badge attivi, ecc.

I tentativi precedenti di "fixare un bug di view sovrapposte" (CSS `!important`, MutationObserver, safety check in switchView) avevano risolto correttamente lo stato DOM (verificato con diagnostica console: `Active count: 1` quando si cambia tab). Quindi la "view-visitors visibile sotto le altre tab" che l'utente vedeva nei suoi screenshot era effettivamente un bug nella versione PRIMA del fix `!important`. Adesso il bug DOM non c'è più, ma l'utente VUOLE quella struttura come **feature intenzionale**.

## Outcome desiderato

Sotto la view di una tab attiva (per le 5 tab non-Visitatori), aggiungere un pannello dedicato "👥 Panoramica Visitatori — <nome evento>" che mostra una tabella sintetica dei visitatori dell'evento attivo. Il pannello è:

- **Sempre visibile** in 5/6 tab (tutte tranne Visitatori dove sarebbe duplicazione)
- **Collassabile** con bottone "▼ Riduci"
- **Auto-aggiornato** ogni 10s con polling silenzioso
- **Header sticky** mentre si scorre la tabella
- **Non interferisce** con i filtri della tab Visitatori dedicata (sono dataset separati: il pannello mostra solo evento attivo, la tab Visitatori è completa)

## Architettura

### DOM (singolo elemento condiviso)

Posizione: dentro `.container`, **dopo** tutti i `<div class="view">`.

```html
<div id="event-overview-panel" data-collapsed="false">
  <header class="eop-header">
    <span class="eop-title">👥 Panoramica Visitatori — <strong id="eop-event-name">—</strong></span>
    <span class="eop-stats">
      <span id="eop-stat-total">0</span> totali ·
      <span id="eop-stat-inside">0</span> dentro ·
      <span id="eop-stat-waiting">0</span> attesi
    </span>
    <button id="eop-toggle" type="button">▼ Riduci</button>
  </header>
  <div class="eop-table-wrap">
    <table>
      <thead>
        <tr>
          <th>Visitatore</th>
          <th>Azienda</th>
          <th>📄 Documento</th>
          <th>Tipo</th>
          <th>Badge</th>
        </tr>
      </thead>
      <tbody id="eop-table-body"></tbody>
    </table>
  </div>
</div>
```

5 colonne (vs 10 della tab Visitatori dedicata): visitatore, azienda, documento, tipo, badge. Volutamente compatte — è una panoramica, non l'editor pieno.

### CSS visibility

```css
/* Pannello visibile in tutte le tab tranne Visitatori (dove sarebbe duplicazione)
   e tranne quando non c'è un evento attivo (niente da mostrare). */
#event-overview-panel { display: none; }
body[data-view]:not([data-view="visitors"]):not([data-view="login"]) #event-overview-panel.has-event {
  display: block;
}
/* Collapsed: nasconde solo la tabella, header resta visibile */
#event-overview-panel[data-collapsed="true"] .eop-table-wrap { display: none; }
```

### JS

`switchView(v)` setta `document.body.dataset.view = v` come effetto collaterale. Il CSS reagisce automaticamente.

`loadEventOverview()`:
- Verifica che esista `activeEvent` (variabile globale già esistente)
- Se sì: aggiunge class `has-event` al pannello + popola titolo + query `visitors?event_id=eq.X&xatlas_status=in.(pending,active)&select=*&order=last_name.asc.nullslast&limit=200`
- Se no: rimuove `has-event` (CSS lo nasconde)

`renderEventOverview(rows)`:
- Pulisce tbody
- Renderizza ogni riga con stesso pattern di `renderTable()` esistente, MA in versione 5-colonne
- Aggiorna stat counters (totale / dentro / attesi)

`startEventOverviewPolling()` e `stopEventOverviewPolling()`:
- setInterval 10s (uguale al polling esistente di view-visitors)
- Skippa se `document.visibilityState === 'hidden'` (tab in background)
- Skippa se `currentView === 'visitors'` (lì c'è già la sua tabella)

Toggle "▼ Riduci" salva preferenza in `localStorage.setItem('eop_collapsed', '1')` per persistenza.

### Funzioni esistenti riusate

- `activeEvent` (var globale già popolata da `refreshActiveEventBanner`) — sorgente per filtro evento attivo
- `api()` — wrapper Supabase fetch
- `esc()` — escaping HTML
- Classi CSS `.gtype`, `.xstatus-active`, `.xstatus-pending`, `.empty-dash` già definite — riusate nelle celle

### Integrazioni con flussi esistenti

- Nessun cambio a `loadData()` (tab Visitatori dedicata) — pannello è separato
- Nessun cambio all'agente Python
- Nessuna nuova migration SQL — usa la tabella `visitors` esistente
- Audit log: niente di nuovo (è solo lettura, non scrive)

## Edge cases

| Caso | Comportamento |
|---|---|
| Niente evento attivo | Pannello nascosto totalmente (no `has-event` class) |
| Evento attivo ma 0 visitatori | Pannello visibile con messaggio "Nessun visitatore registrato" |
| Pannello collassato + cambio tab | Resta collassato (preferenza in localStorage) |
| Tab Visitatori | Pannello SEMPRE nascosto (il dato è già nella view-visitors stessa) |
| Tab login (utente non autenticato) | Pannello nascosto |
| Polling fallisce (rete giù) | Mantiene ultimi dati visibili, niente errore intrusivo |

## File da modificare

Solo uno: `admin/index.html`
- Markup pannello prima della chiusura di `.container`
- Blocco CSS dedicato
- Funzioni JS: `loadEventOverview`, `renderEventOverview`, `startEventOverviewPolling`, `stopEventOverviewPolling`, integrazione `switchView` (`body.dataset.view`)
- Hook `eop-toggle` button + persistenza localStorage

## Verifica end-to-end

1. Aprire admin in tab Visitatori → pannello NON visibile sotto
2. Cliccare tab Acquisizione → pannello visibile in fondo con tabella visitatori evento
3. Cliccare tab Audit → stesso pannello visibile
4. Cliccare ▼ Riduci → tabella sparisce, header rimane
5. Cambiare tab → resta collassato (preferenza salvata)
6. Click su Riprendi → si riapre
7. Aggiungere un visitor in tab Visitatori → entro 10s appare anche nella panoramica delle altre tab
8. Cambiare evento attivo → pannello mostra il nuovo evento
9. Concludere evento attivo → pannello scompare (no evento)

## Stima effort

| Componente | Effort |
|---|---|
| Markup pannello + CSS toggle visibility per tab | 1h |
| `loadEventOverview` + `renderEventOverview` (riuso renderTable patterns) | 1h |
| Polling 10s + integrazione switchView (data-view attribute) | 30min |
| Toggle ▼ Riduci + persistenza localStorage | 20min |
| Test 5 tab + edge cases (no evento attivo, no auth) | 45min |
| Commit + deploy + smoke test live | 25min |
| **TOTALE** | **~4h** |

## Spec Self-Review

- ✅ **Placeholder scan**: nessun TBD/TODO non risolto
- ✅ **Internal consistency**: DOM/CSS/JS/edge cases coerenti tra loro
- ✅ **Scope check**: focalizzato su 1 feature ben delimitata, no feature creep
- ✅ **Ambiguity check**: ogni edge case definito con comportamento esplicito (collassato vs nascosto, no evento → nascosto, ecc.)

## Riferimenti correlati

- Sessione 2026-05-09 (`project_session_2026-05-09.md`): bug UX scroll/layout tab, ora chiaramente identificato come "richiesta feature" non bug
- Sessione 2026-05-10 (`project_session_2026-05-10.md`): tab Acquisizione + lettore HDWR HD-RD80
- Build attuale live: `2026-05-10b · view-isolation` (commit `2666a32`) — questo design la sostituirà
