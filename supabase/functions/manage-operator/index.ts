// Edge Function: manage-operator
// =================================
// Gestisce operazioni amministrative su operatori esistenti:
//   action="ban"     → blocca (ban_duration=876000h ≈ 100 anni)
//   action="unban"   → sblocca (ban_duration="none")
//   action="delete"  → elimina definitivamente
//
// Protezioni:
//   - Chiamante deve essere autenticato (Bearer token valido)
//   - NON si può agire su sé stessi
//   - NON si può agire su un super-admin (whitelist SUPER_ADMIN_EMAILS env var,
//     fallback hard-coded: tecnico.gelormini@gmail.com)
//
// Deploy: supabase functions deploy manage-operator --no-verify-jwt
//
// Body JSON atteso:
//   { "email": "target@example.com", "action": "ban" | "unban" | "delete" }

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

// Fallback se SUPER_ADMIN_EMAILS env non è impostata
const DEFAULT_SUPER_ADMINS = ["tecnico.gelormini@gmail.com"];

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ error: "method not allowed" }, 405);

  // 1. Valida token del chiamante
  const authHeader = req.headers.get("Authorization") ?? "";
  const token = authHeader.replace(/^Bearer\s+/i, "").trim();
  if (!token) return json({ error: "Missing Authorization Bearer token" }, 401);

  const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const anonKey    = Deno.env.get("SUPABASE_ANON_KEY")!;

  const userRes = await fetch(`${supabaseUrl}/auth/v1/user`, {
    headers: { Authorization: `Bearer ${token}`, apikey: anonKey },
  });
  if (!userRes.ok) return json({ error: "Invalid or expired token" }, 401);
  const caller = await userRes.json();
  if (!caller?.email) return json({ error: "Token has no email" }, 401);

  // 1bis. Solo super-admin può gestire (ban/unban/delete) operatori
  const superAdmins = (Deno.env.get("SUPER_ADMIN_EMAILS") || DEFAULT_SUPER_ADMINS.join(","))
    .split(",").map(e => e.trim().toLowerCase()).filter(Boolean);
  if (!superAdmins.includes(caller.email.toLowerCase())) {
    return json({ error: "Solo gli amministratori principali possono bloccare/eliminare operatori" }, 403);
  }

  // 2. Parse body
  let body: { email?: string; action?: string };
  try { body = await req.json(); } catch { return json({ error: "Invalid JSON body" }, 400); }
  const targetEmail = (body.email || "").trim().toLowerCase();
  const action      = (body.action || "").trim().toLowerCase();
  if (!targetEmail || !targetEmail.includes("@")) return json({ error: "Email target mancante o non valida" }, 400);
  if (!["ban", "unban", "delete"].includes(action)) return json({ error: "Action deve essere ban | unban | delete" }, 400);

  // 3. Protezioni
  if (targetEmail === caller.email.toLowerCase()) {
    return json({ error: "Non puoi modificare il tuo stesso account" }, 403);
  }
  if (superAdmins.includes(targetEmail)) {
    return json({ error: `${targetEmail} è un super-admin protetto e non può essere modificato` }, 403);
  }

  // 4. Trova l'utente target tramite admin API
  const admin = createClient(supabaseUrl, serviceKey, {
    auth: { autoRefreshToken: false, persistSession: false },
  });

  // listUsers non supporta filter diretto per email → cerchiamo nella prima pagina (1000)
  const { data: list, error: listErr } = await admin.auth.admin.listUsers({ page: 1, perPage: 1000 });
  if (listErr) return json({ error: `Errore lookup utente: ${listErr.message}` }, 500);
  const target = list?.users?.find(u => (u.email || "").toLowerCase() === targetEmail);
  if (!target) return json({ error: `Operatore non trovato: ${targetEmail}` }, 404);

  // 5. Esegui azione
  try {
    if (action === "ban") {
      const { error } = await admin.auth.admin.updateUserById(target.id, { ban_duration: "876000h" });
      if (error) throw error;
      return json({ ok: true, action, email: targetEmail, performed_by: caller.email }, 200);
    }
    if (action === "unban") {
      const { error } = await admin.auth.admin.updateUserById(target.id, { ban_duration: "none" });
      if (error) throw error;
      return json({ ok: true, action, email: targetEmail, performed_by: caller.email }, 200);
    }
    if (action === "delete") {
      const { error } = await admin.auth.admin.deleteUser(target.id);
      if (error) throw error;
      return json({ ok: true, action, email: targetEmail, performed_by: caller.email }, 200);
    }
  } catch (err: any) {
    return json({ error: err?.message || "Errore esecuzione azione" }, 500);
  }

  return json({ error: "Stato imprevisto" }, 500);
});

function json(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status, headers: { ...CORS, "Content-Type": "application/json" },
  });
}
