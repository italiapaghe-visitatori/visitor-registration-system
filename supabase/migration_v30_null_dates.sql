-- ============================================================
-- MIGRATION v30 — by_date robusto con expected_date NULL
-- ============================================================
--
-- Bug: i 38 guest DM hanno expected_date NULL (import maggio senza
-- data per evento 2 giorni). jsonb_object_agg con chiave NULL va in
-- ERROR "field name must not be null" → la SELECT by_date della view
-- falliva per DM e l'admin ricadeva sui calcoli locali.
--
-- Fix: chiave by_date = COALESCE(expected_date::text, 'senza_data').
-- Il client JS filtra le chiavi con _isValidIsoDate quindi 'senza_data'
-- viene ignorata dalle pillole giorno (comportamento corretto: evento
-- senza date per-ospite non mostra pillole).
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
         COALESCE(expected_date::text, 'senza_data') AS date_str,
         jsonb_build_object(
           'total',   COUNT(*),
           'signed',  COUNT(*) FILTER (WHERE has_sig),
           'waiting', COUNT(*) FILTER (WHERE NOT has_sig)
         ) AS info
       FROM gl_sig
       GROUP BY COALESCE(expected_date::text, 'senza_data')
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
'v30 (2026-06-09): by_date key NULL-safe via COALESCE(senza_data). Fix per
guest senza expected_date (es. DM import maggio) che mandavano in errore
jsonb_object_agg. signed = firma reale (v29). RLS: security_invoker=true.';
