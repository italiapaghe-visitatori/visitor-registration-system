-- ============================================================
-- MIGRATION v25 — Coda apertura tornelli manuale
-- ============================================================
--
-- Contesto: WSM→FMC sync XAtlas rotto dal 15/05/2026. I 38 VIS
-- pre-attivati non raggiungono i tornelli automaticamente.
-- Soluzione: bottone "Apri tornello" in admin che inserisce una
-- riga in questa coda. L'agente Python (su srvxatlas, ha telnet
-- locale a FMC 8189) processa la coda e invia
-- EXEC <gate_id> openEntryOneShot/openExitOneShot.
--
-- Idempotenza: idempotency_key UNIQUE evita doppi click apertura.
-- Audit: trigger auto-popola audit_log con action='gate_open'.
-- Realtime: admin polls la riga + listener su status update.
--
-- Compatibilita: zero impatto su altre tabelle. Nessun FK NOT NULL
-- (visitor_id e guest_id entrambi nullable per casi walk-in al volo).
-- ============================================================

-- Tabella principale coda apertura
CREATE TABLE IF NOT EXISTS gate_open_queue (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Tornello target: ID device XAtlas
  --   202 = TORNELLO_IN (SuperTraxLite ingresso)
  --   205 = TORNELLO_OUT (SuperTraxLite uscita)
  --   240 = AXG_INGRESSO (X0 ingresso alternativo)
  --   242 = AXG_PORTELLO (X0 uscita alternativa / portello)
  gate_id           INTEGER NOT NULL CHECK (gate_id IN (202, 205, 240, 242)),
  direction         TEXT    NOT NULL CHECK (direction IN ('entry', 'exit')),

  -- Riferimenti opzionali (tracciabilita ospite associato)
  visitor_id        UUID REFERENCES visitors(id)    ON DELETE SET NULL,
  guest_id          UUID REFERENCES guest_list(id)  ON DELETE SET NULL,

  -- Chi ha cliccato il bottone (operatore admin)
  operator_email    TEXT NOT NULL,

  -- Stato workflow
  --   pending  = appena inserito, agente non l'ha ancora preso
  --   opening  = agente l'ha claimato, sta inviando EXEC al tornello
  --   opened   = tornello ha confermato apertura
  --   failed   = errore (telnet timeout, EXEC rejected, etc.)
  status            TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'opening', 'opened', 'failed')),

  -- Timing
  requested_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  executed_at       TIMESTAMPTZ,

  -- Risposta agente per debug
  agent_response    TEXT,
  error_message     TEXT,

  -- Idempotency: il bottone genera un key UUID al click. Se l'utente
  -- riclicca prima della risposta, lo stesso key impedisce doppia
  -- insertion (constraint UNIQUE -> 409 Conflict -> UI ignora errore).
  idempotency_key   TEXT NOT NULL UNIQUE,

  -- Note operative opzionali (es. "ingresso ritardatario", "ospite VIP")
  notes             TEXT
);

-- Indice per il polling agente: cerca pending in ordine cronologico
CREATE INDEX IF NOT EXISTS gate_open_queue_pending
  ON gate_open_queue (requested_at)
  WHERE status = 'pending';

-- Indice per realtime UI: per operatore vede le sue ultime
CREATE INDEX IF NOT EXISTS gate_open_queue_by_operator
  ON gate_open_queue (operator_email, requested_at DESC);

-- Indice per visitor lookup (storia aperture per ospite)
CREATE INDEX IF NOT EXISTS gate_open_queue_by_visitor
  ON gate_open_queue (visitor_id, requested_at DESC)
  WHERE visitor_id IS NOT NULL;

-- Indice per guest lookup
CREATE INDEX IF NOT EXISTS gate_open_queue_by_guest
  ON gate_open_queue (guest_id, requested_at DESC)
  WHERE guest_id IS NOT NULL;

-- ── RLS ─────────────────────────────────────────────────────
ALTER TABLE gate_open_queue ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "gate_open_queue_auth_select" ON gate_open_queue;
DROP POLICY IF EXISTS "gate_open_queue_auth_insert" ON gate_open_queue;
DROP POLICY IF EXISTS "gate_open_queue_service_all" ON gate_open_queue;

-- SELECT: ogni operatore autenticato vede tutte le righe
-- (utile per supervisione collaboratrici durante evento)
CREATE POLICY "gate_open_queue_auth_select"
  ON gate_open_queue FOR SELECT
  USING (auth.role() = 'authenticated');

-- INSERT: ogni operatore autenticato puo' inserire SUE richieste
-- (operator_email forzato a auth.email per evitare impersonificazione)
CREATE POLICY "gate_open_queue_auth_insert"
  ON gate_open_queue FOR INSERT
  WITH CHECK (
    auth.role() = 'authenticated'
    AND operator_email = COALESCE(auth.jwt() ->> 'email', auth.email())
  );

