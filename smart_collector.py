import docker
import requests
import json
import re
import threading
import time
import sys
from datetime import datetime

# --- CONFIGURATION DU PROJET ---
# L'adresse du backend Spring Boot d'Abdellah


BACKEND_URL = "http://10.61.234.131:8080/api/logs"


# Liste des conteneurs à surveiller (Network Functions)
TARGET_CONTAINERS = ["amf", "ausf", "smf", "nrf"]

# Configuration UERANSIM (Chemins validés lors du Sprint 0)
UERANSIM_CONTAINER = "ueransim"
GNB_CMD = "/ueransim/nr-gnb -c ./config/free5gc-gnb.yaml"
UE_CMD = "/ueransim/nr-ue -c ./config/free5gc-ue.yaml"

# Connexion au démon Docker local
try:
    client = docker.from_env()
except Exception as e:
    print(f"❌ Erreur critique: Impossible de se connecter à Docker. {e}")
    sys.exit(1)

# --- 1. MODULE DE PARSING (REGEX) ---
def parse_log_line(container_name, raw_line):
    """
    Transforme une ligne de log brute free5GC en dictionnaire structuré.
    Format typique: 2025-11-23T10:00:00Z [INFO][AMF][Main] Message...
    """
    # Nettoyage de la ligne (décodage bytes -> string)
    if isinstance(raw_line, bytes):
        line = raw_line.decode('utf-8', errors='ignore').strip()
    else:
        line = raw_line.strip()

    if not line:
        return None

    # Regex pour capturer: Timestamp, Level, Module, et le Message
    # Exemple pattern: 2023-01-01... [INFO][AMF] ...
    pattern = r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*Z)\s+\[([A-Z]+)\]\[([A-Za-z0-9]+)\](?:\s*\[.*?\])?\s+(.*)$"
    match = re.match(pattern, line)

    log_entry = {
        "timestamp": datetime.now().isoformat(), # Fallback timestamp
        "nf_name": container_name, # Ex: free5gc-amf
        "level": "UNKNOWN",
        "component": "UNKNOWN",
        "message": line, # Message brut par défaut
        "event_type": "LOG", # Par défaut
        "status": "INFO"
    }

    if match:
        log_entry["timestamp"] = match.group(1)
        log_entry["level"] = match.group(2)      # Ex: INFO, ERRO
        log_entry["component"] = match.group(3)  # Ex: AMF, NGAP
        log_entry["message"] = match.group(4)    # Le reste du message

        # Analyse sémantique simple pour aider le Sprint 2 (IDS)
        msg_lower = log_entry["message"].lower()
        if "error" in msg_lower or "fail" in msg_lower or "reject" in msg_lower:
            log_entry["status"] = "FAILURE"
            log_entry["event_type"] = "SECURITY_ALERT" if "auth" in msg_lower else "ERROR"
        elif "success" in msg_lower or "accepted" in msg_lower:
            log_entry["status"] = "SUCCESS"
            log_entry["event_type"] = "TRANSACTION"

    return log_entry

# --- 2. MODULE DE COMMUNICATION BACKEND ---
def send_to_springboot(log_data):
    """Envoie le log JSON vers l'API Spring Boot"""
    try:
        headers = {'Content-Type': 'application/json'}
        # On envoie en mode 'fire and forget' pour ne pas ralentir le parsing, 
        # mais idéalement on gérerait une queue.
        response = requests.post(BACKEND_URL, json=log_data, timeout=2)
        if response.status_code != 200:
            print(f"⚠️ Backend refusé ({response.status_code})")
    except requests.exceptions.ConnectionError:
        # On n'affiche pas l'erreur à chaque ligne pour ne pas spammer si le backend est éteint
        pass 
    except Exception as e:
        print(f"⚠️ Erreur d'envoi: {e}")

# --- 3. MODULE DE MONITORING (THREADS) ---
def monitor_container(container_name):
    """Fonction exécutée dans un thread séparé pour chaque conteneur"""
    print(f"🎧 Démarrage de l'écoute sur {container_name}...")
    try:
        container = client.containers.get(container_name)
        # stream=True permet de lire en temps réel (comme tail -f)
        for line in container.logs(stream=True, follow=True, tail=0):
            parsed_log = parse_log_line(container_name, line)
            if parsed_log:
                # Affichage local pour debug
                print(f"[{container_name}] {parsed_log['message'][:50]}...") 
                # Envoi vers Abdellah
                send_to_springboot(parsed_log)
    except docker.errors.NotFound:
        print(f"❌ Conteneur {container_name} introuvable (est-il lancé ?)")
    except Exception as e:
        print(f"❌ Arrêt monitoring {container_name}: {e}")

# --- 4. MODULE DE SIMULATION (CONTROL PLANE) ---
def launch_simulation():
    """Pilote le conteneur UERANSIM pour lancer gNB et UE"""
    print("\n🚀 --- DÉBUT DE LA SÉQUENCE DE SIMULATION 5G ---")
    
    try:
        ueransim = client.containers.get(UERANSIM_CONTAINER)
        
        # Étape 1 : Nettoyage (au cas où)
        print("🧹 Nettoyage des anciens processus gNB/UE...")
        ueransim.exec_run("killall -9 nr-gnb nr-ue")
        time.sleep(2)

        # Étape 2 : Lancement du gNB (Antenne)
        print(f"📡 Lancement du gNodeB (Antenne)...")
        # detach=True est CRUCIAL pour ne pas bloquer le script Python
        # On lance la commande en background dans le conteneur
        cmd_gnb = f"bash -c '{GNB_CMD} > /var/log/gnb.log 2>&1 &'"
        ueransim.exec_run(cmd_gnb, detach=True)
        
        print("⏳ Attente de l'initialisation de l'antenne (5s)...")
        time.sleep(5) # Laisser le temps au SCTP de monter

        # Étape 3 : Lancement de l'UE (Utilisateur)
        print(f"📱 Lancement de l'User Equipment (Smartphone)...")
        cmd_ue = f"bash -c '{UE_CMD} > /var/log/ue.log 2>&1 &'"
        ueransim.exec_run(cmd_ue, detach=True)

        print("✅ Simulation lancée ! Les logs devraient arriver...")

    except Exception as e:
        print(f"❌ Erreur lors de la simulation: {e}")

# --- MAIN ---
if __name__ == "__main__":
    print("🔒 5G Security IDS - Log Collector & Simulator Agent")
    print("==================================================")

    # 1. Lancer les écouteurs de logs (Threads)
    threads = []
    for target in TARGET_CONTAINERS:
        t = threading.Thread(target=monitor_container, args=(target,))
        t.daemon = True # Le thread mourra quand le script principal s'arrête
        t.start()
        threads.append(t)

    # 2. Attendre un peu que les écouteurs soient prêts
    time.sleep(2)

    # 3. Déclencher la simulation
    launch_simulation()

    # 4. Maintenir le script en vie
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Arrêt du collecteur.")
