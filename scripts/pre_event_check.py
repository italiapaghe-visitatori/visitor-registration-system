#!/usr/bin/env python3
"""Pre-event GO/NO-GO check (READ-ONLY).

Sub-progetto D del piano hardening post-MD 15/05/2026.

Uso:
    python scripts/pre_event_check.py --event-id <UUID>
    python scripts/pre_event_check.py --event-name "Team Building DVI"

Esegue una batteria di controlli READ-ONLY su Supabase + AXS_DB Zucchetti per
dare un verdetto GO / WARN / STOP **prima** di aprire il desk a un evento.

Exit code:
    0 = GO  (tutti i check passati o solo WARN tollerati)
    1 = STOP (almeno un check critico fallito)
    2 = errore di esecuzione (config, rete, parametri)

Pre-requisiti:
- Eseguito su srvxatlas (o macchina che ha accesso ad AXS_DB via psycopg2).
- agent_config.ini accessibile (sezioni [supabase] e [axs_db]).
- Tutti i check sono SOLO LETTURA: nessuna modifica viene MAI scritta.
"""

from __future__ import annotations

import argparse
import configparser
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import psycopg2
import requests


ROME = ZoneInfo("Europe/Rome")

# Colori ANSI per output terminale (no dipendenze)
class Color:
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RESET  = "\033[0m"


@dataclass
class CheckResult:
    name: str
    level: str  # "OK" / "WARN" / "STOP"
    message: str
    details: list[str] = field(default_factory=list)


@dataclass
class Config:
    supabase_url: str
    supabase_key: str
    axs_host: str
    axs_port: int
    axs_user: str
    axs_password: str
    axs_dbname: str


def load_config() -> Config:
    """Carica configurazione da agent_config.ini (stessa dell'agente)."""
    cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "agent_config.ini")
    if not os.path.isfile(cfg_path):
        # Fallback: percorso production su srvxatlas
        cfg_path = r"C:\zucchetti-agent\agent_config.ini"

    cfg = configparser.ConfigParser()
    cfg.read(cfg_path, encoding="utf-8")
    try:
        return Config(
            supabase_url=cfg["supabase"]["url"],
            supabase_key=cfg["supabase"]["service_key"],
            axs_host=cfg["axs_db"]["host"],
            axs_port=int(cfg["axs_db"].get("port", "5432")),
            axs_user=cfg["axs_db"]["user"],
            axs_password=cfg["axs_db"]["password"],
            axs_dbname=cfg["axs_db"]["dbname"],
        )
    except KeyError as e:
        print(f"{Color.RED}ERRORE config: chiave mancante {e} in {cfg_path}{Color.RESET}",
              file=sys.stderr)
        sys.exit(2)


# ---------- Helper ----------

def sb_get(cfg: Config, path: str, params: dict | None = None) -> Any:
    """GET su Supabase REST con service_role key. Read-only."""
    headers = {
        "apikey":        cfg.supabase_key,
        "Authorization": f"Bearer {cfg.supabase_key}",
        "Accept":        "application/json",
    }
    url = f"{cfg.supabase_url}/rest/v1/{path}"
    r = requests.get(url, headers=headers, params=params or {}, timeout=15)
    r.raise_for_status()
    return r.json()


def axs_query(cfg: Config, sql: str, params: tuple = ()) -> list[tuple]:
    """SELECT su AXS_DB Zucchetti. SOLO SELECT (vincolo del check)."""
    sql_strip = sql.strip().upper()
    if not sql_strip.startswith("SELECT") and not sql_strip.startswith("WITH"):
        raise ValueError(f"axs_query rifiuta non-SELECT: {sql[:60]!r}")

    conn = psycopg2.connect(
        host=cfg.axs_host, port=cfg.axs_port,
        user=cfg.axs_user, password=cfg.axs_password,
        dbname=cfg.axs_dbname, connect_timeout=10,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())
    finally:
        conn.close()


# ---------- Controlli ----------

