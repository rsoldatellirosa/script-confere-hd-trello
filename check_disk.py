"""
check_disk.py — Hapolo Server Disk Monitor
Roda no Windows CMD, Linux ou Mac.

Instalacao (uma vez so):
    pip install paramiko requests python-dotenv

Uso:
    1. Copie o arquivo .env.example para .env
    2. Preencha o .env com as credenciais reais
    3. python check_disk.py
"""

import paramiko
import csv
import os
import sys
import requests
import time
import json
from datetime import datetime
from dotenv import load_dotenv

# Carrega variaveis do arquivo .env
load_dotenv()

# =============================================================================
# CONFIGURACOES — lidas do .env
# =============================================================================
SSH_PORT        = int(os.getenv("SSH_PORT", "22"))
SSH_USER        = os.getenv("SSH_USER", "root")
SSH_TIMEOUT     = int(os.getenv("SSH_TIMEOUT", "10"))
ALERT_THRESHOLD = int(os.getenv("ALERT_THRESHOLD", "70"))

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "disk_reports")
TIMESTAMP  = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
CSV_FILE   = os.path.join(OUTPUT_DIR, f"disk_report_{TIMESTAMP}.csv")
LATEST     = os.path.join(OUTPUT_DIR, "disk_report_LATEST.csv")

# =============================================================================
# TRELLO — lido do .env
# =============================================================================
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY", "")
TRELLO_TOKEN   = os.getenv("TRELLO_TOKEN", "")
TRELLO_CARD_ID = os.getenv("TRELLO_CARD_ID", "")
CHECKLIST_1_ID = os.getenv("CHECKLIST_1_ID", "")
CHECKLIST_2_ID = os.getenv("CHECKLIST_2_ID", "")

# =============================================================================
# SERVIDORES — lidos do arquivo servers.json
# Formato: [{"name": "NOME", "password": "SENHA", "ip": "IP"}, ...]
# =============================================================================
_SERVERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servers.json")

def load_servers():
    if not os.path.exists(_SERVERS_FILE):
        print(f"ERRO: Arquivo {_SERVERS_FILE} nao encontrado.")
        print("Copie o servers.json.example para servers.json e preencha com os dados reais.")
        sys.exit(1)
    with open(_SERVERS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return [(s["name"], s["password"], s["ip"]) for s in data]

# =============================================================================
# CHECKLIST ITEMS — lidos do arquivo checklist_items.json
# Formato: {"IP": "TRELLO_ITEM_ID", ...}
# =============================================================================
_CHECKLIST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "checklist_items.json")

def load_checklist_items():
    if not os.path.exists(_CHECKLIST_FILE):
        print(f"ERRO: Arquivo {_CHECKLIST_FILE} nao encontrado.")
        print("Copie o checklist_items.json.example para checklist_items.json e preencha com os IDs reais.")
        sys.exit(1)
    with open(_CHECKLIST_FILE, encoding="utf-8") as f:
        return json.load(f)

# =============================================================================
# CORES ANSI (funcionam no CMD Windows 10+)
# =============================================================================
RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

if sys.platform == "win32":
    os.system("color")

SKIP_FS = ("tmpfs", "devtmpfs", "udev", "cgroupfs", "overlay", "none")

# =============================================================================
# FUNCOES SSH
# =============================================================================

def check_server(name, password, ip):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=ip,
            port=SSH_PORT,
            username=SSH_USER,
            password=password,
            timeout=SSH_TIMEOUT,
            allow_agent=False,
            look_for_keys=False,
        )
        _, stdout, _ = client.exec_command(
            "df -h --output=source,size,used,avail,pcent,target 2>/dev/null | tail -n +2"
        )
        output = stdout.read().decode(errors="replace")
        client.close()
        return output, None
    except Exception as e:
        return None, str(e)


def parse_df(output):
    rows = []
    for line in output.strip().splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        fs, size, used, avail, pct_raw, mount = (
            parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
        )
        if any(fs.startswith(s) for s in SKIP_FS):
            continue
        try:
            pct = int(pct_raw.replace("%", ""))
        except ValueError:
            pct = -1
        rows.append({
            "filesystem": fs,
            "size": size,
            "used": used,
            "available": avail,
            "use_pct": pct,
            "use_pct_str": pct_raw,
            "mountpoint": mount,
        })
    return rows


def color_pct(pct):
    if pct < 0:
        return YELLOW + "??%" + RESET
    if pct >= ALERT_THRESHOLD:
        return RED + f"{pct}%" + RESET
    return GREEN + f"{pct}%" + RESET


# =============================================================================
# FUNCOES TRELLO
# =============================================================================

def trello_params():
    return {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}


