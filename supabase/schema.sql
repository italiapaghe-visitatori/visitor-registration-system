-- Visitor Registration System - Supabase Schema with Authentication
-- Based on JotForm "Modulo di Registrazione Visitatori" + modifiche

CREATE TABLE visitor_registrations (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ DEFAULT NOW(),  
  -- Visitor info (Nome e Cognome separati)
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  visit_date DATE NOT NULL,
  entry_time TIME NOT NULL,
  exit_time TIME,  
  -- Visit details
  person_to_visit TEXT,
  visit_reason TEXT NOT NULL CHECK (visit_reason IN (
    'Appuntamento di lavoro',
    'Colloquio',
    'Consegna documenti',
    'Corso di formazione in aula',
    'Fornitore',
    'Incontro di lavoro',
    'Intervista di lavoro',
    'Manutenzione/assistenza tecnica',
    'Prenotazione',
    'Consegna',
    'Visita',
    'Assistenza clienti',
    'Ritiro documenti',
    'Trasferimento',
    'Altro'
  )),  
  -- Additional fields
  department TEXT,
  vehicle_plate TEXT,
  -- Badge
  badge_number TEXT,  
  -- Consent and signature
  data_consent BOOLEAN DEFAULT FALSE,
  signature TEXT, -- base64 encoded signature  
  -- Metadata
  ip_address TEXT,
  user_agent TEXT
);

-- Enable Row Level Security
ALTER TABLE visitor_registrations ENABLE ROW LEVEL SECURITY;

-- Allow anonymous inserts (for the public form - visitors registering)
CREATE POLICY "Allow anonymous inserts" ON visitor_registrations
  FOR INSERT WITH CHECK (true);

-- ONLY authenticated users can read (for admin panel)
CREATE POLICY "Allow authenticated reads" ON visitor_registrations
  FOR SELECT USING (auth.role() = 'authenticated');

-- Only authenticated users can update/delete
CREATE POLICY "Allow authenticated update" ON visitor_registrations
  FOR UPDATE USING (auth.role() = 'authenticated');

-- Indexes for better query performance
CREATE INDEX idx_visitor_date ON visitor_registrations(visit_date);
CREATE INDEX idx_visitor_first_name ON visitor_registrations(first_name);
CREATE INDEX idx_visitor_last_name ON visitor_registrations(last_name);
CREATE INDEX idx_visitor_reason ON visitor_registrations(visit_reason);

COMMENT ON TABLE visitor_registrations IS 'Registrazione visitatori - sistema modulare multi-contesto - ACCESSO RISERVATO';

-- Create an admin user (run this after enabling email auth in Supabase)
-- In Supabase Dashboard: Authentication > Settings > Enable Email auth
-- Then create user manually in Authentication > Users > Invite User

-- ============================================================
-- MIGRATION v2 — Integrazione XAtlas + Lista Ospiti Pre-registrati
-- Eseguire nel SQL Editor di Supabase Dashboard
-- ============================================================

-- Tabella ospiti pre-registrati
CREATE TABLE IF NOT EXISTS guest_list (
  id                 UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  first_name         TEXT NOT NULL,
  last_name          TEXT NOT NULL,
  email              TEXT,
  company            TEXT,
  person_to_visit    TEXT,
  visit_reason       TEXT,
  expected_date      DATE,
  notes              TEXT,
  matched_visitor_id UUID REFERENCES visitors(id) DEFAULT NULL,
  created_at         TIMESTAMPTZ DEFAULT NOW()
);

-- Aggiungi colonna se la tabella esiste già senza di essa
ALTER TABLE guest_list ADD COLUMN IF NOT EXISTS matched_visitor_id UUID REFERENCES visitors(id) DEFAULT NULL;

ALTER TABLE guest_list ENABLE ROW LEVEL SECURITY;
CREATE POLICY "guest_list_anon_read"   ON guest_list FOR SELECT USING (true);
CREATE POLICY "guest_list_auth_insert" ON guest_list FOR INSERT WITH CHECK (auth.role() = 'authenticated');
CREATE POLICY "guest_list_auth_update" ON guest_list FOR UPDATE USING (auth.role() = 'authenticated');
CREATE POLICY "guest_list_auth_delete" ON guest_list FOR DELETE USING (auth.role() = 'authenticated');