def check_event_exists(cfg: Config, event_id: str | None, event_name: str | None) -> tuple[dict | None, CheckResult]:
    """C1 — l'evento esiste, e' attivo, le date sono sensate."""
    if event_id:
        rows = sb_get(cfg, "events", {"id": f"eq.{event_id}", "select": "*", "limit": "1"})
    elif event_name:
        rows = sb_get(cfg, "events", {"name": f"ilike.*{event_name}*", "select": "*", "limit": "5"})
    else:
        return None, CheckResult("Event lookup", "STOP",
                                 "Fornire --event-id o --event-name")

    if not rows:
        return None, CheckResult("Event lookup", "STOP",
                                 f"Evento non trovato (id={event_id} name={event_name!r})")
    if len(rows) > 1:
        return None, CheckResult("Event lookup", "STOP",
                                 f"{len(rows)} eventi corrispondono. Disambiguare con --event-id.",
                                 [f"  {r['id']}  {r['name']}  ({r['event_start_date']})" for r in rows])

    e = rows[0]
    today = datetime.now(ROME).date()
    start = date.fromisoformat(e["event_start_date"])
    end   = date.fromisoformat(e["event_end_date"])
    closed = e.get("closed_at") is not None
    active = e.get("is_active") is True

    details = [
        f"  id:         {e['id']}",
        f"  nome:       {e['name']}",
        f"  date:       {start} → {end}",
        f"  is_active:  {active}",
        f"  closed_at:  {e.get('closed_at')}",
    ]

    if closed:
        return e, CheckResult("Event lookup", "STOP", "Evento chiuso. No-go.", details)
    if end < today:
        return e, CheckResult("Event lookup", "STOP",
                              f"event_end_date {end} nel passato (oggi {today})", details)
    if start > today + timedelta(days=14):
        return e, CheckResult("Event lookup", "WARN",
                              f"event_start_date {start} oltre 14gg, check prematuro", details)

    return e, CheckResult("Event lookup", "OK", f"Evento valido, inizia {start}", details)


def check_visitors_supabase(cfg: Config, event: dict) -> tuple[list[dict], CheckResult]:
    """C2 — i visitatori dell'evento esistono su Supabase, con badge."""
    visitors = sb_get(cfg, "visitors", {
        "event_id": f"eq.{event['id']}",
        "select":   "id,first_name,last_name,badge_number,xatlas_status,signature,event_id",
        "limit":    "500",
    })
    n_total = len(visitors)
    n_with_badge = sum(1 for v in visitors if v.get("badge_number"))
    n_signed = sum(1 for v in visitors if v.get("signature"))
    n_active = sum(1 for v in visitors if v.get("xatlas_status") == "active")

    details = [
        f"  visitatori totali:   {n_total}",
        f"  con badge_number:    {n_with_badge}",
        f"  firmati:             {n_signed}",
        f"  xatlas_status=active:{n_active}",
    ]

    if n_total == 0:
        return [], CheckResult("Visitors Supabase", "STOP",
                               "Nessun visitatore per questo evento. Pre-assegnazione mancante?", details)
    if n_with_badge < n_total:
        miss = n_total - n_with_badge
        return visitors, CheckResult("Visitors Supabase", "WARN",
                                     f"{miss} visitatori senza badge_number (walk-in attesi?)", details)

    return visitors, CheckResult("Visitors Supabase", "OK", f"{n_total} visitatori, tutti con badge", details)


def check_axs_vis_users(cfg: Config, event: dict, supabase_visitors: list[dict]) -> CheckResult:
    """C3 — per ogni badge in Supabase esiste l'utente VIS{badge} in AXS_DB con validity OK."""
    badges_in_sb = sorted({str(v["badge_number"]).strip() for v in supabase_visitors if v.get("badge_number")})
    if not badges_in_sb:
        return CheckResult("AXS VIS users", "OK", "Nessun badge da verificare")

    placeholders = ",".join(["%s"] * len(badges_in_sb))
    rows = axs_query(cfg, f"""
        SELECT regexp_replace(identifier, '^VIS', '') AS badge,
               id, validity_start::date AS vs, validity_end::date AS ve, enabled
          FROM external_user
         WHERE identifier LIKE 'VIS%%'
           AND regexp_replace(identifier, '^VIS', '') IN ({placeholders})
        """, tuple(badges_in_sb))

    by_badge = {r[0]: r for r in rows}
    end = date.fromisoformat(event["event_end_date"])
    today = datetime.now(ROME).date()

    missing = [b for b in badges_in_sb if b not in by_badge]
    expired = []
    not_enabled = []
    for b, (_, uid, vs, ve, en) in by_badge.items():
        if ve < end:
            expired.append((b, ve))
        if not en:
            not_enabled.append(b)

    details = [
        f"  badge Supabase:        {len(badges_in_sb)}",
        f"  utenti VIS in AXS:     {len(by_badge)}",
        f"  mancanti in AXS:       {len(missing)} {missing[:5] if missing else ''}",
        f"  validity_end < event_end ({end}): {len(expired)}",
        f"  enabled=false:         {len(not_enabled)}",
    ]
    if expired:
        details.append("  -- VIS scaduti prima dell'evento --")
        for b, ve in expired[:10]:
            details.append(f"     VIS{b}  scade {ve}")
        if len(expired) > 10:
            details.append(f"     ... e altri {len(expired)-10}")

    if missing or expired or not_enabled:
        # STOP se almeno 1 scaduto/mancante/disabled => evento NON puo' aprire
        return CheckResult("AXS VIS users", "STOP",
                           f"{len(missing)} mancanti, {len(expired)} scaduti, {len(not_enabled)} disabilitati. "
                           "Lanciare refresh tramite recreate (xatlas_renamed=false) prima dell'evento.",
                           details)

    return CheckResult("AXS VIS users", "OK",
                       f"Tutti i {len(badges_in_sb)} badge attivi e validi fino a {end}+", details)


