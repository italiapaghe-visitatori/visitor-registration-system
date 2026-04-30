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
  ADD COLUMN IF NOT EXISTS email          TEXT,
  ADD COLUMN IF NOT EXISTS xatlas_status  TEXT DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS xatlas_user_id INTEGER DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS guest_id       UUID REFERENCES guest_list(id) DEFAULT NULL;

-- xatlas_status valori: NULL | 'pending' | 'active' | 'checked_out'
-- guest_id: valorizzato dal kiosk se il visitatore è in lista ospiti attesi
