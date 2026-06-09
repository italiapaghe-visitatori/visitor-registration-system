-- ============================================================
-- MIGRATION v32 — Lockdown colonne anon su visitors + REVOKE movements
-- ============================================================
--
-- Finding security audit 2026-06-09 (HIGH GDPR): anon (chiunque con la anon
-- key pubblica) leggeva TUTTE le colonne di visitors, inclusi document_id,
-- document_type, consent_ip, consent_user_agent, phone, email.
--
-- Fix column-level (NON rompe il kiosk — verificato):
-- Il kiosk pubblico legge da visitors SOLO: id, guest_id, first_name,
-- last_name, signature (per filtro is.null/not.is.null), event_id, created_at.
-- Le INSERT/PATCH di firma usano Prefer: return=minimal → NON serve SELECT
-- per scrivere. Quindi restringo le colonne SELECT di anon a quelle 7.
--
-- visitor_movements: anon non lo usa (kiosk 0 query reali, agente usa
-- service_role, admin e' authenticated) → REVOKE anon completo.
--
-- L'admin (authenticated) e l'agente (service_role) mantengono accesso pieno.
-- guest_list NON toccato qui (usa select=* per QR personale → richiede
-- VIEW + modifica frontend, pianificato separatamente).
-- ============================================================

-- ── visitors: solo 7 colonne leggibili da anon ──
REVOKE SELECT ON public.visitors FROM anon;
GRANT SELECT (id, guest_id, first_name, last_name, signature, event_id, created_at)
  ON public.visitors TO anon;

-- ── visitor_movements: anon fuori del tutto ──
-- (agente=service_role, admin=authenticated, kiosk non lo usa)
REVOKE ALL ON public.visitor_movements FROM anon;

COMMENT ON TABLE public.visitors IS
'v32 (2026-06-09): anon ha SELECT solo su (id,guest_id,first_name,last_name,
signature,event_id,created_at). Bloccati document_id/consent_ip/email/phone ad
anon. INSERT/UPDATE-prestub anon invariati (return=minimal). Full read per
authenticated/service_role.';