-- UPDATE: nessun operatore admin puo' modificare le righe (immutabili lato UI).
-- Solo l'agente Python via service_role aggiorna lo status.
-- (service_role bypassa RLS by default, quindi non serve policy esplicita)

-- ── Audit log trigger ───────────────────────────────────────
-- Ad ogni INSERT sulla coda, registra audit_log con action='gate_open_request'.
-- A ogni UPDATE che porta a status terminal (opened/failed), registra esito.
CREATE OR REPLACE FUNCTION gate_open_audit_trigger()
RETURNS TRIGGER AS $$
DECLARE
  gate_name TEXT;
BEGIN
  gate_name := CASE NEW.gate_id
    WHEN 202 THEN 'TORNELLO_IN'
    WHEN 205 THEN 'TORNELLO_OUT'
    WHEN 240 THEN 'AXG_INGRESSO'
    WHEN 242 THEN 'AXG_PORTELLO'
    ELSE 'UNKNOWN(' || NEW.gate_id::text || ')'
  END;

  IF TG_OP = 'INSERT' THEN
    INSERT INTO audit_log (user_email, action, entity, entity_id, details)
    VALUES (
      NEW.operator_email,
      'gate_open_request',
      'gate_open_queue',
      NEW.id::text,
      jsonb_build_object(
        'gate_id',     NEW.gate_id,
        'gate_name',   gate_name,
        'direction',   NEW.direction,
        'visitor_id',  NEW.visitor_id,
        'guest_id',    NEW.guest_id,
        'notes',       NEW.notes
      )
    );
  ELSIF TG_OP = 'UPDATE' AND OLD.status IN ('pending','opening') AND NEW.status IN ('opened','failed') THEN
    INSERT INTO audit_log (user_email, action, entity, entity_id, details)
    VALUES (
      NEW.operator_email,
      CASE NEW.status WHEN 'opened' THEN 'gate_open_success' ELSE 'gate_open_failed' END,
      'gate_open_queue',
      NEW.id::text,
      jsonb_build_object(
        'gate_id',        NEW.gate_id,
        'gate_name',      gate_name,
        'direction',      NEW.direction,
        'visitor_id',     NEW.visitor_id,
        'guest_id',       NEW.guest_id,
        'executed_at',    NEW.executed_at,
        'latency_ms',     EXTRACT(EPOCH FROM (NEW.executed_at - NEW.requested_at)) * 1000,
        'agent_response', LEFT(COALESCE(NEW.agent_response, ''), 200),
        'error_message',  NEW.error_message
      )
    );
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS gate_open_audit ON gate_open_queue;
CREATE TRIGGER gate_open_audit
  AFTER INSERT OR UPDATE ON gate_open_queue
  FOR EACH ROW
  EXECUTE FUNCTION gate_open_audit_trigger();

-- ── Helper view per UI: ultime aperture per visitor ───────
-- security_invoker=true => la view honora le RLS di gate_open_queue per il
-- caller (non bypassa con i privilegi dell'owner). Combinato con REVOKE da
-- anon/PUBLIC, garantisce che solo operatori authenticated possano leggere
-- operator_email + visitor movement patterns (dati sensibili).
CREATE OR REPLACE VIEW gate_open_queue_recent
WITH (security_invoker = true) AS
SELECT
  gq.id,
  gq.gate_id,
  CASE gq.gate_id
    WHEN 202 THEN 'TORNELLO_IN'
    WHEN 205 THEN 'TORNELLO_OUT'
    WHEN 240 THEN 'AXG_INGRESSO'
    WHEN 242 THEN 'AXG_PORTELLO'
  END AS gate_name,
  gq.direction,
  gq.visitor_id,
  gq.guest_id,
  gq.operator_email,
  gq.status,
  gq.requested_at,
  gq.executed_at,
  EXTRACT(EPOCH FROM (gq.executed_at - gq.requested_at)) * 1000 AS latency_ms
FROM gate_open_queue gq
WHERE gq.requested_at > NOW() - INTERVAL '24 hours'
ORDER BY gq.requested_at DESC;

-- IMPORTANTE: anon_key è esposta nel kiosk pubblico (frontend/config.js).
-- Negare esplicitamente anon + PUBLIC su questa view per non leakare
-- operator_email e movement patterns degli ospiti via richiesta anonima.
REVOKE ALL ON gate_open_queue_recent FROM PUBLIC, anon;
GRANT SELECT ON gate_open_queue_recent TO authenticated;

-- ── Cleanup automatico: cancella righe vecchie > 30 giorni ───
-- (idempotente, eseguito manualmente o da job cleanup esistente)
-- DELETE FROM gate_open_queue WHERE requested_at < NOW() - INTERVAL '30 days';

-- ============================================================
-- FINE MIGRATION v25
-- ============================================================
