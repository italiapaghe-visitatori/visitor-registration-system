"""
Test rapido connessioni - Zucchetti Bridge Agent.

Verifica che Supabase, AXS_DB e XAtlas siano raggiungibili e configurati
correttamente PRIMA di avviare l'agente in produzione.

Uso:
    pip install -r requirements.txt
    python test_connections.py
"""

import configparser
import os
import sys

import psycopg2
import requests


GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def ok(msg):    print(f"{GREEN}[OK]{RESET} {msg}")
def fail(msg):  print(f"{RED}[ERRORE]{RESET} {msg}")
def warn(msg):  print(f"{YELLOW}[WARN]{RESET} {msg}")
def section(t): print(f"\n{CYAN}{BOLD}=== {t} ==={RESET}")


def main():
    # Su Windows abilita codici ANSI nel cmd
    if os.name == "nt":
        os.system("")

    _dir     = os.path.dirname(os.path.abspath(__file__))
    cfg_path = os.path.join(_dir, "agent_config.ini")

    if not os.path.exists(cfg_path):
        fail(f"agent_config.ini non trovato in {_dir}")
        sys.exit(1)

    cfg = configparser.ConfigParser()
    cfg.read(cfg_path, encoding="utf-8")

    # ── 1. Supabase ────────────────────────────────────────────────────────
    section("1. Supabase")
    sb_url = cfg["supabase"]["url"]
    sb_key = cfg["supabase"]["service_key"]

    if "INSERIRE" in sb_key:
        fail("service_key è ancora il placeholder. Riempi agent_config.ini")
        sys.exit(1)

    try:
        r = requests.get(
            f"{sb_url}/rest/v1/visitors?select=id,first_name,last_name,xatlas_status&limit=3",
            headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}"},
            timeout=10,
        )
        if r.ok:
            data = r.json()
            ok(f"Supabase raggiungibile ({r.status_code}). Visitor in tabella: {len(data)} mostrati")
            # Conta pending e active
            r2 = requests.get(
                f"{sb_url}/rest/v1/visitors?select=xatlas_status",
                headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}"},
                timeout=10,
            )
            if r2.ok:
                rows    = r2.json()
                pending = sum(1 for v in rows if v.get("xatlas_status") == "pending")
                active  = sum(1 for v in rows if v.get("xatlas_status") == "active")
                ok(f"Pending: {pending} | Active: {active} | Totale visitor: {len(rows)}")
        else:
            fail(f"Supabase {r.status_code}: {r.text[:200]}")
            sys.exit(1)
    except Exception as e:
        fail(f"Supabase non raggiungibile: {e}")
        sys.exit(1)

    # ── 2. AXS_DB ──────────────────────────────────────────────────────────
    section("2. AXS_DB (PostgreSQL)")
    db = dict(
        host=cfg["axs_db"]["host"],
        port=int(cfg["axs_db"].get("port", "5432")),
        dbname=cfg["axs_db"]["dbname"],
        user=cfg["axs_db"]["user"],
        password=cfg["axs_db"].get("password", ""),
    )

    try:
        conn = psycopg2.connect(**db)
        cur  = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM card;")
        nc = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM transaction;")
        nt = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM external_user;")
        ne = cur.fetchone()[0]
        cur.execute("SELECT MAX(event_timestamp) FROM transaction;")
        last_ts = cur.fetchone()[0]
        cur.close()
        conn.close()
        ok(f"AXS_DB connesso → {nc} card, {nt} transaction, {ne} external_user")
        ok(f"Ultima transazione: {last_ts}")
    except Exception as e:
        fail(f"AXS_DB: {e}")
        sys.exit(1)

    # ── 3. XAtlas login ────────────────────────────────────────────────────
    section("3. XAtlas API")
    xa_base = cfg["xatlas"]["base_url"]
    xa_user = cfg["xatlas"]["username"]
    xa_pass = cfg["xatlas"]["password"]

    if "INSERIRE" in xa_pass:
        fail("password XAtlas ancora placeholder. Riempi agent_config.ini")
        sys.exit(1)

    s = requests.Session()
    try:
        # Step 1: GET pagina login per JSESSIONID
        s.get(f"{xa_base}/web/login", timeout=10)
        # Step 2: POST credenziali form-urlencoded
        r = s.post(
            f"{xa_base}/web/login",
            data={"username": xa_user, "password": xa_pass, "submit": "Accedi"},
            allow_redirects=False,
            timeout=10,
        )
        if r.status_code in (302, 303):
            loc = r.headers.get("Location", "")
            if "login" not in loc.lower():
                ok(f"XAtlas login OK → redirect a {loc}")
            else:
                fail(f"XAtlas: credenziali rifiutate (redirect a {loc})")
                sys.exit(1)
        else:
            fail(f"XAtlas login: status inatteso {r.status_code}")
            sys.exit(1)
    except Exception as e:
        fail(f"XAtlas non raggiungibile: {e}")
        sys.exit(1)

    # ── 4. Lookup card di test ─────────────────────────────────────────────
    section("4. Lookup card_id (badge di test)")
    test_badge = "161083"  # Baudo Pippo
    try:
        conn = psycopg2.connect(**db)
        cur  = conn.cursor()
        cur.execute(
            """
            SELECT c.id, c.user_id, c.clear_code, c.enabled
            FROM card c
            WHERE c.clear_code = %s
            LIMIT 1;
            """,
            (test_badge,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            ok(f"Card {test_badge} trovata: id={row[0]} user_id={row[1]} enabled={row[3]}")
        else:
            warn(f"Card {test_badge} non trovata - verifica un badge esistente nel tuo sistema")
    except Exception as e:
        fail(f"Lookup card: {e}")

    # ── 5. Verifica colonne visitors ──────────────────────────────────────
    section("5. Schema Supabase visitors (colonne richieste)")
    try:
        r = requests.get(
            f"{sb_url}/rest/v1/visitors?select=id,badge_number,xatlas_status,xatlas_user_id,entry_time,exit_time,visit_date,company,guest_id&limit=1",
            headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}"},
            timeout=10,
        )
        if r.ok:
            ok("Tutte le colonne necessarie presenti su visitors (badge_number, xatlas_status, xatlas_user_id, entry_time, exit_time, company, guest_id)")
        else:
            fail(f"Schema visitors: {r.status_code} {r.text[:200]}")
    except Exception as e:
        fail(f"Verifica schema: {e}")

    print(f"\n{GREEN}{BOLD}=== TEST COMPLETATO ===")
    print(f"Se tutti i test sono OK, lancia l'agente in debug:{RESET}")
    print("    python zucchetti_agent.py debug\n")


if __name__ == "__main__":
    main()
