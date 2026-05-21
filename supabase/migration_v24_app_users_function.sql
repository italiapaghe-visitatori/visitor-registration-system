-- MIGRATION v24 — Fix advisor 'auth_users_exposed': view -> function RPC
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
