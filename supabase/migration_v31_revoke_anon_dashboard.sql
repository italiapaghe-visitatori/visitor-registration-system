-- ============================================================
-- MIGRATION v31 — REVOKE anon su event_dashboard (fix PII leak)
-- ============================================================
--
-- Finding security audit 2026-06-09: la view event_dashboard (creata in
-- v27-v30) era GRANT SELECT a anon. anon = chiunque abbia la anon key
-- pubblica (estraibile dal JS del kiosk). Esponeva conteggi per-evento +
-- nomi degli attendee multi-giornata (multi_day_attendees) di TUTTI gli
-- eventi, senza login.
--
-- Fix: la view serve SOLO al pannello admin (autenticato). Il kiosk
-- pubblico NON la usa (verificato: 0 riferimenti in frontend/index.html).
-- Stesso pattern gia' applicato a gate_open_queue_recent (v25).
--
-- NESSUNA rottura: admin usa role authenticated.
-- ============================================================

REVOKE ALL ON public.event_dashboard FROM anon, PUBLIC;
GRANT SELECT ON public.event_dashboard TO authenticated, service_role;

COMMENT ON VIEW public.event_dashboard IS
'v31 (2026-06-09): REVOKE anon — solo authenticated/service_role. Fix PII leak
audit. La view serve al pannello admin autenticato; kiosk pubblico non la usa.';