-- Nuove colonne su visitors (tabella reale usata dall'app)
ALTER TABLE visitors
  ADD COLUMN IF NOT EXISTS email             TEXT,
  ADD COLUMN IF NOT EXISTS company           TEXT,
  ADD COLUMN IF NOT EXISTS xatlas_status     TEXT DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS xatlas_user_id    INTEGER DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS guest_id          UUID REFERENCES guest_list(id) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS badge_agreement   BOOLEAN DEFAULT FALSE;

-- xatlas_status valori: NULL | 'pending' | 'active' | 'checked_out'
-- guest_id: valorizzato dal kiosk se il visitatore è in lista ospiti attesi

-- ============================================================
-- POLICY anon UPDATE su record STUB (pre-attivati)
-- Necessaria per permettere al kiosk di completare la firma su
-- visitor records creati in anticipo dall'admin (pre-assegna badge).
-- Solo i record con signature NULL possono essere modificati da anon
-- (= stub pre-attivati). Una volta firmati, immutabili per anon.
-- ============================================================

DROP POLICY IF EXISTS "anon_update_pre_stub" ON visitors;
CREATE POLICY "anon_update_pre_stub" ON visitors
  FOR UPDATE
  USING (signature IS NULL)
  WITH CHECK (true);

-- ============================================================
-- MIGRATION v3 — Anti race-condition + Heartbeat agente
-- Eseguire nel SQL Editor di Supabase Dashboard
-- ============================================================

-- 1) UNIQUE PARTIAL INDEX su badge_number per record attivi
--    Impedisce a due operatori di assegnare lo stesso badge a visitatori diversi.
--    Se un secondo INSERT/UPDATE prova a duplicare un badge in pending/active,
--    PostgreSQL solleva errore 23505 (unique_violation) → admin mostra messaggio.
--    I record con xatlas_status = 'checked_out' (usciti) sono ESCLUSI:
--    il badge è libero e riassegnabile al prossimo visitatore.
CREATE UNIQUE INDEX IF NOT EXISTS visitors_badge_active_unique
  ON visitors (badge_number)
  WHERE badge_number IS NOT NULL
    AND xatlas_status IN ('pending', 'active');

-- 2) Tabella heartbeat agente Python
--    Single-row table: l'agente aggiorna last_heartbeat ad ogni loop (~5s).
--    L'admin legge questo timestamp per mostrare stato connessione.
CREATE TABLE IF NOT EXISTS agent_status (
  id              INTEGER PRIMARY KEY DEFAULT 1,
  last_heartbeat  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  agent_version   TEXT,
  notes           TEXT,
  CONSTRAINT agent_status_singleton CHECK (id = 1)
);

-- Riga iniziale (idempotente)
INSERT INTO agent_status (id, last_heartbeat) VALUES (1, NOW())
  ON CONFLICT (id) DO NOTHING;

ALTER TABLE agent_status ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "agent_status_anon_read"   ON agent_status;
DROP POLICY IF EXISTS "agent_status_auth_read"   ON agent_status;
DROP POLICY IF EXISTS "agent_status_anon_update" ON agent_status;

-- Lettura: chiunque (admin auth + kiosk anon)
CREATE POLICY "agent_status_anon_read" ON agent_status FOR SELECT USING (true);
-- Scrittura: nessuna policy → solo service_role bypassa RLS e scrive
-- (l'agente Python usa la service_key, non la anon key)

-- ============================================================
-- MIGRATION v4 — Eventi + Tracciamento timbrature legale + QR pre-registrazione
-- Eseguire nel SQL Editor di Supabase Dashboard
-- ============================================================

-- 1) TABELLA events: 1 evento attivo alla volta, range di date, QR validity range
CREATE TABLE IF NOT EXISTS events (
  id                UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  name              TEXT NOT NULL,
  event_start_date  DATE NOT NULL,
  event_end_date    DATE NOT NULL,
  qr_valid_from     DATE,                          -- pre-registrazione attiva da (default = oggi)
  daily_open_time   TIME,                          -- opzionale (Phase D futura)
  daily_close_time  TIME,                          -- opzionale (Phase D futura)
  is_active         BOOLEAN DEFAULT FALSE,
  notes             TEXT,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  closed_at         TIMESTAMPTZ,
  CONSTRAINT events_dates_valid CHECK (event_end_date >= event_start_date)
);

-- Constraint: solo 1 evento attivo alla volta
CREATE UNIQUE INDEX IF NOT EXISTS events_only_one_active
  ON events ((TRUE)) WHERE is_active = TRUE;