def check_name_consistency(cfg: Config, supabase_visitors: list[dict]) -> CheckResult:
    """C4 — confronto nome Supabase vs nome utente Zucchetti per badge.

    Pattern del mismatch SICILIANO/Romano Elisa 759039 il 15/05/2026.
    """
    badges = sorted({str(v["badge_number"]).strip() for v in supabase_visitors if v.get("badge_number")})
    if not badges:
        return CheckResult("Name consistency Supabase↔Zucchetti", "OK", "Nessun badge da confrontare")

    placeholders = ",".join(["%s"] * len(badges))
    rows = axs_query(cfg, f"""
        SELECT regexp_replace(identifier, '^VIS', '') AS badge, surname, name
          FROM external_user
         WHERE identifier LIKE 'VIS%%'
           AND regexp_replace(identifier, '^VIS', '') IN ({placeholders})
        """, tuple(badges))
    axs_by_badge = {r[0]: (r[1] or "", r[2] or "") for r in rows}

    def norm(s: str) -> set[str]:
        return {p for p in (s or "").upper().replace("'", " ").split() if p}

    mismatches = []
    clean = 0
    for v in supabase_visitors:
        b = str(v.get("badge_number") or "").strip()
        if not b or b not in axs_by_badge:
            continue
        ax_sn, ax_nm = axs_by_badge[b]
        sb_words = norm(v.get("last_name", "") + " " + v.get("first_name", ""))
        ax_words = norm(ax_sn + " " + ax_nm)
        # Se la differenza simmetrica e' vuota o solo variazioni minori (uno e' subset dell'altro) -> match
        if sb_words == ax_words or sb_words.issubset(ax_words) or ax_words.issubset(sb_words):
            clean += 1
        else:
            mismatches.append((b,
                               (v.get("last_name", "") + " " + v.get("first_name", "")).strip(),
                               (ax_sn + " " + ax_nm).strip()))

    details = [f"  puliti: {clean}",
               f"  mismatch: {len(mismatches)}"]
    for b, sb, ax in mismatches[:10]:
        details.append(f"     badge {b:>8} | SB: {sb:<30} | ZK: {ax}")
    if len(mismatches) > 10:
        details.append(f"     ... e altri {len(mismatches)-10}")

    if mismatches:
        return CheckResult("Name consistency Supabase↔Zucchetti", "WARN",
                           f"{len(mismatches)} mismatch (verificare se varianti innocue o veri swap)", details)
    return CheckResult("Name consistency Supabase↔Zucchetti", "OK",
                       f"{clean} nomi coerenti tra Supabase e Zucchetti", details)


def check_employees_untouched(cfg: Config) -> CheckResult:
    """C5 — sanity: i dipendenti (internal_user) non sono stati toccati dalla nostra logica.

    Non e' un check pre-evento *per* l'evento; e' un check globale di sicurezza:
    verifica che internal_user esiste e non e' vuoto, e che external_user non
    contiene non-VIS (l'agente lavora solo nel namespace VIS).
    """
    rows = axs_query(cfg, """
        SELECT 'internal_user_count'   , count(*)::text FROM internal_user
        UNION ALL
        SELECT 'external_user_VIS'     , count(*)::text FROM external_user WHERE identifier LIKE 'VIS%'
        UNION ALL
        SELECT 'external_user_non_VIS' , count(*)::text FROM external_user
              WHERE identifier NOT LIKE 'VIS%' OR identifier IS NULL
        """)
    stats = {r[0]: int(r[1]) for r in rows}
    details = [f"  {k}: {v}" for k, v in stats.items()]

    if stats.get("internal_user_count", 0) == 0:
        return CheckResult("Employees & namespace", "STOP",
                           "internal_user e' vuoto! Possibile catastrofe — fermarsi.", details)
    if stats.get("external_user_non_VIS", 0) > 0:
        # Solo informativo: potrebbe essere esistenza legacy, ma vale segnalare
        return CheckResult("Employees & namespace", "WARN",
                           f"{stats['external_user_non_VIS']} external_user non-VIS (legacy?)", details)

    return CheckResult("Employees & namespace", "OK",
                       f"{stats['internal_user_count']} dipendenti, namespace VIS isolato",
                       details)


