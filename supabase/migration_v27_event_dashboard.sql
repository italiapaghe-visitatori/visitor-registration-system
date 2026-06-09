-- ============================================================
-- MIGRATION v27 — View event_dashboard (server-side stats)
-- ============================================================
--
-- Causa: il pannello admin "Ospiti Attesi" calcolava i contatori
-- TOTALE/FIRMATI/DA ARRIVARE/DENTRO/USCITI lato client a partire da
-- query plurime (visitors + guest_list + arrivedSet). Ogni edit
-- introduceva un edge case (race polling, guest cross-event, +1 ghost).
--
-- Soluzione: una VIEW server-side che esprime in modo deterministico
-- i conteggi per ogni evento, sfruttando integrita' referenziale
-- guest_list.event_id e matched_visitor_id NON NULL.
--
-- USAGE client:
--   GET /rest/v1/event_dashboard?event_id=eq.<UUID>&select=*
-- → 1 sola riga con tutti i contatori + by_date + by_slot
--   come JSONB pronti da renderizzare.
--
-- RLS: la view ha security_invoker=true (eredita policy delle tabelle
-- sottostanti). Niente bypass auth.
-- ============================================================

DROP VIEW IF EXISTS public.event_dashboard CASCADE;

CREATE VIEW public.event_dashboard
WITH (security_invoker = true) AS
SELECT
  e.id                                  AS event_id,
  e.name                                AS event_name,
  e.event_type,
  e.is_active,
  e.event_start_date,
  e.event_end_date,
  e.qr_valid_from,
  e.closed_at,
  -- Contatori base (guest_list authoritative — niente client iteration)
  COALESCE(gl_counts.total_guests, 0)   AS total_guests,
  COALESCE(gl_counts.signed, 0)         AS signed,
  COALESCE(gl_counts.waiting, 0)        AS waiting,
  -- Contatori movimento (visitors): chi e' dentro adesso / chi e' uscito
  COALESCE(v_counts.inside_now, 0)      AS inside_now,
  COALESCE(v_counts.checked_out, 0)     AS checked_out,
  -- Breakdown per giornata { "2026-06-09": {total, signed, waiting}, ... }
  COALESCE(gl_counts.by_date, '{}'::jsonb)  AS by_date,
  -- Breakdown per slot { "mattina": {total, signed, waiting}, ... }
  COALESCE(gl_counts.by_slot, '{}'::jsonb)  AS by_slot
FROM events e
LEFT JOIN LATERAL (
  SELECT
    COUNT(*)                                                AS total_guests,
    COUNT(gl.matched_visitor_id)                            AS signed,
    COUNT(*) FILTER (WHERE gl.matched_visitor_id IS NULL)   AS waiting,
    -- by_date
    (SELECT jsonb_object_agg(date_str, info)
     FROM (
       SELECT
         inner_gl.expected_date::text AS date_str,
         jsonb_build_object(
           'total',   COUNT(*),
           'signed',  COUNT(inner_gl.matched_visitor_id),
           'waiting', COUNT(*) - COUNT(inner_gl.matched_visitor_id)
         ) AS info
       FROM guest_list inner_gl
       WHERE inner_gl.event_id = e.id
       GROUP BY inner_gl.expected_date
     ) sub) AS by_date,
    -- by_slot (classificazione su notes)
    (SELECT jsonb_object_agg(slot_key, info)
     FROM (
       SELECT
         CASE
           WHEN LOWER(COALESCE(inner_gl.notes, '')) LIKE '%mattina%'    THEN 'mattina'
           WHEN LOWER(COALESCE(inner_gl.notes, '')) LIKE '%pomeriggio%' THEN 'pomeriggio'
           WHEN LOWER(COALESCE(inner_gl.notes, '')) LIKE '%giornata%'   THEN 'giornata'
           ELSE 'altro'
         END AS slot_key,
         jsonb_build_object(
           'total',   COUNT(*),
           'signed',  COUNT(inner_gl.matched_visitor_id),
           'waiting', COUNT(*) - COUNT(inner_gl.matched_visitor_id)
         ) AS info
       FROM guest_list inner_gl
       WHERE inner_gl.event_id = e.id
       GROUP BY slot_key
     ) sub) AS by_slot
  FROM guest_list gl
  WHERE gl.event_id = e.id
) gl_counts ON true
LEFT JOIN LATERAL (
  SELECT
    COUNT(*) FILTER (
      WHERE v.entry_time IS NOT NULL
        AND v.exit_time IS NULL
        AND COALESCE(v.xatlas_status, '') <> 'checked_out'
    ) AS inside_now,
    COUNT(*) FILTER (WHERE v.xatlas_status = 'checked_out') AS checked_out
  FROM visitors v
  WHERE v.event_id = e.id
) v_counts ON true;

-- Permessi (RLS della view eredita da events/guest_list/visitors tramite security_invoker)
GRANT SELECT ON public.event_dashboard TO anon, authenticated, service_role;

COMMENT ON VIEW public.event_dashboard IS
'Stats per evento server-side authoritative. Usata dal pannello admin per
totale/firmati/da_arrivare/dentro/usciti + breakdown by_date/by_slot.
Sostituisce calcoli client-side che erano fragili (race polling, +1 ghost da
guest_list cross-event). RLS: security_invoker=true.';
