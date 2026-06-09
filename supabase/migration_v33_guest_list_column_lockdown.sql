-- ============================================================
-- MIGRATION v33 — Lockdown colonne anon su guest_list
-- ============================================================
--
-- Completa il fix PII: guest_list aveva guest_list_anon_read USING(true) →
-- anon leggeva TUTTE le colonne incluse phone, document_id, document_type,
-- department, notes di tutti gli ospiti di tutti gli eventi.
--
-- Il kiosk legge da guest_list SOLO: id, first_name, last_name, email,
-- company, job_title, person_to_visit, visit_reason, expected_date,
-- handoff_requested_at, event_id, matched_visitor_id (il frontend e' stato
-- aggiornato per non usare piu' select=*). email serve per il filtro
-- ilike del lockout → resta leggibile (residuo accettato).
--
-- INSERT/UPDATE guest_list restano authenticated-only (gia' cosi'): il kiosk
-- non scrive guest_list, solo visitors.
-- ============================================================

REVOKE SELECT ON public.guest_list FROM anon;
GRANT SELECT (id, first_name, last_name, email, company, job_title,
              person_to_visit, visit_reason, expected_date,
              handoff_requested_at, event_id, matched_visitor_id, created_at)
  ON public.guest_list TO anon;

COMMENT ON TABLE public.guest_list IS
'v33 (2026-06-09): anon SELECT solo su colonne kiosk (no phone/document_id/
document_type/department/notes). email leggibile (filtro lockout). INSERT/UPDATE
authenticated-only.';