def check_auth_group(cfg: Config) -> CheckResult:
    """C6 — il gruppo VISITATORI (auth_group 249) esiste ed e' coerente."""
    rows = axs_query(cfg, """
        SELECT g.id, g.authorizations_list
          FROM authorizations_group g
         WHERE g.id = 249
        """)
    if not rows:
        return CheckResult("Auth group VISITATORI (249)", "STOP",
                           "Gruppo 249 non esiste in AXS_DB",
                           [])
    return CheckResult("Auth group VISITATORI (249)", "OK",
                       f"Gruppo 249 presente, authorizations={rows[0][1]}",
                       [f"  id 249, auth list = {rows[0][1]}"])


# ---------- Main ----------

def emit(c: CheckResult) -> None:
    color = {"OK": Color.GREEN, "WARN": Color.YELLOW, "STOP": Color.RED}.get(c.level, "")
    print(f"  [{color}{c.level:>4}{Color.RESET}] {Color.BOLD}{c.name}{Color.RESET} — {c.message}")
    for d in c.details:
        print(f"        {Color.DIM}{d}{Color.RESET}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Pre-event GO/NO-GO check (read-only)")
    ap.add_argument("--event-id", help="UUID evento Supabase")
    ap.add_argument("--event-name", help="filtro ILIKE su events.name")
    args = ap.parse_args()

    if not args.event_id and not args.event_name:
        print(f"{Color.RED}Specificare --event-id o --event-name{Color.RESET}", file=sys.stderr)
        return 2

    cfg = load_config()

    print(f"\n{Color.BOLD}════════ PRE-EVENT CHECK ════════{Color.RESET}")
    print(f"  Ora: {datetime.now(ROME).strftime('%Y-%m-%d %H:%M:%S %Z')}\n")

    results: list[CheckResult] = []

    try:
        event, r1 = check_event_exists(cfg, args.event_id, args.event_name)
        results.append(r1); emit(r1)
        if not event or r1.level == "STOP":
            print(f"\n{Color.RED}{Color.BOLD}STOP{Color.RESET}: evento non utilizzabile. Verdetto finale: STOP.\n")
            return 1

        visitors, r2 = check_visitors_supabase(cfg, event)
        results.append(r2); emit(r2)

        if visitors:
            r3 = check_axs_vis_users(cfg, event, visitors)
            results.append(r3); emit(r3)

            r4 = check_name_consistency(cfg, visitors)
            results.append(r4); emit(r4)

        r5 = check_employees_untouched(cfg)
        results.append(r5); emit(r5)

        r6 = check_auth_group(cfg)
        results.append(r6); emit(r6)

    except Exception as e:
        print(f"\n{Color.RED}ERRORE: {e}{Color.RESET}", file=sys.stderr)
        return 2

    # Verdetto
    print()
    n_stop = sum(1 for r in results if r.level == "STOP")
    n_warn = sum(1 for r in results if r.level == "WARN")
    n_ok   = sum(1 for r in results if r.level == "OK")
    print(f"  {Color.GREEN}OK={n_ok}{Color.RESET}  "
          f"{Color.YELLOW}WARN={n_warn}{Color.RESET}  "
          f"{Color.RED}STOP={n_stop}{Color.RESET}")

    if n_stop > 0:
        print(f"\n{Color.RED}{Color.BOLD}VERDETTO: STOP — risolvere le anomalie critiche prima di aprire il desk.{Color.RESET}\n")
        return 1

    if n_warn > 0:
        print(f"\n{Color.YELLOW}{Color.BOLD}VERDETTO: GO con riserva — controlla i WARN sopra.{Color.RESET}\n")
        return 0

    print(f"\n{Color.GREEN}{Color.BOLD}VERDETTO: GO — tutti i check passati.{Color.RESET}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
