# Visitor Registration System

Piattaforma per la registrazione visitatori in strutture ricettive.

## Struttura
- `supabase/schema.sql` - Schema database
- `frontend/` - Modulo registrazione visitatori
- `admin/` - Backend gestione e filtri

## Setup

### 1. Supabase
1. Crea progetto su https://supabase.com
2. Esegui `supabase/schema.sql` in SQL Editor
3. In Settings > API copia URL e Anon Key

### 2. Frontend (Modulo Registrazione)
In `frontend/index.html` sostituisci:
- `YOUR_SUPABASE_URL` con la tua URL
- `YOUR_SUPABASE_ANON_KEY` con la tua Anon Key
- Aggiungi logo aziendale (vedi sezione Personalizzazione)

### 3. Admin Panel
In `admin/index.html` sostituisci le stesse credenziali Supabase.
Il pannello permette filtri per data, nome, motivo visita.

### 4. GitHub
1. Crea repository su GitHub
2. Carica i file
3. Abilita GitHub Pages per il frontend

## Personalizzazione
- Logo: sostituisci `src=""` nell'img con URL logo aziendale
- Voci aggiuntive: modifica le option in `select#visit_reason`
- Colori: modifica le variabili CSS nel tag style

## Campi Modulo (JotForm + personalizzazione)
- Nome e Cognome
- Data Visita
- Ora Ingresso / Uscita
- Persona da Visitare
- Motivo Visita (incluso "Corso formazione in Aula")
- Numero Badge
- Note
- Consenso Dati (GDPR)
- Firma
