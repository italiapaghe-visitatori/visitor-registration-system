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
