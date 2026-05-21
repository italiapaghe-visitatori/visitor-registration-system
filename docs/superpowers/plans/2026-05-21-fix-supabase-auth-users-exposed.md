# A1 — Fix Supabase `auth_users_exposed` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sostituire la VIEW `public.app_users` (flaggata dall'advisor Supabase `auth_users_exposed`) con una FUNCTION SECURITY DEFINER `public.list_app_users()` che applica controllo server-side: super-admin vede tutti, operatori normali vedono solo sé.

**Architecture:** Migration v18 in `supabase/schema.sql` (DROP VIEW + CREATE FUNCTION + GRANT) + copia standalone in `supabase/migration_v18_app_users_function.sql` per DR. Modifica minimale a `admin/index.html` nel `loadOperators()`: REST GET → POST RPC + rimozione filter frontend (ora server-side).

**Tech Stack:** PostgreSQL (Supabase), PostgREST RPC, JavaScript admin frontend.

**Riferimento spec:** [`docs/superpowers/specs/2026-05-21-fix-supabase-auth-users-exposed-design.md`](../specs/2026-05-21-fix-supabase-auth-users-exposed-design.md)

**STOP CONDITION:** Il piano si ferma al commit del branch feature `feat/a1-supabase-auth-users` + push su origin. Merge in master, esecuzione della migration sul Supabase di produzione e deploy GitHub Pages richiedono OK esplicito utente.

---

## File Structure

**Modificati:**
- `supabase/schema.sql` — appende blocco migration v18 in fondo
- `admin/index.html` — funzione `loadOperators()` (~riga 4096-4140)

**Creati:**
- `supabase/migration_v18_app_users_function.sql` — copia standalone (pattern usato per v22/v23)

---

## Task 0: Preflight

**Files:** nessuno modificato. Solo verifiche.

- [ ] **Step 1: Verifica branch e working tree**

Run:
```bash
cd "c:/Users/GaInformatica/Documents/Progetti_OpenCode/visitor-registration-system"
git status --short
git branch --show-current
```
Expected: branch `feat/a1-supabase-auth-users`, working tree clean (solo untracked).

- [ ] **Step 2: Verifica posizione current loadOperators() in admin**

Run:
```bash
grep -n "loadOperators\|app_users" admin/index.html | head -20
```
Expected: si trovano le occorrenze di `app_users` intorno a riga 4061-4111 e la chiamata REST a riga 4098. Conferma che il piano sia ancorato alle righe corrette.

- [ ] **Step 3: Verifica la presenza della view nello schema attuale**

Run:
```bash
grep -n "CREATE OR REPLACE VIEW public.app_users\|FROM auth.users" supabase/schema.sql
```
Expected: 2 occorrenze di `CREATE OR REPLACE VIEW public.app_users` (v15 + v16) e 2 occorrenze di `FROM auth.users`. Conferma.

---

## Task 1: Crea migration v18 standalone (file separato per DR)

**Files:**
- Create: `supabase/migration_v18_app_users_function.sql`

- [ ] **Step 1: Crea il file con il blocco SQL completo**

