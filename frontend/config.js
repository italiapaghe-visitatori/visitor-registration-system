/**
 * CONFIGURAZIONE - Modifica questi valori per adattare il sistema a qualsiasi contesto
 * Esempi: Hotel, Azienda, Ospedale, Scuola, Palestra, Condominio, Evento
 */

const CONFIG = {
  // ===== IDENTITA =====
  appTitle: 'Registrazione Visitatore',
  headerTitle: 'Registrazione Visitatore',
  logoPath: '../assets/logo-ip.png', // Inserisci logo o lascia vuoto per nascondere
  
  // ===== COLORI (per adattarsi al brand) =====
  colors: {
    primary: '#667eea',      // Colore primario (bottoni, gradienti)
    secondary: '#764ba2',    // Colore secondario
    background: '#f7fafc',   // Sfondo
    text: '#2d3748'          // Testo
  },
  
  // ===== CAMPI VISIBILI =====
  fields: {
    firstName: { enabled: true, label: 'Nome', required: true },
    lastName: { enabled: true, label: 'Cognome', required: true },
    visitDate: { enabled: true, label: 'Data Visita', required: true },
    entryTime: { enabled: true, label: 'Ora Ingresso', required: true },
    exitTime: { enabled: true, label: 'Ora Uscita', required: false },
    personToVisit: { enabled: true, label: 'Persona da Visitare', required: false },
    visitReason: { enabled: true, label: 'Motivo della Visita', required: true },
    badgeNumber: { enabled: true, label: 'Numero Badge', required: false },
    phone: { enabled: true, label: 'Numero di Telefono', required: false },
    department: { enabled: false, label: 'Reparto/Ufficio', required: false },
    vehiclePlate: { enabled: false, label: 'Targa Veicolo', required: false },
    signature: { enabled: true, label: 'Firma del Visitatore', required: false },
    dataConsent: { enabled: true, label: 'Acconsento al trattamento dei dati personali ai sensi del Regolamento UE 2016/679 (GDPR)', required: true }
  },
  
  // ===== MOTIVI VISITA (Alphabetical order + extra coerenti) =====
  visitReasons: [
    { value: '', label: 'Seleziona...' },
    { value: 'Appuntamento di lavoro', label: 'Appuntamento di lavoro' },
    { value: 'Colloquio', label: 'Colloquio' },
    { value: 'Consegna documenti', label: 'Consegna documenti' },
    { value: 'Corso di formazione in aula', label: 'Corso di formazione in aula' },
    { value: 'Fornitore', label: 'Fornitore' },
    { value: 'Incontro di lavoro', label: 'Incontro di lavoro' },
    { value: 'Intervista di lavoro', label: 'Intervista di lavoro' },
    { value: 'Manutenzione/assistenza tecnica', label: 'Manutenzione/assistenza tecnica' },
    { value: 'Prenotazione', label: 'Prenotazione' },
    { value: 'Consegna', label: 'Consegna' },
    { value: 'Visita', label: 'Visita' },
    { value: 'Assistenza clienti', label: 'Assistenza clienti' },
    { value: 'Ritiro documenti', label: 'Ritiro documenti' },
    { value: 'Trasferimento', label: 'Trasferimento' },
    { value: 'Altro', label: 'Altro' }
  ],
  
  // ===== SUPABASE =====
  supabase: {
    url: 'https://sebhatzxsxuafsmbdtsx.supabase.co',
    anonKey: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNlYmhhdHp4c3h1YWZzbWJkdHN4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzczNjM0ODYsImV4cCI6MjA5MjkzOTQ4Nn0.5nvuSf8sxRcVPTEbgQe8mRERvEuGXCYs4fPogzhjYTI'
  },
  
  // ===== CONTESTO (auto-genera placeholder) =====
  context: 'struttura ricettiva' // Es: 'azienda', 'ospedale', 'scuola', 'hotel'
};
