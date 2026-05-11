# Edge Function: manage-operator

Gestisce le operazioni amministrative su operatori già esistenti (ban / unban / delete) dal modal "Operatori" del pannello admin.

## Azioni supportate

| action | Effetto | Reversibile |
|--------|---------|-------------|
| `ban` | Blocca l'operatore per 100 anni (`ban_duration=876000h`). Non può più fare login. | Sì (`unban`) |
| `unban` | Rimuove il blocco. Riprende a poter fare login. | — |
| `delete` | Elimina definitivamente l'utente da `auth.users` + cascade. | **NO** |

## Protezioni

- Chiamante deve essere autenticato (Bearer token valido in `auth.users`)
- Non puoi modificare il tuo stesso account
- Non puoi modificare un **super-admin** (whitelist via env var `SUPER_ADMIN_EMAILS`, fallback hard-coded `tecnico.gelormini@gmail.com`)

## Configurazione opzionale

Per estendere la whitelist dei super-admin (es. aggiungere un secondo admin protetto):

```bash
supabase secrets set SUPER_ADMIN_EMAILS="tecnico.gelormini@gmail.com,altro.admin@s2s.it"
```

I valori sono case-insensitive e separati da virgola.

## Deploy

```bash
supabase functions deploy manage-operator --no-verify-jwt
```

Flag `--no-verify-jwt` perché la function valida il token internamente per leggere l'email del chiamante (utile per audit + auto-protezione).

## Body atteso

```json
{ "email": "ester.ferraro@iol.it", "action": "ban" }
```

## Risposte

- `200 OK` → `{ "ok": true, "action": "...", "email": "...", "performed_by": "..." }`
- `400` → email/action mancanti o invalidi
- `401` → token mancante/invalido
- `403` → tentativo su sé stessi o su super-admin
- `404` → operatore non trovato
- `500` → errore Supabase Admin API

## Audit

Tutte le chiamate vanno tracciate lato client in `audit_log` con action `operator_ban`, `operator_unban`, `operator_delete` + entità email target + dettagli JSON.
