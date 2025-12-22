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

# 1. Backend Spring Boot (Ton IP Windows)
BACKEND_URL = "http://10.244.196.131:8080/api/logs"

# 2. Infrastructure
# Chemin absolu vers le dossier contenant les fichiers docker-compose
COMPOSE_FILE_PATH = os.path.expanduser("/home/aazdag/Bureau/free5gc-compose/docker-compose.yaml")
COMPOSE_PROJECT_DIR = os.path.dirname(COMPOSE_FILE_PATH)

# 3. Cibles Monitoring
TARGET_CONTAINERS = [
    "amf", "ausf", "smf", "nrf", "udm", 
    "pcf", "nssf", "nef", "chf", "tngf", 
    "n3iwf", "upf", "webui"
]

# 4. Simulation UERANSIM
UERANSIM_CONTAINER = "ueransim"
GNB_CMD = "./nr-gnb -c config/gnbcfg.yaml"
UE_CMD = "./nr-ue -c config/uecfg.yaml"


# ==========================================
# 🏗️ MODULE 1 : INFRASTRUCTURE (START & STOP)
# ==========================================
def start_infrastructure():
    print("🏗️  Démarrage de l'infrastructure free5GC + Prometheus...")
    
    if not os.path.exists(COMPOSE_FILE_PATH):
        print(f"❌ ERREUR: Fichier introuvable : {COMPOSE_FILE_PATH}")
        sys.exit(1)

    try:
        # ON CHARGE LES DEUX FICHIERS : Core 5G + Monitoring
        cmd = [
            "docker", "compose", 
            "-f", "docker-compose.yaml", 
            "-f", "docker-compose-prometheus.yaml", 
            "up", "-d"
        ]
        
        subprocess.run(cmd, cwd=COMPOSE_PROJECT_DIR, check=True)
        
        print("✅ Docker Compose (5G + Metrics) OK. Attente stabilisation (30s)...")
        time.sleep(30) # On laisse un peu plus de temps pour Prometheus/Grafana
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Erreur démarrage infra: {e}")
        sys.exit(1)

def stop_infrastructure():
    """Arrête proprement tous les conteneurs"""
    print("\n🛑 ARRÊT DE L'INFRASTRUCTURE EN COURS...")
    print("⏳ Veuillez patienter, suppression des conteneurs...")
    
    try:
        # ON ÉTEINT TOUT PROPREMENT
        cmd = [
            "docker", "compose", 
            "-f", "docker-compose.yaml", 
            "-f", "docker-compose-prometheus.yaml", 
            "down"
        ]
        
        subprocess.run(cmd, cwd=COMPOSE_PROJECT_DIR, check=True)
        print("✅ Infrastructure arrêtée avec succès.")
        
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Erreur lors de l'arrêt: {e}")

def stop_simulation():
    """Arrête les processus internes de UERANSIM"""
    print("🛑 Arrêt de la simulation (UE/gNB)...")
    try:
        container = client.containers.get(UERANSIM_CONTAINER)
        container.exec_run("bash -c 'pkill -9 nr-ue || true'")
        container.exec_run("bash -c 'pkill -9 nr-gnb || true'")
    except:
        pass 

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

    # Regex standard free5GC
    pattern = r"^(\S+)\s+\[([A-Z]+)\]\[([a-zA-Z0-9]+)\](?:\[(.*?)\])?\s+(.*)"
    match = re.match(pattern, clean_message)

    # Structure JSON conforme au Backend Java
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
        pass


# ==========================================
# 🚀 MODULE 4 : SIMULATION
# ==========================================
def launch_simulation():
    print("\n🚀 --- LANCEMENT AUTOMATIQUE DE LA SIMULATION ---")
    
    try:
        container = client.containers.get(UERANSIM_CONTAINER)
        
        # 1. Nettoyage initial
        stop_simulation()
        time.sleep(2)

        # 2. Démarrage gNB
        print(f"📡 Démarrage gNB (config/gnbcfg.yaml)...")
        # On force le dossier de travail avec cd /ueransim
        cmd_gnb_full = f"bash -c 'cd /ueransim && nohup {GNB_CMD} > /var/log/gnb.log 2>&1 &'"
        container.exec_run(cmd_gnb_full, detach=True)
        
        print("⏳ Initialisation antenne (15s)...")
        time.sleep(15)

        # 3. Démarrage UE
        print(f"📱 Connexion UE (config/uecfg.yaml)...")
        cmd_ue_full = f"bash -c 'cd /ueransim && nohup {UE_CMD} > /var/log/ue.log 2>&1 &'"
        container.exec_run(cmd_ue_full, detach=True)
        
        print("⏳ Enregistrement réseau (30s)...")
        time.sleep(30)

        # 4. Debug Logs
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
            print("❌ ÉCHEC : Interface uesimtun0 non active ou problème DNS.")

    except docker.errors.NotFound:
        print(f"❌ Erreur: Conteneur {UERANSIM_CONTAINER} introuvable.")
    except Exception as e:
        print(f"❌ Erreur Simulation: {e}")


# ==========================================
# 🏁 MAIN
# ==========================================
if __name__ == "__main__":
    print("🤖 SIEM 5G ORCHESTRATOR v4.0 (Prometheus Enabled)")
    
    # 1. Démarrer
    start_infrastructure()

    # 2. Monitorer
    print("🔌 Démarrage des capteurs...")
    for target in TARGET_CONTAINERS:
        t = threading.Thread(target=monitor, args=(target,), daemon=True)
        t.start()

    time.sleep(2)
    
    # 3. Simuler
    launch_simulation()

    print("\n✅ Système en cours d'exécution...")
    print("👉 Grafana est accessible sur : http://localhost:3001 (admin/admin)")
    print("👉 Prometheus est accessible sur : http://localhost:9091")
    print("👉 Appuie sur Ctrl+C pour TOUT ARRÊTER proprement.")
    
    # 4. Boucle principale avec gestion d'arrêt
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n👋 Signal d'arrêt reçu (Ctrl+C) !")
        stop_simulation()
        stop_infrastructure()
        print("🏁 Programme terminé proprement.")
        sys.exit(0)
