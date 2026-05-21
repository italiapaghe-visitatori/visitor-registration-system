# A1 — Fix Supabase advisor `auth_users_exposed`

**Data:** 2026-05-21
**Stato:** Design da approvare
**Riferimento:** alert Supabase del 17/05/2026 sul progetto `sebhatzxsxuafsmbdtsx`
**Indipendente da:** B1 (validità XAtlas). Sono mondi separati e i due branch possono essere mergiati in qualsiasi ordine.

---

## Sintesi per utente non tecnico

**Cosa risolve:** l'advisor critico di Supabase che dice "stai esponendo dati degli utenti tramite una vista". Oggi la vista `public.app_users` (usata dal modale admin "Gestione operatori" per mostrare email/last login/status degli operatori) è marcata `security_definer` → bypassa la protezione di Supabase su `auth.users`. Anche se l'accesso è ristretto agli operatori loggati e non agli anonimi, Supabase la flagga giustamente come pattern rischioso.

**Cosa cambia:** la vista viene sostituita da una **funzione SQL** chiamata via RPC. La funzione:
- accetta solo operatori autenticati (rifiuta gli anonimi)
- restituisce **tutti gli utenti** se il chiamante è super-admin
- restituisce **solo se stesso** se è un operatore normale
- niente cambia per il modale Gestione operatori dal punto di vista utente

**Bonus sicurezza:** oggi il filtraggio "non super-admin vede solo se stesso" è fatto dal frontend (bypassabile via API call diretta). Spostandolo nel server diventa **non aggirabile**. Quindi A1 chiude l'advisor Supabase E rafforza la sicurezza reale.

**Cosa NON cambia:** modale Gestione operatori (stessa UI), Edge Functions invite/manage-operator (già service_role), auth flow Supabase, niente di tutto questo.

---

## Problema

`supabase/schema.sql:597-645` definisce:

```sql
CREATE OR REPLACE VIEW public.app_users
WITH (security_invoker = false) AS
SELECT u.id, u.email, ... FROM auth.users u ...;
GRANT SELECT ON public.app_users TO authenticated;
REVOKE ALL ON public.app_users FROM anon;
```

Pattern flaggato da Supabase advisor `auth_users_exposed` come critico (anche se anon è già escluso). Motivo: vista `security_definer` su `auth.users` espone PII a tutti gli `authenticated`, indipendentemente da chi siano.

Consumer unico: `admin/index.html:4098` in `loadOperators()`:

```javascript
const res = await api(`${SUPABASE_URL}/rest/v1/app_users?select=*`);
```

Il frontend poi filtra a `if (!isSuperAdmin) users = users.filter(u => u.id === currentUserId)` (filtraggio UI bypassabile).

## Soluzione

Sostituire la vista con una **funzione RPC** `public.list_app_users()` `SECURITY DEFINER` con:

1. Check `auth.role() = 'authenticated'` (anon refused esplicitamente).
2. Determina caller email via `auth.email()` o `(auth.jwt() ->> 'email')`.
3. Costruisce whitelist super-admin: `tecnico.gelormini@gmail.com` (canonico, da memoria progetto `project_session_2026-05-12`).
4. SE caller_email IN whitelist → ritorna TUTTE le righe di `auth.users` (filtrate sui campi sicuri).
   ALTRIMENTI → ritorna solo la riga del caller (filtra su `id = auth.uid()`).
5. La function restituisce lo stesso schema della vista precedente: id, email, created_at, email_confirmed_at, last_sign_in_at, banned_until, display_name, status. Frontend invariato sul rendering.

Permission:
- `REVOKE ALL ON FUNCTION public.list_app_users() FROM PUBLIC;`
- `GRANT EXECUTE ON FUNCTION public.list_app_users() TO authenticated;`

La vista vecchia viene **droppata** (`DROP VIEW IF EXISTS public.app_users CASCADE`).

Frontend admin: cambia 1 chiamata REST in POST RPC:

```javascript
// PRIMA
const res = await api(`${SUPABASE_URL}/rest/v1/app_users?select=*`);
// DOPO
const res = await api(`${SUPABASE_URL}/rest/v1/rpc/list_app_users`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({}),
});
```

Rimuovo il filtraggio frontend non-super-admin (ora server-side, più sicuro). Aggiorno il messaggio di errore "migration non applicata" alla v24.

---

## Sicurezza dipendenti

A1 **non tocca nessun dato dei dipendenti** né del flusso visitatori/tornelli. Lavora solo sul namespace `auth.users` (utenti operatori del nostro admin). I dipendenti dell'azienda (gestiti da Zucchetti/HR, ed esistenti come `external_user` in AXS_DB) sono in un mondo completamente separato — Supabase non li conosce.

---

## Cosa NON fa A1 (vincoli espliciti)

