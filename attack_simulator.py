import requests
import json
import time
import random
from datetime import datetime

# --- CONFIGURATION ---
# Remplacez par l'IP de votre backend Spring Boot (comme dans smart_collector.py)
# Si vous testez tout en local : http://localhost:8080/api/logs
# Si c'est sur la VM : http://10.61.234.131:8080/api/logs
API_URL = "http://192.168.1.233:8080/api/logs" 

def send_log(payload):
    """Envoie un log simulé au Backend"""
    try:
        headers = {'Content-Type': 'application/json'}
        response = requests.post(API_URL, json=payload, timeout=2)
        if response.status_code == 200:
            print(f"✅ [ENVOYÉ] {payload['nf_name']} - {payload['message'][:40]}...")
        else:
            print(f"⚠️ [REFUSÉ] Status: {response.status_code}")
    except Exception as e:
        print(f"❌ [ERREUR] Impossible de contacter le backend: {e}")

def generate_base_log(nf_name, level, component, message):
    """Génère la structure JSON standard compatible avec votre projet"""
    return {
        "timestamp": datetime.now().isoformat(),
        "nf_name": nf_name,
        "level": level,
        "component": component,
        "message": message,
        "event_type": "LOG",   # Par défaut, l'IDS backend doit le changer en ALERT si détecté
        "status": "INFO"
    }

# --- SCÉNARIO 1 : Attaque par Force Brute (DoS Auth) ---
# Règle : "10 erreurs d’authentification en 5s"
def simulate_dos_auth():
    print("\nqp --- 1. SIMULATION: DoS / Brute Force Authentication ---")
    print("Envoi de 12 échecs d'authentification rapides...")
    
    for i in range(12):
        log = generate_base_log(
            nf_name="AUSF", # Authentication Server Function
            level="ERROR",
            component="Fn_Authentication",
            message=f"Authentication failed for UE_ID: 20893000000000{i} -MAC failure"
        )
        # On force un statut d'erreur pour aider l'IDS
        log["status"] = "FAILURE" 
        log["event_type"] = "SECURITY_ALERT" # Simulons que le collecteur a déjà suspecté quelque chose
        
        send_log(log)
        time.sleep(0.1) # Très rapide pour déclencher la règle temporelle (10 en 5s)

# --- SCÉNARIO 2 : Intrusion NF Inconnue ---
# Règle : "NF inconnue → intrusion possible"
def simulate_rogue_nf():
    print("\n🕵️ --- 2. SIMULATION: Rogue Network Function (Intrusion) ---")
    
    log = generate_base_log(
        nf_name="DARK-WEB-SCAMMER-NF", # Nom suspect qui n'est pas dans la liste officielle (AMF, SMF, etc.)
        level="WARN",
        component="UNKNOWN",
        message="Attempting to register new NF instance with invalid certificate."
    )
    log["status"] = "UNKNOWN"
    
    send_log(log)

# --- SCÉNARIO 3 : Message SBI Non Conforme ---
# Règle : "Message SBI non conforme → alerte format"
def simulate_malformed_sbi():
    print("\nrp --- 3. SIMULATION: Malformed SBI Message ---")
    
    log = generate_base_log(
        nf_name="AMF",
        level="WARN",
        component="Ngap_Handler",
        message="SBI Message Parse Error: JSON syntax error in HTTP/2 payload from SMF. Missing mandatory field 'pduSessionId'."
    )
    log["status"] = "FAILURE"
    
    send_log(log)

# --- MENU PRINCIPAL ---
if __name__ == "__main__":
    print("==========================================")
    print("🔫 5G SIEM - Outil de Simulation d'Attaques")
    print("Target Backend:", API_URL)
    print("==========================================")
    
    while True:
        print("\nChoisissez une attaque à simuler :")
        print("1. DoS / Brute Force (12 erreurs en < 2s)")
        print("2. Intrusion NF Inconnue")
        print("3. Message SBI Malformé")
        print("4. TOUT LANCER")
        print("0. Quitter")
        
        choice = input("Votre choix > ")
        
        if choice == '1':
            simulate_dos_auth()
        elif choice == '2':
            simulate_rogue_nf()
        elif choice == '3':
            simulate_malformed_sbi()
        elif choice == '4':
            simulate_dos_auth()
            time.sleep(2)
            simulate_rogue_nf()
            time.sleep(2)
            simulate_malformed_sbi()
        elif choice == '0':
            break
        else:
            print("Choix invalide.")
