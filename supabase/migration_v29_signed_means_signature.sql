-- ============================================================
-- MIGRATION v29 — "signed" = firma reale (non solo matched_visitor_id)
-- ============================================================
--
-- Bug scoperto 9/06 sera (evento DM): la view v28 contava
-- signed = COUNT(matched_visitor_id). Ma per DM i 38 ospiti hanno
-- visitor STUB creati a maggio per la pre-attivazione badge XAtlas:
-- matched_visitor_id valorizzato MA signature NULL. Il pannello
-- mostrava "38 firmati / 0 da arrivare" quando in realta' molti
-- non hanno mai firmato.
--
-- Fix: signed = COUNT di guest il cui visitor collegato ha una
-- signature reale (length > 100 per escludere stringhe spurie).
-- Stessa correzione per by_date e by_slot.
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
  COALESCE(gl_counts.total_guests, 0)   AS total_guests,
  COALESCE(gl_counts.total_guests, 0)   AS total_presences,
  COALESCE(gl_counts.signed, 0)         AS signed,
  COALESCE(gl_counts.waiting, 0)        AS waiting,
  COALESCE(uniq.unique_persons, 0)      AS unique_persons,
  COALESCE(uniq.multi_day_count, 0)     AS multi_day_count,
  COALESCE(uniq.multi_day_attendees, '[]'::jsonb) AS multi_day_attendees,
  COALESCE(v_counts.inside_now, 0)      AS inside_now,
  COALESCE(v_counts.checked_out, 0)     AS checked_out,
  COALESCE(gl_counts.by_date, '{}'::jsonb)  AS by_date,
  COALESCE(gl_counts.by_slot, '{}'::jsonb)  AS by_slot
FROM events e
LEFT JOIN LATERAL (
  -- has_sig: firma reale del visitor collegato (no stub badge)
  WITH gl_sig AS (
    SELECT gl.*,
           EXISTS (
             SELECT 1 FROM visitors v
             WHERE v.id = gl.matched_visitor_id
               AND v.signature IS NOT NULL
               AND length(v.signature) > 100
           ) AS has_sig
    FROM guest_list gl
    WHERE gl.event_id = e.id
  )
  SELECT
    COUNT(*)                                  AS total_guests,
    COUNT(*) FILTER (WHERE has_sig)           AS signed,
    COUNT(*) FILTER (WHERE NOT has_sig)       AS waiting,
    (SELECT jsonb_object_agg(date_str, info)
     FROM (
       SELECT
         expected_date::text AS date_str,
         jsonb_build_object(
           'total',   COUNT(*),
           'signed',  COUNT(*) FILTER (WHERE has_sig),
           'waiting', COUNT(*) FILTER (WHERE NOT has_sig)
         ) AS info
       FROM gl_sig
       GROUP BY expected_date
     ) sub) AS by_date,
    (SELECT jsonb_object_agg(slot_key, info)
     FROM (
       SELECT
         CASE
           WHEN LOWER(COALESCE(notes, '')) LIKE '%mattina%'    THEN 'mattina'
           WHEN LOWER(COALESCE(notes, '')) LIKE '%pomeriggio%' THEN 'pomeriggio'
           WHEN LOWER(COALESCE(notes, '')) LIKE '%giornata%'   THEN 'giornata'
           ELSE 'altro'
         END AS slot_key,
         jsonb_build_object(
           'total',   COUNT(*),
           'signed',  COUNT(*) FILTER (WHERE has_sig),
           'waiting', COUNT(*) FILTER (WHERE NOT has_sig)
         ) AS info
       FROM gl_sig
       GROUP BY slot_key
     ) sub) AS by_slot
  FROM gl_sig
) gl_counts ON true
LEFT JOIN LATERAL (
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
'v29 (2026-06-09): signed ora = firma reale del visitor collegato (signature
length>100), non semplice matched_visitor_id. Fix per stub badge pre-assegnati
(DM) che venivano contati come firmati. RLS: security_invoker=true.';