- Non modifica il codice agente Python.
- Non tocca i tornelli o AXS_DB.
- Non tocca le Edge Function (invite-operator, manage-operator restano service_role).
- Non tocca il modale Gestione operatori a livello di UI (solo la singola chiamata fetch).
- Non aggiunge nuove tabelle o colonne.

---

## File interessati

**Modificati:**
- `supabase/schema.sql` — appende migration v24 (DROP VIEW + CREATE FUNCTION + GRANT)
- `admin/index.html` — modifica `loadOperators()` (~riga 4096-4140): chiamata REST → RPC + rimozione filter frontend + aggiornamento messaggio errore migration

**Creati:**
- `supabase/migration_v24_app_users_function.sql` — copia standalone della migration per disaster recovery / staging clone (segue pattern usato per v22/v23 il 14/05)

**Toccati zero:** tutto il resto (zucchetti_agent.py, frontend kiosk, edge functions, altri script).

---

## Test plan

Niente pytest (è SQL + frontend tiny change). Test in 2 fasi:

### Test SQL (eseguibili in Supabase SQL editor)

Dopo migration applicata, eseguire come blocco di smoke test:

```sql
-- 1) La function esiste
SELECT proname, pg_get_function_arguments(oid) FROM pg_proc
WHERE proname = 'list_app_users';
-- Atteso: 1 riga.

-- 2) La vecchia view NON esiste piu'
SELECT viewname FROM pg_views WHERE viewname = 'app_users';
-- Atteso: 0 righe.

-- 3) Permission anon: rifiutato (eseguito con jwt anon)
-- Eseguibile solo da client con anon key; verificato a mano.

-- 4) Verifica struttura ritornata (deve combaciare col rendering frontend)
SELECT * FROM public.list_app_users() LIMIT 1;
-- Atteso: colonne id, email, created_at, email_confirmed_at, last_sign_in_at,
-- banned_until, display_name, status.

-- 5) Filtraggio server-side:
--    chiamando come super-admin -> N righe (tutti gli operatori)
--    chiamando come operatore normale -> 1 riga (se stesso)
-- Verificato lato admin reale dopo deploy.
```

### Test frontend (smoke a mano via browser)

Dopo deploy della modifica admin:
1. Login come **tecnico.gelormini@gmail.com** (super-admin) → tab Operatori → vede TUTTI gli operatori.
2. Login come **operatore normale** → tab Operatori → vede SOLO se stesso (anche se ispeziona la chiamata di rete, il server non risponde di più).

---

## Deploy plan

Il dettaglio operativo va nel piano. Sommario:

1. **Deploy DB:** utente esegue il contenuto di `supabase/migration_v24_app_users_function.sql` nel SQL Editor di Supabase (blocco idempotente con `CREATE OR REPLACE` e `DROP VIEW IF EXISTS`).
2. **Deploy frontend:** push del branch su master → GitHub Pages auto-deploya in ~1-2 minuti.
3. **Ordine consigliato:** prima la migration SQL (la function diventa disponibile), poi il deploy admin. Tra i due c'è un buco di ~2 minuti in cui un admin che apre Gestione operatori riceverà 404 sulla vista vecchia. Trascurabile (admin di solito non riapre il modale ogni 2 minuti).
4. **Rollback:** `DROP FUNCTION` + ripristino vista vecchia + git revert del frontend. ~5 minuti.

---

## Edge cases noti

| Scenario | Probabilità | Gravità | Gestione |
|---|---|---|---|
| Admin loggato apre Gestione operatori durante il deploy SQL | Bassa | Bassa | 404 transitorio, ricarica risolve |
| `auth.email()` ritorna NULL (es. user senza email) | Bassa | Media | La function rifiuta con eccezione esplicita (preferenza fail-fast) |
| Whitelist hardcoded vs scalabile | Media (operatori cambiano) | Bassa | Soluzione corrente già hardcoded in Edge Functions; coerenza |
| Migration applicata ma frontend non deployato | Media | Bassa | Admin mostra "migration v24 da applicare" (nuovo messaggio) |
| Frontend deployato ma migration non applicata | Media | Media | Admin mostra 404 → utente sa che deve applicare la migration |

---

## Out-of-scope (rinviato a sotto-progetti futuri)

- Whitelist super-admin in tabella dedicata (es. `operator_roles`) invece di hardcoded → ridurre churn quando cambiano i super-admin. Da valutare se in futuro ne servono > 1.
- Audit log delle chiamate a `list_app_users` (chi consulta la lista quando) → minor compliance feature.

---

## Cosa serve dopo questa spec

1. ✅ Spec scritta (questo file)
2. Self-review
3. Plan dettagliato (file separato)
4. Implementazione su branch `feat/a1-supabase-auth-users` (già creato)
5. Test SQL + smoke frontend
6. STOP pre-merge: utente approva → merge in master → migration SQL su Supabase → GitHub Pages auto-deploy