```sql
-- MIGRATION v18 — Fix advisor 'auth_users_exposed': view -> function RPC
-- =====================================================================
-- Applicare nel SQL Editor di Supabase Dashboard.
-- Vedi spec docs/superpowers/specs/2026-05-21-fix-supabase-auth-users-exposed-design.md
--
-- Problema risolto: la view public.app_users (security_definer, GRANT a authenticated)
-- e' flaggata da Supabase advisor come 'auth_users_exposed' perche' bypassa l'RLS
-- di auth.users. Sostituzione con FUNCTION RPC con controllo ruolo server-side.
--
-- Comportamento nuovo:
--  - anon -> EXECUTE rifiutato (no GRANT)
--  - authenticated super-admin (whitelist) -> vede tutti gli operatori
--  - authenticated operatore normale -> vede solo se stesso (filtraggio non aggirabile)
-- ======================================================================

-- 1) Rimuovi vecchia view (idempotente)
DROP VIEW IF EXISTS public.app_users CASCADE;

-- 2) Crea function SECURITY DEFINER
CREATE OR REPLACE FUNCTION public.list_app_users()
RETURNS TABLE (
  id                  uuid,
  email               text,
  created_at          timestamptz,
  email_confirmed_at  timestamptz,
  last_sign_in_at     timestamptz,
  banned_until        timestamptz,
  display_name        text,
  status              text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth
AS $$
DECLARE
  caller_email text;
  is_super_admin boolean;
BEGIN
  -- Rifiuta anon esplicitamente. auth.role() restituisce 'anon' o 'authenticated'.
  IF (SELECT auth.role()) <> 'authenticated' THEN
    RAISE EXCEPTION 'list_app_users: caller non autenticato'
      USING HINT = 'login richiesto';
  END IF;

  -- Email del caller dal JWT
  caller_email := (auth.jwt() ->> 'email');
  IF caller_email IS NULL THEN
    RAISE EXCEPTION 'list_app_users: email caller non disponibile nel JWT';
  END IF;

  -- Whitelist super-admin (allineata con Edge Function invite-operator)
  is_super_admin := caller_email IN ('tecnico.gelormini@gmail.com');

  IF is_super_admin THEN
    RETURN QUERY
    SELECT
      u.id,
      u.email::text,
      u.created_at,
      u.email_confirmed_at,
      u.last_sign_in_at,
      u.banned_until,
      COALESCE(u.raw_user_meta_data->>'display_name', split_part(u.email::text, '@', 1))::text AS display_name,
      CASE
        WHEN u.banned_until IS NOT NULL AND u.banned_until > now() THEN 'banned'
        WHEN u.email_confirmed_at IS NULL THEN 'invited'
        WHEN u.last_sign_in_at IS NULL THEN 'confirmed'
        ELSE 'active'
      END::text AS status
    FROM auth.users u
    ORDER BY u.created_at DESC;
  ELSE
    -- Operatore normale: solo se stesso (server-side, non aggirabile)
    RETURN QUERY
    SELECT
      u.id,
      u.email::text,
      u.created_at,
      u.email_confirmed_at,
      u.last_sign_in_at,
      u.banned_until,
      COALESCE(u.raw_user_meta_data->>'display_name', split_part(u.email::text, '@', 1))::text AS display_name,
      CASE
        WHEN u.banned_until IS NOT NULL AND u.banned_until > now() THEN 'banned'
        WHEN u.email_confirmed_at IS NULL THEN 'invited'
        WHEN u.last_sign_in_at IS NULL THEN 'confirmed'
        ELSE 'active'
      END::text AS status
    FROM auth.users u
    WHERE u.id = auth.uid();
  END IF;
END;
$$;

-- 3) Permission: revoca da PUBLIC e anon, grant solo a authenticated
REVOKE ALL ON FUNCTION public.list_app_users() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.list_app_users() FROM anon;
GRANT EXECUTE ON FUNCTION public.list_app_users() TO authenticated;

-- 4) Verifica smoke (esegui dopo applicazione)
--    a) la function esiste:
--       SELECT proname FROM pg_proc WHERE proname = 'list_app_users';   -- atteso 1
--    b) la vecchia view non esiste piu':
--       SELECT viewname FROM pg_views WHERE viewname = 'app_users';     -- atteso 0
--    c) struttura ritornata corretta (logged come authenticated):
--       SELECT * FROM public.list_app_users() LIMIT 1;
```

- [ ] **Step 2: Commit del file standalone**

Run:
```bash
git add supabase/migration_v18_app_users_function.sql
git commit -m "feat(supabase): migration v18 list_app_users SECURITY DEFINER (A1 standalone)"
```

---

## Task 2: Appende migration v18 a `supabase/schema.sql`

**Files:**
- Modify: `supabase/schema.sql` — appende in fondo al file

- [ ] **Step 1: Trova la fine del file**

Run:
```bash
tail -10 supabase/schema.sql
```
Verifica che l'ultimo blocco sia coerente (commenti finali o ultima migration). Decidi se aggiungere una riga vuota di separazione.

- [ ] **Step 2: Appende il blocco migration v18 in fondo a `supabase/schema.sql`**