ALTER TABLE events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "events_anon_read"   ON events;
DROP POLICY IF EXISTS "events_auth_insert" ON events;
DROP POLICY IF EXISTS "events_auth_update" ON events;
DROP POLICY IF EXISTS "events_auth_delete" ON events;
-- Lettura: chiunque (frontend QR mode legge per validare validità)
CREATE POLICY "events_anon_read"   ON events FOR SELECT USING (true);
-- Scrittura: solo authenticated (admin)
CREATE POLICY "events_auth_insert" ON events FOR INSERT WITH CHECK (auth.role() = 'authenticated');
CREATE POLICY "events_auth_update" ON events FOR UPDATE USING (auth.role() = 'authenticated');
CREATE POLICY "events_auth_delete" ON events FOR DELETE USING (auth.role() = 'authenticated');

-- 2) NUOVE COLONNE su visitors: associazione evento + documento di identità
ALTER TABLE visitors
  ADD COLUMN IF NOT EXISTS event_id      UUID REFERENCES events(id) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS event_name    TEXT,                              -- snapshot per archive
  ADD COLUMN IF NOT EXISTS event_date    DATE,                              -- snapshot (event_start_date)
  ADD COLUMN IF NOT EXISTS document_id   TEXT,                              -- numero documento
  ADD COLUMN IF NOT EXISTS document_type TEXT;                              -- 'CI' | 'PASSAPORTO' | 'PATENTE'

CREATE INDEX IF NOT EXISTS idx_visitors_event_id ON visitors(event_id);

-- 3) TABELLA visitor_movements: append-only, prova legale completa di ogni timbratura
CREATE TABLE IF NOT EXISTS visitor_movements (
  id                  BIGSERIAL PRIMARY KEY,
  visitor_id          UUID NOT NULL REFERENCES visitors(id) ON DELETE CASCADE,
  event_id            UUID REFERENCES events(id),
  timestamp           TIMESTAMPTZ NOT NULL,
  direction           TEXT NOT NULL CHECK (direction IN ('entry','exit')),
  source              TEXT DEFAULT 'xatlas',                                -- 'xatlas' | 'manual' | 'midnight_cleanup'
  badge_number        TEXT,
  raw_transaction_id  BIGINT,                                               -- riferimento AXS_DB.transaction.id
  created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS vm_by_visitor ON visitor_movements(visitor_id, "timestamp" DESC);
CREATE INDEX IF NOT EXISTS vm_by_event   ON visitor_movements(event_id,   "timestamp" DESC);

ALTER TABLE visitor_movements ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "vm_auth_read" ON visitor_movements;
-- Lettura: solo admin (i timestamp sono dati personali)
CREATE POLICY "vm_auth_read" ON visitor_movements FOR SELECT USING (auth.role() = 'authenticated');
-- Scrittura: nessuna policy → solo service_role (agente Python) può scrivere

-- 4) TABELLA badge_pool: badge pre-attivi anonimi per assegnazione al volo (Phase B)
CREATE TABLE IF NOT EXISTS badge_pool (
  id              BIGSERIAL PRIMARY KEY,
  badge_number    TEXT NOT NULL,
  xatlas_user_id  INTEGER,                                                  -- popolato da agente quando attiva
  card_id         INTEGER,
  status          TEXT DEFAULT 'preparing' CHECK (status IN ('preparing','available','in_use','released')),
  event_id        UUID REFERENCES events(id),
  visitor_id      UUID REFERENCES visitors(id) DEFAULT NULL,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  activated_at    TIMESTAMPTZ,
  assigned_at     TIMESTAMPTZ
);
-- Solo un'entry "viva" per badge_number (evita duplicati attivi)
CREATE UNIQUE INDEX IF NOT EXISTS badge_pool_active_unique
  ON badge_pool (badge_number)
  WHERE status IN ('preparing','available','in_use');

ALTER TABLE badge_pool ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "badge_pool_auth_all" ON badge_pool;
-- Lettura/Scrittura: solo admin (l'agente Python usa service_role e bypassa)
CREATE POLICY "badge_pool_auth_all" ON badge_pool FOR ALL USING (auth.role() = 'authenticated');

-- ============================================================
-- MIGRATION v5 — Multi-utenza tracking + audit log + pool rename agent
-- Eseguire nel SQL Editor di Supabase Dashboard
-- ============================================================

-- 1) Tracciamento operatore su visitors e badge_pool
ALTER TABLE visitors
  ADD COLUMN IF NOT EXISTS assigned_by    TEXT,           -- email operatore che ha assegnato il badge
  ADD COLUMN IF NOT EXISTS assigned_at    TIMESTAMPTZ,    -- quando il badge è stato assegnato
  ADD COLUMN IF NOT EXISTS xatlas_renamed BOOLEAN DEFAULT FALSE; -- l'agente ha già rinominato l'utente XAtlas (per pool walk-in)

