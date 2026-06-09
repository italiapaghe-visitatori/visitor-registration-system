-- ============================================================
-- MIGRATION v28 — Estende event_dashboard con persone uniche + multi-giornata
-- ============================================================
--
-- Contesto: il pannello mostrava 67 totali nel PS ma il file MD originale
-- ha 53 persone uniche (11 ospiti compaiono SIA il 9/6 SIA il 18/6 per
-- corsi multi-giornata). 67 = presenze (person-day), 53 = persone uniche.
--
-- Aggiungo alla view event_dashboard:
--   unique_persons         INT    -> count distinct di nome+cognome normalizzati
--   multi_day_attendees    JSONB  -> [{"name": "...", "dates": [...]}] (chi viene >1 giorno)
--   total_presences        INT    -> alias di total_guests per chiarezza semantica
--
-- Nessun breaking change: i campi v27 restano invariati.
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
  -- Conteggi base
  COALESCE(gl_counts.total_guests, 0)   AS total_guests,
  COALESCE(gl_counts.total_guests, 0)   AS total_presences,     -- alias: presenze (person-day)
  COALESCE(gl_counts.signed, 0)         AS signed,
  COALESCE(gl_counts.waiting, 0)        AS waiting,
  -- Persone uniche (deduplicate per nome+cognome normalizzato)
  COALESCE(uniq.unique_persons, 0)      AS unique_persons,
  COALESCE(uniq.multi_day_count, 0)     AS multi_day_count,
  COALESCE(uniq.multi_day_attendees, '[]'::jsonb) AS multi_day_attendees,
  -- Movimento
  COALESCE(v_counts.inside_now, 0)      AS inside_now,
  COALESCE(v_counts.checked_out, 0)     AS checked_out,
  -- Breakdown
  COALESCE(gl_counts.by_date, '{}'::jsonb)  AS by_date,
  COALESCE(gl_counts.by_slot, '{}'::jsonb)  AS by_slot
FROM events e
LEFT JOIN LATERAL (
  SELECT
    COUNT(*)                                                AS total_guests,
    COUNT(gl.matched_visitor_id)                            AS signed,
    COUNT(*) FILTER (WHERE gl.matched_visitor_id IS NULL)   AS waiting,
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
  -- Persone uniche + chi viene in piu' giornate
  SELECT
    COUNT(DISTINCT name_norm)                       AS unique_persons,
    COUNT(DISTINCT name_norm) FILTER (WHERE n_days > 1) AS multi_day_count,
    COALESCE(
      jsonb_agg(jsonb_build_object('name', display_name, 'dates', dates_arr) ORDER BY display_name)
        FILTER (WHERE n_days > 1),
      '[]'::jsonb
    ) AS multi_day_attendees
  FROM (
    SELECT
      TRIM(UPPER(COALESCE(last_name,'') || ' ' || COALESCE(first_name,''))) AS name_norm,
      UPPER(COALESCE(last_name,'')) || ' ' || INITCAP(LOWER(COALESCE(first_name,''))) AS display_name,
      COUNT(DISTINCT expected_date)                                          AS n_days,
      array_agg(DISTINCT to_char(expected_date, 'DD/MM/YYYY')
                ORDER BY to_char(expected_date, 'DD/MM/YYYY'))               AS dates_arr
    FROM guest_list
    WHERE event_id = e.id
      AND (COALESCE(last_name,'') <> '' OR COALESCE(first_name,'') <> '')
    GROUP BY name_norm, display_name
  ) per_person
) uniq ON true
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

GRANT SELECT ON public.event_dashboard TO anon, authenticated, service_role;

COMMENT ON VIEW public.event_dashboard IS
'v28 (2026-06-10): aggiunto unique_persons + multi_day_count + multi_day_attendees
per distinguere "presenze (person-day)" da "persone uniche" in eventi multi-giornata
(es. PS dove 11 ospiti vengono sia il 9 sia il 18). RLS: security_invoker=true.';
