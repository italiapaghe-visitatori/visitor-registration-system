-- ============================================================
-- MIGRATION v26 — Campo event_type su events (turnstile vs qr_only)
-- ============================================================
--
-- Contesto: il titolare ha deciso di non usare piu' badge/tornelli per
-- alcuni eventi (es. Corso di Primo Soccorso 9-19/06). Per quegli eventi
-- gli ospiti firmano via QR e basta — niente badge fisico, niente swipe
-- al tornello. Per altri eventi (es. Formazione Direzione Marketing
-- 10-11/06) continuiamo col workflow standard (badge + tornelli + Gate
-- Open System).
--
-- Soluzione: aggiungo `event_type` a events:
--   'turnstile' = workflow classico (badge, tornelli, pool, pre-assegnazione)
--   'qr_only'   = workflow semplificato (firma QR + Gate Open System OUT-only)
--
-- L'admin nasconde sezioni Badge/Pool/Pre-assegna se evento attivo e' qr_only.
-- Il kiosk frontend cambia il messaggio iniziale ("Ritira badge" -> solo firma).
-- Default 'turnstile' per backward compatibility con eventi esistenti.
-- ============================================================

ALTER TABLE events
  ADD COLUMN IF NOT EXISTS event_type TEXT NOT NULL DEFAULT 'turnstile'
  CHECK (event_type IN ('turnstile', 'qr_only'));

COMMENT ON COLUMN events.event_type IS
  'turnstile = con badge e tornelli (workflow classico); qr_only = solo registrazione QR (no badge, no tornelli, exit tracciato manualmente via Gate Open System OUT)';

-- Indice per filtri rapidi su tipo evento (utile per stats e dashboard)
CREATE INDEX IF NOT EXISTS events_event_type_idx ON events (event_type);

-- Marca Corso di Primo Soccorso come qr_only (decisione del titolare 08/06)
UPDATE events
SET event_type = 'qr_only'
WHERE id = '7d2ca899-2722-4d2c-a5c6-db2427cb546e';

-- Formazione Direzione Marketing resta turnstile (badge gia' pre-assegnati,
-- workflow classico per evento 10-11/06)
UPDATE events
SET event_type = 'turnstile'
WHERE id = '450da933-f438-43ed-853f-6ede8ece3659';
