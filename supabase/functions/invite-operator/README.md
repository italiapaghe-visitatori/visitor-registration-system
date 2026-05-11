# Edge Function: invite-operator

Invia un'email di invito automatica a un nuovo operatore admin direttamente
dal modal "Operatori" del pannello web, senza dover passare dal dashboard
Supabase.

## Cosa fa

Quando un admin loggato inserisce email + nome e clicca "Invita operatore":

1. La function valida il Bearer token del chiamante (deve essere autenticato)
2. Chiama `auth.admin.inviteUserByEmail()` (richiede service_role key,
   esposta solo lato server)
3. Supabase invia all'email un link con scadenza 24h
4. L'operatore clicca il link, sceglie la sua password, accede

## Deploy (una tantum, ~3 minuti)

Prerequisiti:

- Supabase CLI installato: <https://supabase.com/docs/guides/cli>
- Logged in: `supabase login`
- Linked al progetto: `supabase link --project-ref sebhatzxsxuafsmbdtsx`

Deploy:

```bash
cd visitor-registration-system
supabase functions deploy invite-operator --no-verify-jwt
```

Il flag `--no-verify-jwt` è importante: la function valida il token
internamente per ottenere l'email del chiamante (utile per audit), ma non
richiede a Supabase di pre-validarlo (altrimenti perdiamo accesso al body).

Le env variables (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
`SUPABASE_ANON_KEY`) sono iniettate automaticamente da Supabase: non serve
configurarle.

## Verifica deploy

```bash
supabase functions list
```

Deve mostrare `invite-operator` come deployed.

Test rapido (dal browser, dopo login admin):

```js
const token = localStorage.getItem('sb-access-token');
fetch('https://sebhatzxsxuafsmbdtsx.supabase.co/functions/v1/invite-operator', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: 'test@example.com', display_name: 'Test User' })
}).then(r => r.json()).then(console.log);
```

## Configurazione email Supabase (consigliata)

Per avere email di invito ben formattate in italiano:

1. Dashboard Supabase → Authentication → Email Templates
2. Personalizza il template "Invite user" con testo italiano (vedi sotto)
3. Authentication → URL Configuration → imposta `Site URL` =
   `https://italiapaghe-visitatori.github.io/visitor-registration-system/admin/`
4. (Opzionale) Authentication → SMTP Settings → configura M365 Graph API
   (le stesse credenziali usate per QR personali) per evitare il limite
   30 email/ora del SMTP gratuito Supabase

Template suggerito (Authentication → Email Templates → Invite user):

```
Oggetto: Invito ad accedere a Gestione Visitatori S2S

Ciao,

sei stato invitato come operatore del sistema Gestione Visitatori di Service
to Service Srl. Clicca il link qui sotto per scegliere la tua password e
iniziare:

{{ .ConfirmationURL }}

Il link scade tra 24 ore. Se non l'hai richiesto, ignora questa email.

Per assistenza scrivi a: tecnico.gelormini@gmail.com
```

## Fallback se non deployata

Se la function non è disponibile, il modal Operatori mostra un avviso e
guida l'admin a fare l'invito manualmente dal dashboard Supabase. Niente
si rompe.

## Sicurezza

- Service role key MAI esposto al browser (resta solo nell'env della
  function)
- Il chiamante deve essere un operatore autenticato (token valido in
  auth.users)
- Tutti gli inviti tracciati in audit_log con `operator_invite` (action),
  email invitata + email invitante
