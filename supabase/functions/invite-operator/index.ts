// Edge Function: invite-operator
// =================================
// Invia un'email di invito a un nuovo operatore admin. Richiede che il
// chiamante sia già un operatore autenticato (Bearer token valido).
//
// Deploy: supabase functions deploy invite-operator --no-verify-jwt
// (no-verify-jwt perché validiamo noi il token internamente per leggere l'email
// del chiamante per audit log; in alternativa rimuovi --no-verify-jwt per
// affidare la validazione a Supabase ma perdi l'email caller).

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

// Fallback se SUPER_ADMIN_EMAILS env non è impostata
const DEFAULT_SUPER_ADMINS = ["tecnico.gelormini@gmail.com"];
function getSuperAdmins(): string[] {
  return (Deno.env.get("SUPER_ADMIN_EMAILS") || DEFAULT_SUPER_ADMINS.join(","))
    .split(",").map(e => e.trim().toLowerCase()).filter(Boolean);
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "method not allowed" }), {
      status: 405, headers: { ...CORS, "Content-Type": "application/json" },
    });
  }

  // 1. Valida il token del chiamante (deve essere un operatore admin)
  const authHeader = req.headers.get("Authorization") ?? "";
  const token = authHeader.replace(/^Bearer\s+/i, "").trim();
  if (!token) {
    return json({ error: "Missing Authorization Bearer token" }, 401);
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY")!;

  // Verifica il token via auth/v1/user con anon key
  const userRes = await fetch(`${supabaseUrl}/auth/v1/user`, {
    headers: { Authorization: `Bearer ${token}`, apikey: anonKey },
  });
  if (!userRes.ok) return json({ error: "Invalid or expired token" }, 401);
  const caller = await userRes.json();
  if (!caller?.email) return json({ error: "Token has no email" }, 401);

  // 1bis. Solo super-admin può invitare nuovi operatori
  const superAdmins = getSuperAdmins();
  if (!superAdmins.includes(caller.email.toLowerCase())) {
    return json({ error: "Solo gli amministratori principali possono invitare nuovi operatori" }, 403);
  }

  // 2. Parsing input
  let body: { email?: string; display_name?: string; redirect_to?: string };
  try { body = await req.json(); } catch { return json({ error: "Invalid JSON body" }, 400); }
  const email = (body.email || "").trim().toLowerCase();
  if (!email || !email.includes("@")) {
    return json({ error: "Email mancante o non valida" }, 400);
  }
  const displayName = (body.display_name || "").trim() || null;
  const redirectTo = body.redirect_to || null;

  // 3. Chiamata admin API per invitare (richiede service_role)
  const admin = createClient(supabaseUrl, serviceKey, {
    auth: { autoRefreshToken: false, persistSession: false },
  });

  const { data, error } = await admin.auth.admin.inviteUserByEmail(email, {
    data: displayName ? { display_name: displayName } : undefined,
    redirectTo: redirectTo || undefined,
  });

  if (error) {
    // Gestione errore comune: utente già esistente
    if (error.message?.includes("already") || error.status === 422) {
      return json({ error: `Email già registrata: ${email}` }, 409);
    }
    return json({ error: error.message || "Errore invio invito" }, 500);
  }

  return json({
    ok: true,
    user_id: data?.user?.id || null,
    email,
    invited_by: caller.email,
  }, 200);
});

function json(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status, headers: { ...CORS, "Content-Type": "application/json" },
  });
}
