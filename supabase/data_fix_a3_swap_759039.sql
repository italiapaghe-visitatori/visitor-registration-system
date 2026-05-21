-- A3 — Fix swap dati 759039 (SICILIANO ANTONIO / ROMANO ELISA)
-- ============================================================================
-- Da eseguire UNA SOLA VOLTA nel SQL Editor di Supabase Dashboard.
-- Lo script e' un singolo blocco auto-committato; non usare BEGIN/COMMIT manuali
-- (l'editor Supabase auto-committa il blocco intero — vedi lezione 15/05/2026).
--
-- Causa: pattern noto di mis-aggancio dal link QR generico (?mode=qr&event=...)
-- in cui un ospite seleziona/scrive il nome di un altro invitato dalla lista
-- → la sua firma viene agganciata al guest_id sbagliato.
--
-- Stato pre-fix:
--   visitor ff436167 — "ANTONIO SICILIANO", badge 759039 (era di ELISA ROMANO),
--                      guest_id=d2edf4ff (slot di ELISA ROMANO), firma=SI.
--                      Cioe': firma di SICILIANO finita sul slot di Elisa Romano.
--   visitor f18c2403 — vero stub di SICILIANO ANTONIO, badge 257806 (suo),
--                      guest_id=ba6a6e69 (slot suo), firma=NO.
--   ROMANO ELISA   — nessun record visitor proprio (il suo slot e' occupato).
--
-- Obiettivo del fix:
--   1) Copia la firma+consensi+documento da ff436167 a f18c2403 (SICILIANO firmato sul suo slot).
--   2) Resetta ff436167 come stub pulito di ELISA ROMANO (badge 759039 resta suo).
-- ============================================================================

-- 1) Sposta la firma di SICILIANO dal record sbagliato (ff436167)
--    al suo stub corretto (f18c2403, badge 257806)
UPDATE visitors p SET
  signature             = s.signature,
  document_id           = s.document_id,
  document_type         = s.document_type,
  phone                 = COALESCE(s.phone, p.phone),
  data_consent          = s.data_consent,
  badge_agreement       = s.badge_agreement,
  access_rules_consent  = s.access_rules_consent,
  access_rules_at       = s.access_rules_at,
  access_rules_version  = s.access_rules_version,
  access_rules_opened   = s.access_rules_opened,
  consent_ip            = s.consent_ip,
  consent_user_agent    = s.consent_user_agent,
  access_rules_pdf_hash = s.access_rules_pdf_hash,
  access_rules_pdf_size = s.access_rules_pdf_size
FROM visitors s
WHERE p.id = 'f18c2403-8dd0-4407-9eee-c4ab9310d4a3'
  AND s.id = 'ff436167-170e-47cf-858b-25344b5b2eb3';

-- 2) Ripristina ff436167 come stub PULITO di ELISA ROMANO
--    (badge 759039 resta = e' il suo originale, guest_id resta = il suo slot)
UPDATE visitors SET
  first_name            = 'ELISA',
  last_name             = 'ROMANO',
  email                 = 'elisa.romano@mdspa.it',
  signature             = NULL,
  document_id           = NULL,
  document_type         = NULL,
  data_consent          = FALSE,
  badge_agreement       = FALSE,
  access_rules_consent  = FALSE,
  access_rules_at       = NULL,
  access_rules_version  = NULL,
  access_rules_opened   = FALSE,
  consent_ip            = NULL,
  consent_user_agent    = NULL,
  access_rules_pdf_hash = NULL,
  access_rules_pdf_size = NULL
WHERE id = 'ff436167-170e-47cf-858b-25344b5b2eb3';

-- 3) Verifica esito atteso (incollare l'output qui sotto a chi ti segue)
SELECT id, first_name, last_name, email, badge_number,
       (signature IS NOT NULL) AS firmato
FROM visitors
WHERE id IN ('f18c2403-8dd0-4407-9eee-c4ab9310d4a3',
             'ff436167-170e-47cf-858b-25344b5b2eb3');

-- Atteso:
--   f18c2403 -> ANTONIO  SICILIANO  | badge 257806 | firmato = true
--   ff436167 -> ELISA    ROMANO     | badge 759039 | firmato = false
