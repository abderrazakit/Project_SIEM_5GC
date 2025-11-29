import docker
import requests
import re
import threading
import time
import sys
import os
import subprocess
from datetime import datetime

# ==========================================
# ⚙️ CONFIGURATION DU PROJET
# ==========================================

# 1. Backend Spring Boot
BACKEND_URL = "http://10.61.234.131:8080/api/logs"

# 2. Infrastructure
# Chemin absolu vers ton docker-compose   /home/aazdag/Bureau/free5gc-compose
COMPOSE_FILE_PATH = os.path.expanduser("/home/aazdag/Bureau/free5gc-compose/docker-compose.yaml")
COMPOSE_PROJECT_DIR = os.path.dirname(COMPOSE_FILE_PATH)

# 3. Cibles Monitoring
TARGET_CONTAINERS = ["amf", "ausf", "smf", "nrf", "udm"]

# 4. Simulation UERANSIM (CORRECTION DES NOMS DE FICHIERS ICI)
UERANSIM_CONTAINER = "ueransim"
# On utilise les noms exacts trouvés par ton 'ls' : gnbcfg.yaml et uecfg.yaml
GNB_CMD = "./nr-gnb -c config/gnbcfg.yaml"
UE_CMD = "./nr-ue -c config/uecfg.yaml"


# ==========================================
# 🏗️ MODULE 1 : INFRASTRUCTURE
# ==========================================
def start_infrastructure():
    print("🏗️  Démarrage de l'infrastructure free5GC...")
    
    if not os.path.exists(COMPOSE_FILE_PATH):
        print(f"❌ ERREUR: Fichier introuvable : {COMPOSE_FILE_PATH}")
        sys.exit(1)

    try:
        subprocess.run(
            ["docker", "compose", "-f", "docker-compose.yaml", "up", "-d"], 
            cwd=COMPOSE_PROJECT_DIR,
            check=True
        )
        print("✅ Docker Compose OK. Attente stabilisation (20s)...")
        time.sleep(20) 
    except subprocess.CalledProcessError as e:
        print(f"❌ Erreur démarrage infra: {e}")
        sys.exit(1)


# ==========================================
# 🧹 MODULE 2 : PARSING
# ==========================================
def remove_ansi_colors(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def parse_and_send(container_name, raw_line):
    if isinstance(raw_line, bytes):
        line_str = raw_line.decode('utf-8', errors='ignore').strip()
    else:
        line_str = raw_line.strip()
    
    clean_message = remove_ansi_colors(line_str)
    if not clean_message: return

    pattern = r"^(\S+)\s+\[([A-Z]+)\]\[([a-zA-Z0-9]+)\](?:\[(.*?)\])?\s+(.*)"
    match = re.match(pattern, clean_message)

    log_payload = {
        "timestamp": datetime.now().isoformat(),
        "nfName": container_name,
        "level": "INFO",
        "component": "SYSTEM",
        "message": clean_message
    }

    if match:
        log_payload["timestamp"] = match.group(1)
        log_payload["level"] = match.group(2)
        log_payload["component"] = match.group(3)
        log_payload["message"] = match.group(5)

    try:
        requests.post(BACKEND_URL, json=log_payload, timeout=0.5)
    except Exception:
        pass


# ==========================================
# 🎧 MODULE 3 : MONITORING
# ==========================================
try:
    client = docker.from_env()
except Exception:
    print("❌ Erreur Docker. Vérifie que Docker tourne.")
    sys.exit(1)

def monitor(name):
    print(f"🎧 Écoute active: {name}")
    try:
        container = client.containers.get(name)
        for line in container.logs(stream=True, follow=True, tail=0):
            parse_and_send(name, line)
    except Exception:
        print(f"⚠️  Arrêt écoute {name}")


# ==========================================
# 🚀 MODULE 4 : SIMULATION (CORRIGÉ & ROBUSTE)
# ==========================================
def launch_simulation():
    print("\n🚀 --- LANCEMENT AUTOMATIQUE DE LA SIMULATION ---")
    
    try:
        container = client.containers.get(UERANSIM_CONTAINER)
        
        # 1. Nettoyage
        print("🧹 Kill des anciens processus...")
        container.exec_run("bash -c 'pkill -9 nr-gnb || true'")
        container.exec_run("bash -c 'pkill -9 nr-ue || true'")
        time.sleep(2)

        # 2. Démarrage gNB
        print(f"📡 Démarrage gNB (config/gnbcfg.yaml)...")
        # On force le dossier /ueransim pour que le chemin relatif 'config/...' fonctionne
        cmd_gnb_full = f"bash -c 'cd /ueransim && nohup {GNB_CMD} > /var/log/gnb.log 2>&1 &'"
        container.exec_run(cmd_gnb_full, detach=True)
        
        print("⏳ Initialisation antenne (15s)...")
        time.sleep(15)

        # 3. Démarrage UE
        print(f"📱 Connexion UE (config/uecfg.yaml)...")
        cmd_ue_full = f"bash -c 'cd /ueransim && nohup {UE_CMD} > /var/log/ue.log 2>&1 &'"
        container.exec_run(cmd_ue_full, detach=True)
        
        print("⏳ Enregistrement réseau (10s)...")
        time.sleep(10)

        # 4. Debug Logs (Vérification immédiate)
        print("🔍 Vérification du démarrage UE...")
        check_ue = container.exec_run("tail -n 5 /var/log/ue.log")
        log_output = check_ue.output.decode('utf-8').strip()
        print(f"--- LOG UE (Extrait) ---\n{log_output}\n------------------------")

        # 5. Test Ping
        print("\n📶 TEST PING (uesimtun0)...")
        ping_cmd = "ping -I uesimtun0 -c 3 google.com"
        exit_code, output = container.exec_run(ping_cmd)
        
        print("--- SORTIE PING ---")
        print(output.decode('utf-8'))
        print("-------------------")

        if exit_code == 0:
            print("✅ SUCCÈS : Connexion 5G établie ! Le SIEM reçoit des logs valides.")
        else:
            print("❌ ÉCHEC :")
            if "No such device" in output.decode('utf-8'):
                print("👉 L'interface uesimtun0 n'existe pas. L'UE a crashé ou a été rejeté par l'AMF.")
            else:
                print("👉 Problème de routage ou DNS.")

    except docker.errors.NotFound:
        print(f"❌ Erreur: Conteneur {UERANSIM_CONTAINER} introuvable.")
    except Exception as e:
        print(f"❌ Erreur Simulation: {e}")


# ==========================================
# 🏁 MAIN
# ==========================================
if __name__ == "__main__":
    print("🤖 SIEM 5G ORCHESTRATOR v3.0 (Fix Config Paths)")
    
    start_infrastructure()

    print("🔌 Démarrage des capteurs...")
    for target in TARGET_CONTAINERS:
        threading.Thread(target=monitor, args=(target,), daemon=True).start()

    time.sleep(2)
    launch_simulation()

    print("\n✅ Script en cours d'exécution (Ctrl+C pour quitter)...")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        print("👋 Bye.")