ALTER TABLE badge_pool
  ADD COLUMN IF NOT EXISTS assigned_by TEXT;              -- email operatore che ha consegnato il badge dal pool

-- 2) Tabella guest_list: opzionale event_id per "ospite inatteso aggiunto durante evento"
ALTER TABLE guest_list
  ADD COLUMN IF NOT EXISTS event_id UUID REFERENCES events(id) DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_guest_list_event_id ON guest_list(event_id);

-- 3) Tabella audit_log: traccia delle azioni admin (chi ha fatto cosa, quando, su cosa)
CREATE TABLE IF NOT EXISTS audit_log (
  id          BIGSERIAL PRIMARY KEY,
  user_email  TEXT NOT NULL,
  action      TEXT NOT NULL,                 -- es. 'badge_assign','walkin_register','conclude_visit','event_create','event_start','event_close','pool_add','pool_remove','guest_add','guest_delete'
  entity      TEXT,                          -- 'visitor' | 'event' | 'badge_pool' | 'guest_list'
  entity_id   TEXT,                          -- id (UUID o BIGINT serializzato)
  details     JSONB,                         -- payload contestuale (badge, nome, etc.)
  created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS audit_log_by_user  ON audit_log(user_email, created_at DESC);
CREATE INDEX IF NOT EXISTS audit_log_by_entity ON audit_log(entity, entity_id);
CREATE INDEX IF NOT EXISTS audit_log_recent   ON audit_log(created_at DESC);

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "audit_log_auth_read"   ON audit_log;
DROP POLICY IF EXISTS "audit_log_auth_insert" ON audit_log;
-- Lettura: tutti gli admin (utile per accountability)
CREATE POLICY "audit_log_auth_read"   ON audit_log FOR SELECT USING (auth.role() = 'authenticated');
-- Scrittura: tutti gli admin (chi fa l'azione registra il proprio log)
CREATE POLICY "audit_log_auth_insert" ON audit_log FOR INSERT WITH CHECK (auth.role() = 'authenticated');

-- ============================================================
-- MIGRATION v5b — Anti-duplicate visitor_movements (idempotenza agente)
-- L'agente legge le transazioni recenti AXS_DB ogni 5s; senza dedup la stessa
-- transazione viene scritta più volte in visitor_movements (es. 12 righe per minuto).
-- Soluzione: UNIQUE su raw_transaction_id + insert con on_conflict ignore-duplicates.
-- ============================================================

-- Cleanup: cancella duplicati esistenti tenendo la riga con id minore (la prima inserita)
DELETE FROM visitor_movements vm1
USING visitor_movements vm2
WHERE vm1.id > vm2.id
  AND vm1.raw_transaction_id = vm2.raw_transaction_id
  AND vm1.raw_transaction_id IS NOT NULL;

-- UNIQUE partial: solo per raw_transaction_id valorizzato (le voci manuali senza
-- raw_transaction_id possono comunque coesistere)
CREATE UNIQUE INDEX IF NOT EXISTS visitor_movements_raw_tx_unique
  ON visitor_movements (raw_transaction_id)
  WHERE raw_transaction_id IS NOT NULL;

-- ============================================================
-- MIGRATION v6 — FK badge_pool.visitor_id con ON DELETE SET NULL
-- ============================================================
-- Eliminare un visitor con badge dal pool dava errore FK constraint.
-- Cambiamo la FK per accettare l'eliminazione, mantenendo l'entry pool intatta
-- (visitor_id viene azzerato).

ALTER TABLE badge_pool DROP CONSTRAINT IF EXISTS badge_pool_visitor_id_fkey;
ALTER TABLE badge_pool
  ADD CONSTRAINT badge_pool_visitor_id_fkey
  FOREIGN KEY (visitor_id) REFERENCES visitors(id)
  ON DELETE SET NULL;

-- ============================================================
-- MIGRATION v7 — Coda email per invio QR personali ai partecipanti
-- ============================================================
-- L'admin clicca "Invia QR" su un ospite (o massivo) → INSERT in email_queue.
-- L'agente Python su srvXatlas legge la coda ogni ciclo, invia via SMTP @s2s.it
-- e marca status='sent' o 'failed' (con error).
-- Il QR personale ha ?mode=qr&event=<eid>&guest=<gid>: il frontend precompila
-- l'ospite specifico e blocca dopo registrazione (privacy: niente lista visibile).

CREATE TABLE IF NOT EXISTS email_queue (
  id           BIGSERIAL PRIMARY KEY,
  guest_id     UUID REFERENCES guest_list(id) ON DELETE CASCADE,
  event_id     UUID REFERENCES events(id),
  to_email     TEXT NOT NULL,
  to_name      TEXT,
  subject      TEXT NOT NULL,
  body_html    TEXT NOT NULL,
  qr_url       TEXT,
  status       TEXT DEFAULT 'pending' CHECK (status IN ('pending','sending','sent','failed')),
  error        TEXT,
  attempts     INT DEFAULT 0,
  scheduled_at TIMESTAMPTZ DEFAULT NOW(),
  sent_at      TIMESTAMPTZ,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  created_by   TEXT
);

CREATE INDEX IF NOT EXISTS email_queue_pending  ON email_queue(status, scheduled_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS email_queue_by_guest ON email_queue(guest_id);
CREATE INDEX IF NOT EXISTS email_queue_recent   ON email_queue(created_at DESC);

ALTER TABLE email_queue ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "email_queue_auth_read"   ON email_queue;
DROP POLICY IF EXISTS "email_queue_auth_insert" ON email_queue;
DROP POLICY IF EXISTS "email_queue_auth_update" ON email_queue;
DROP POLICY IF EXISTS "email_queue_auth_delete" ON email_queue;
CREATE POLICY "email_queue_auth_read"   ON email_queue FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "email_queue_auth_insert" ON email_queue FOR INSERT WITH CHECK (auth.role() = 'authenticated');
CREATE POLICY "email_queue_auth_update" ON email_queue FOR UPDATE USING (auth.role() = 'authenticated');
CREATE POLICY "email_queue_auth_delete" ON email_queue FOR DELETE USING (auth.role() = 'authenticated');
-- L'agente Python usa service_role e bypassa RLS per fare update di status.

-- =====================================================
-- MIGRATION v8 — Pre-assegnazione Badge (draft persistente)
-- =====================================================
-- Permette alla segreteria di importare un CSV di partecipanti, compilare i numeri
-- badge in un editor web e salvare il lavoro su DB così da poter chiudere il browser
-- e riprendere in seguito (anche da un altro PC) senza perdere il progresso.
-- Il draft è separato da guest_list: solo dopo la "finalizzazione" (export CSV +
-- import massivo) i record passano in guest_list e i badge vengono pre-attivati.

CREATE TABLE IF NOT EXISTS guest_drafts (
  id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  name         TEXT NOT NULL,                              -- nome draft (es. "Team Building 2026-05-10")
  event_id     UUID REFERENCES events(id) ON DELETE SET NULL,
  status       TEXT DEFAULT 'editing'
                 CHECK (status IN ('editing','finalized','archived')),
  rows         JSONB NOT NULL DEFAULT '[]'::jsonb,         -- array di partecipanti con badge
  row_count    INT GENERATED ALWAYS AS (jsonb_array_length(rows)) STORED,
  created_by   TEXT,
  updated_by   TEXT,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS guest_drafts_status_updated ON guest_drafts(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS guest_drafts_event ON guest_drafts(event_id);

ALTER TABLE guest_drafts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "guest_drafts_auth_read"   ON guest_drafts;
DROP POLICY IF EXISTS "guest_drafts_auth_insert" ON guest_drafts;
DROP POLICY IF EXISTS "guest_drafts_auth_update" ON guest_drafts;
DROP POLICY IF EXISTS "guest_drafts_auth_delete" ON guest_drafts;
CREATE POLICY "guest_drafts_auth_read"   ON guest_drafts FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "guest_drafts_auth_insert" ON guest_drafts FOR INSERT WITH CHECK (auth.role() = 'authenticated');
CREATE POLICY "guest_drafts_auth_update" ON guest_drafts FOR UPDATE USING (auth.role() = 'authenticated');
CREATE POLICY "guest_drafts_auth_delete" ON guest_drafts FOR DELETE USING (auth.role() = 'authenticated');

-- Trigger updated_at automatico
CREATE OR REPLACE FUNCTION guest_drafts_touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS guest_drafts_updated_at ON guest_drafts;
CREATE TRIGGER guest_drafts_updated_at
  BEFORE UPDATE ON guest_drafts
  FOR EACH ROW EXECUTE FUNCTION guest_drafts_touch_updated_at();
