/**
 * CONFIGURAZIONE - Modifica questi valori per adattare il sistema a qualsiasi contesto
 * Esempi: Hotel, Azienda, Ospedale, Scuola, Palestra, Condominio, Evento
 */

const CONFIG = {
  // ===== IDENTITA =====
  appTitle: 'Registrazione Visitatore',
  headerTitle: 'Registrazione Visitatore',
  logoPath: '../assets/logo-S2S-def.gif', // Inserisci logo o lascia vuoto per nascondere
  
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
    email: { enabled: true, label: 'Email', required: false },
    company: { enabled: true, label: 'Azienda', required: false },
    visitDate: { enabled: false, label: 'Data Visita', required: false },
    entryTime: { enabled: false, label: 'Ora Ingresso', required: false },
    exitTime: { enabled: false, label: 'Ora Uscita', required: false },
    personToVisit: { enabled: true, label: 'Persona da Visitare', required: false },
    visitReason: { enabled: true, label: 'Motivo della Visita', required: true },
    documentType: { enabled: true, label: 'Tipo Documento', required: true },
    documentId:   { enabled: true, label: 'Numero Documento', required: true },
    badgeNumber: { enabled: false, label: 'Numero Badge', required: false },
    phone: { enabled: false, label: 'Numero di Telefono', required: false },
    department: { enabled: false, label: 'Reparto/Ufficio', required: false },
    vehiclePlate: { enabled: false, label: 'Targa Veicolo', required: false },
    signature: { enabled: true, label: 'Firma del Visitatore', required: true },
    dataConsent: {
      enabled: true,
      // Label HTML — include link al PDF Norme di accesso. event.stopPropagation()
      // evita che cliccando sul link si flippi il checkbox.
      label: 'Acconsento al trattamento dei dati personali ai sensi del Regolamento UE 2016/679 (GDPR) e dichiaro di aver letto e accettato le <a href="../assets/S2S_Brochure_Accesso_Immobile.pdf" target="_blank" rel="noopener" class="consent-link" onclick="event.stopPropagation()">📄 Norme di accesso all\'immobile</a> (badge, videosorveglianza, sicurezza, emergenza).',
      required: true
    }
  },
  
  // ===== MOTIVI VISITA (Alphabetical order + extra coerenti) =====
  visitReasons: [
    { value: '', label: 'Seleziona...' },
    { value: 'Appuntamento di lavoro', label: 'Appuntamento di lavoro' },
    { value: 'Colloquio', label: 'Colloquio' },
    { value: 'Consegna documenti', label: 'Consegna documenti' },
    { value: 'Corso di formazione in aula', label: 'Corso di formazione in aula' },
    { value: 'Fornitore', label: 'Fornitore' },
    { value: 'Team Building DVI CL 1e 10', label: 'Team Building DVI CL 1e 10' },
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
  
  // ===== KIOSK PIN (autorizzazione tablet al desk) =====
  // Il tablet kiosk al desk DEVE essere autorizzato una volta inserendo nel browser:
  //   .../frontend/?kiosk_authorize=<PIN>
  // Se il PIN matcha, viene salvato un flag in localStorage e il tablet ricorda
  // l'autorizzazione per sempre. Senza autorizzazione (e senza ?mode=qr&event=...)
  // l'accesso al frontend viene bloccato → impedisce ai visitatori che conoscono
  // l'URL pubblico GitHub Pages di registrarsi al posto di altri.
  // CAMBIA QUESTO PIN ⇩ con uno tuo prima del go-live.
  kioskPIN: 'S2S-2026',

  // ===== SUPABASE =====
  supabase: {
    url: 'https://sebhatzxsxuafsmbdtsx.supabase.co',
    anonKey: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNlYmhhdHp4c3h1YWZzbWJkdHN4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzczNjM0ODYsImV4cCI6MjA5MjkzOTQ4Nn0.5nvuSf8sxRcVPTEbgQe8mRERvEuGXCYs4fPogzhjYTI'
  },
  
  // ===== TIPI DOCUMENTO =====
  documentTypes: [
    { value: '',          label: 'Seleziona...' },
    { value: 'CI',        label: 'Carta d\'Identità' },
    { value: 'PATENTE',   label: 'Patente' },
    { value: 'PASSAPORTO',label: 'Passaporto' },
    { value: 'ALTRO',     label: 'Altro' }
  ],

  // ===== CONTESTO (auto-genera placeholder) =====
  context: 'struttura ricettiva' // Es: 'azienda', 'ospedale', 'scuola', 'hotel'
};