def update_checklist_item(item_id, new_name, retries=3):
    """Atualiza o nome de um checkItem. Tenta ate 3 vezes em caso de timeout."""
    for attempt in range(1, retries + 1):
        try:
            r = requests.put(
                f"https://api.trello.com/1/cards/{TRELLO_CARD_ID}/checkItem/{item_id}",
                params={**trello_params(), "name": new_name, "state": "incomplete"},
                timeout=30,
            )
            return r.status_code == 200
        except requests.exceptions.Timeout:
            if attempt < retries:
                time.sleep(3)
            else:
                return False
        except Exception:
            return False


def build_item_name(name, password, ip, pct_str):
    return f"{name} ({password}) ----- {ip} ----- **{pct_str}**"


def update_trello(results, checklist_items):
    """Atualiza os checkItems do Trello em paralelo usando threads."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    print()
    print(f"  Atualizando Trello ...", end=" ", flush=True)

    tasks = {}
    for ip, data in results.items():
        item_id = checklist_items.get(ip)
        if not item_id:
            continue
        if data["error"]:
            new_name = f"{data['name']} ({data['password']}) ----- {ip} ----- **ERRO SSH**"
        else:
            new_name = build_item_name(data["name"], data["password"], ip, data["pct_str"])
        tasks[item_id] = new_name

    updated = 0
    failed  = 0

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(update_checklist_item, iid, name): iid for iid, name in tasks.items()}
        for future in as_completed(futures):
            try:
                if future.result():
                    updated += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

    if failed == 0:
        print(CYAN + f"OK! {updated} itens atualizados." + RESET)
    else:
        print(YELLOW + f"{updated} atualizados, {failed} com erro." + RESET)


# =============================================================================
# MAIN
# =============================================================================

def main():
    SERVERS         = load_servers()
    CHECKLIST_ITEMS = load_checklist_items()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print()
    print(CYAN + BOLD + "=" * 60 + RESET)
    print(CYAN + BOLD + f"  Hapolo Disk Monitor -- {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}" + RESET)
    print(CYAN + BOLD + "=" * 60 + RESET)
    print()

    ok_count   = 0
    warn_count = 0
    err_count  = 0
    csv_rows   = []
    results    = {}

    for name, password, ip in SERVERS:
        label = f"{name:<22} {ip:<18}"
        print(f"  {BOLD}{label}{RESET} ... ", end="", flush=True)

        output, error = check_server(name, password, ip)

        if error:
            print(RED + f"ERRO: {error}" + RESET)
            csv_rows.append({
                "timestamp": TIMESTAMP, "server": name, "ip": ip,
                "filesystem": "", "size": "", "used": "", "available": "",
                "use_pct": "", "mountpoint": "", "status": f"ERRO_SSH: {error}",
            })
            results[ip] = {"name": name, "password": password, "pct": -1, "pct_str": "ERRO", "error": True}
            err_count += 1
            continue

        disks = parse_df(output)

        if not disks:
            print(YELLOW + "Sem dados de disco" + RESET)
            continue

        root_disk = next((d for d in disks if d["mountpoint"] == "/"), disks[0])
        results[ip] = {
            "name": name,
            "password": password,
            "pct": root_disk["use_pct"],
            "pct_str": root_disk["use_pct_str"],
            "error": False,
        }

        first = True
        for d in disks:
            status = "ALERTA" if d["use_pct"] >= ALERT_THRESHOLD else "OK"
            if d["use_pct"] >= ALERT_THRESHOLD:
                warn_count += 1
            else:
                ok_count += 1

            csv_rows.append({
                "timestamp":  TIMESTAMP,
                "server":     name,
                "ip":         ip,
                "filesystem": d["filesystem"],
                "size":       d["size"],
                "used":       d["used"],
                "available":  d["available"],
                "use_pct":    d["use_pct_str"],
                "mountpoint": d["mountpoint"],
                "status":     status,
            })

            line_info = f"{color_pct(d['use_pct'])} usado  ({d['mountpoint']})"
            if first:
                print(line_info)
                first = False
            else:
                print(f"  {'':22} {'':18}     {line_info}")

    fieldnames = [
        "timestamp", "server", "ip", "filesystem", "size",
        "used", "available", "use_pct", "mountpoint", "status"
    ]
    for path in (CSV_FILE, LATEST):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)

    print()
    print(CYAN + BOLD + "=" * 60 + RESET)
    print(f"  Alertas (>={ALERT_THRESHOLD}%)  : {RED}{BOLD}{warn_count}{RESET}")
    print(f"  Erros SSH         : {RED}{BOLD}{err_count}{RESET}")
    print(f"  Relatorio salvo   : {CYAN}{CSV_FILE}{RESET}")

    update_trello(results, CHECKLIST_ITEMS)

    print(CYAN + BOLD + "=" * 60 + RESET)
    print()


if __name__ == "__main__":
    main()