Apri `supabase/schema.sql` ed appende questo contenuto in fondo (dopo l'ultima riga esistente, lasciando una riga vuota di separazione):

```sql

-- ============================================================
-- v18 — Fix advisor 'auth_users_exposed': view -> function RPC
-- ============================================================
-- 2026-05-21 — Chiude Supabase advisor critico (security_definer view su auth.users).
-- Replace public.app_users (view) con public.list_app_users() (function RPC con
-- controllo ruolo server-side). Migration applicata via SQL Editor; vedi spec
-- docs/superpowers/specs/2026-05-21-fix-supabase-auth-users-exposed-design.md
-- e file standalone supabase/migration_v18_app_users_function.sql

DROP VIEW IF EXISTS public.app_users CASCADE;

CREATE OR REPLACE FUNCTION public.list_app_users()
RETURNS TABLE (
  id                  uuid,
  email               text,
  created_at          timestamptz,
  email_confirmed_at  timestamptz,
  last_sign_in_at     timestamptz,
  banned_until        timestamptz,
  display_name        text,
  status              text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, auth
AS $$
DECLARE
  caller_email text;
  is_super_admin boolean;
BEGIN
  IF (SELECT auth.role()) <> 'authenticated' THEN
    RAISE EXCEPTION 'list_app_users: caller non autenticato'
      USING HINT = 'login richiesto';
  END IF;

  caller_email := (auth.jwt() ->> 'email');
  IF caller_email IS NULL THEN
    RAISE EXCEPTION 'list_app_users: email caller non disponibile nel JWT';
  END IF;

  is_super_admin := caller_email IN ('tecnico.gelormini@gmail.com');

  IF is_super_admin THEN
    RETURN QUERY
    SELECT
      u.id,
      u.email::text,
      u.created_at,
      u.email_confirmed_at,
      u.last_sign_in_at,
      u.banned_until,
      COALESCE(u.raw_user_meta_data->>'display_name', split_part(u.email::text, '@', 1))::text AS display_name,
      CASE
        WHEN u.banned_until IS NOT NULL AND u.banned_until > now() THEN 'banned'
        WHEN u.email_confirmed_at IS NULL THEN 'invited'
        WHEN u.last_sign_in_at IS NULL THEN 'confirmed'
        ELSE 'active'
      END::text AS status
    FROM auth.users u
    ORDER BY u.created_at DESC;
  ELSE
    RETURN QUERY
    SELECT
      u.id,
      u.email::text,
      u.created_at,
      u.email_confirmed_at,
      u.last_sign_in_at,
      u.banned_until,
      COALESCE(u.raw_user_meta_data->>'display_name', split_part(u.email::text, '@', 1))::text AS display_name,
      CASE
        WHEN u.banned_until IS NOT NULL AND u.banned_until > now() THEN 'banned'
        WHEN u.email_confirmed_at IS NULL THEN 'invited'
        WHEN u.last_sign_in_at IS NULL THEN 'confirmed'
        ELSE 'active'
      END::text AS status
    FROM auth.users u
    WHERE u.id = auth.uid();
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION public.list_app_users() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.list_app_users() FROM anon;
GRANT EXECUTE ON FUNCTION public.list_app_users() TO authenticated;
```

- [ ] **Step 3: Commit dell'aggiornamento schema.sql**

Run:
```bash
git add supabase/schema.sql
git commit -m "feat(supabase): append v18 list_app_users a schema.sql"
```

---

## Task 3: Modifica admin frontend — `loadOperators()`

**Files:**
- Modify: `admin/index.html` — funzione `loadOperators()` (~riga 4096-4140)

- [ ] **Step 1: Localizza il blocco da sostituire**

Trova in `admin/index.html` la chiamata REST (~riga 4098):

```javascript
        const res = await api(`${SUPABASE_URL}/rest/v1/app_users?select=*`);
        if (!res || !res.ok) {
          // Vista non disponibile → migration v15 non applicata
          if (res && res.status === 404) {
```

- [ ] **Step 2: Sostituisci la chiamata REST con POST RPC**

Sostituisci:

```javascript
        const res = await api(`${SUPABASE_URL}/rest/v1/app_users?select=*`);
```

Con:

```javascript
        // A1 fix: chiamata RPC con filtraggio server-side (non aggirabile).
        // L'advisor Supabase 'auth_users_exposed' richiedeva di rimuovere la
        // view security-definer su auth.users; sostituita con function
        // public.list_app_users() (vedi migration v18).
        const res = await api(`${SUPABASE_URL}/rest/v1/rpc/list_app_users`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        });
```

- [ ] **Step 3: Aggiorna il messaggio "migration non trovata" (v15 → v18)**

Trova il blocco (~riga 4101-4115) che mostra il messaggio HTML "Vista app_users non trovata. Applica la migration v15..." con la SQL della vecchia view. Sostituiscilo con un messaggio aggiornato che cita la migration v18 e la function:

```javascript
          if (res && res.status === 404) {
            tbody.innerHTML = `<tr><td colspan="5" class="users-empty">
              ⚠️ Funzione <code>list_app_users</code> non trovata. Applica la migration v18 nel SQL Editor di Supabase
              (vedi <code>supabase/migration_v18_app_users_function.sql</code> nel repo).
              </td></tr>`;
            countEl.textContent = 'Migration v18 da applicare';
            return;
          }
```

- [ ] **Step 4: Rimuovi il filtraggio frontend non-super-admin (ora server-side)**

Trova il blocco (~riga 4118-4125) che filtra `users` lato JavaScript se l'utente non è super-admin:

```javascript
        let users = await res.json();
        \ Filtro permessi: gli operatori non super-admin vedono solo se stessi.
        // Anche se la vista app_users è leggibile da tutti gli authenticated,
        // la UI nasconde gli altri operatori per chiarezza + minimizzazione.
        \ Sicurezza vera: le azioni invite/ban/delete sono rifiutate server-side.
```

Verifica esattamente qual è la logica di filter qui leggendo il file. Se c'è un `if (!isSuperAdmin) users = users.filter(...)` o simile, **rimuovilo** e sostituisci il commento con:

```javascript
        // A1: nessun filtraggio frontend necessario.
        // public.list_app_users() applica gia' il filtro server-side:
        // super-admin riceve tutti, operatore normale riceve solo se stesso.
        let users = await res.json();
```

Se non c'è un filter esplicito (era forse solo commento) → aggiorna solo il commento.

- [ ] **Step 5: Test di sintassi JS (non ci sono linter Python qui, ma verifica almeno che il file non sia corrotto)**

Run:
```bash
grep -n "list_app_users" admin/index.html
```
Expected: 2 occorrenze (la chiamata RPC + il messaggio errore migration).

```bash
grep -c "app_users" admin/index.html
```
Expected: idealmente 0-2 occorrenze rimanenti (i commenti possono restare per spiegare la storia). Verifica che la chiamata REST GET sia sparita:

```bash
grep -n "rest/v1/app_users" admin/index.html
```
Expected: 0 risultati.

- [ ] **Step 6: Commit della modifica frontend**

Run:
```bash
git add admin/index.html
git commit -m "feat(admin): loadOperators usa RPC list_app_users invece di view"
```

---

## Task 4: Self-check + push branch

- [ ] **Step 1: Diff completo branch vs master**

Run:
```bash
git log master..HEAD --oneline
git diff master...HEAD --stat
```
Expected: 4 commit (3 feat + 1 docs già esistente sulla branch se hai committato spec+plan). Stat dovrebbe mostrare schema.sql, migration_v18_*.sql, admin/index.html, docs/superpowers/specs/, docs/superpowers/plans/.

- [ ] **Step 2: Verifica conformità VIEW rimossa / FUNCTION aggiunta**

Run:
```bash
grep -c "CREATE OR REPLACE VIEW public.app_users" supabase/schema.sql
```
Expected: 2 (le occorrenze storiche v15 e v16 — devono restare nei commenti/migrazioni storiche, sono parte della cronologia). NON deve esserci un terzo CREATE VIEW.

```bash
grep -c "CREATE OR REPLACE FUNCTION public.list_app_users" supabase/schema.sql
```
Expected: 1 (la nuova migration v18).

```bash
grep -n "DROP VIEW IF EXISTS public.app_users" supabase/schema.sql
```
Expected: 1 (la riga nella migration v18).

- [ ] **Step 3: Push branch**

Run:
```bash
git push -u origin feat/a1-supabase-auth-users
```
Expected: branch pushato su GitHub.

- [ ] **Step 4: STOP — riferire all'utente**

NON eseguire:
- ❌ Merge in master
- ❌ Esecuzione della migration SQL sul Supabase di produzione
- ❌ Modifiche a Supabase Auth o all'admin in produzione

Riferire all'utente:
- branch creato e pushato
- spec/plan + migration + frontend pronti
- chiedere OK per: merge in master, esecuzione migration su SQL Editor, attesa GitHub Pages
- smoke test post-deploy con 2 account (super-admin + operatore normale)

---

## Self-Review

**1. Spec coverage**

| Sezione spec | Task | OK |
|---|---|---|
| Migration v18 DROP VIEW + CREATE FUNCTION + GRANT | Task 1 + 2 | ✅ |
| Function SECURITY DEFINER con check role + whitelist + filtraggio | Task 1/2 (corpo function) | ✅ |
| Schema return identico alla vista vecchia | Task 1/2 (RETURNS TABLE) | ✅ |
| Frontend RPC instead of REST view | Task 3 step 2 | ✅ |
| Messaggio errore migration aggiornato (v15 → v18) | Task 3 step 3 | ✅ |
| Filtraggio frontend rimosso (server-side è la nuova autorità) | Task 3 step 4 | ✅ |
| File migration standalone in supabase/ per DR | Task 1 | ✅ |
| Stop pre-deploy/merge | Task 4 step 4 | ✅ |

**2. Placeholder scan**

Nessun TBD/TODO/"implementare dopo". Tutti gli step hanno codice/comandi completi.

**3. Type consistency**

| Symbol | Task | Note |
|---|---|---|
| `public.list_app_users()` | Task 1/2 (definita), Task 3 (chiamata via `/rpc/list_app_users`) | Coerente |
| Colonne ritornate (id, email, created_at, ...) | Task 1/2 (RETURNS), Task 3 (rendering rimane invariato) | Identico alla vista vecchia ⇒ frontend non rompe |
| Permission GRANT EXECUTE TO authenticated | Task 1/2 | Coerente |

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-21-fix-supabase-auth-users-exposed.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch fresh subagent per task, review tra task.

**2. Inline Execution (per scope contenuto come questo)** — Esegui in sessione, batch execution con checkpoint.

Per A1 il subagent overhead non vale: scope contenuto, 4 task, codice chirurgico. **Inline è la scelta efficiente.**
