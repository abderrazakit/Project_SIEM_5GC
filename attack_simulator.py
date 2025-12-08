import requests
import json
import time
import random
from datetime import datetime

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
# Adresse de ton Backend Spring Boot (Windows) vue depuis la VM Ubuntu
API_URL = "http://172.28.54.163:8080/api/logs" 

def send_log(payload):
    """Envoie le log au Backend et affiche le résultat"""
    try:
        headers = {'Content-Type': 'application/json'}
        response = requests.post(API_URL, json=payload, timeout=2)
        
        if response.status_code == 200:
            print(f"✅ [ENVOYÉ] {payload['nfName']} -> {payload['message'][:50]}...")
        else:
            print(f"⚠️ [REFUSÉ] HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ [ERREUR] Impossible de joindre {API_URL} : {e}")

def generate_log(nf_name, level, component, message):
    """
    Génère le JSON exact attendu par LogEntry.java (Spring Boot)
    IMPORTANT: On utilise 'nfName' (camelCase) et pas 'nf_name' !
    """
    return {
        "timestamp": datetime.now().isoformat(),
        "nfName": nf_name,       # <--- Correction critique pour le Backend Java
        "level": level,
        "component": component,
        "message": message
    }

# ==========================================
# 🛡️ SCÉNARIOS D'ATTAQUE (Basés sur SecurityService.java)
# ==========================================

# RÈGLE 1 : Échec Authentification (Brute Force)
def sim_auth_failure():
    print("\n🔐 SCÉNARIO 1 : Brute Force sur AUSF/UDM")
    for i in range(5): # On envoie 5 échecs rapides
        log = generate_log(
            "ausf", 
            "WARN", 
            "UeAuth", 
            f"Authentication failed for IMSI:20893000000000{i} (MacFailure)"
        )
        send_log(log)
        time.sleep(0.1)

# RÈGLE 2 : SMF Crash (DoS)
def sim_smf_crash():
    print("\n💥 SCÉNARIO 2 : Crash Critique SMF (DoS)")
    log = generate_log(
        "smf", 
        "ERROR", 
        "SessionMgr", 
        "Critical Service Failure: Memory Overflow, Session Dropped"
    )
    send_log(log)

# RÈGLE 3 : QoS Tampering (Vol de bande passante)
def sim_qos_tampering():
    print("\n💎 SCÉNARIO 3 : Modification QoS (PCF)")
    log = generate_log(
        "pcf", 
        "WARN", 
        "PolicyAuth", 
        "Policy reject: User attempted QoS modification failed"
    )
    send_log(log)

# RÈGLE 4 : Slice Attack (Accès interdit)
def sim_slice_attack():
    print("\n🍰 SCÉNARIO 4 : Slice Hopping (NSSF)")
    log = generate_log(
        "nssf", 
        "WARN", 
        "SliceSelection", 
        "Slice Selection Failed: Requested nssai forbidden for this subscriber"
    )
    send_log(log)

# RÈGLE 5 : API Abuse (NEF)
def sim_api_abuse():
    print("\n🌐 SCÉNARIO 5 : Abus API (NEF)")
    log = generate_log(
        "nef", 
        "WARN", 
        "ApiGateway", 
        "API Access Error: Rate limit exceeded for partner APP_01"
    )
    send_log(log)

# RÈGLE 6 : Rogue NF (Intrusion matériel inconnu)
def sim_rogue_nf():
    print("\n🏴‍☠️ SCÉNARIO 6 : Rogue Network Function")
    log = generate_log(
        "hacker_device_01", # Nom qui n'est pas dans la liste blanche
        "WARN", 
        "Scanner", 
        "Scanning network ports for open vulnerabilities..."
    )
    send_log(log)

# RÈGLE 7 : Congestion Réseau
def sim_congestion():
    print("\n🚦 SCÉNARIO 7 : Congestion Réseau")
    log = generate_log(
        "upf", 
        "WARN", 
        "GTP-U", 
        "Packet dropped: buffer overflow due to network congestion"
    )
    send_log(log)

# ==========================================
# 🎮 MENU PRINCIPAL
# ==========================================
if __name__ == "__main__":
    print("==========================================")
    print("🔫 5G SIEM - GÉNÉRATEUR D'ATTAQUES (VM)")
    print(f"Cible : {API_URL}")
    print("==========================================")
    
    while True:
        print("\n--- CHOISISSEZ UNE ATTAQUE ---")
        print("1. 🔐 Brute Force (AUSF)")
        print("2. 💥 SMF Crash (DoS)")
        print("3. 💎 QoS Tampering (PCF)")
        print("4. 🍰 Slice Attack (NSSF)")
        print("5. 🌐 API Abuse (NEF)")
        print("6. 🏴‍☠️ Rogue NF (Intrusion)")
        print("7. 🚦 Congestion")
        print("9. 🚀 TOUT LANCER (Mode Démo)")
        print("0. Quitter")
        
        choice = input("\nVotre choix > ")
        
        if choice == '1': sim_auth_failure()
        elif choice == '2': sim_smf_crash()
        elif choice == '3': sim_qos_tampering()
        elif choice == '4': sim_slice_attack()
        elif choice == '5': sim_api_abuse()
        elif choice == '6': sim_rogue_nf()
        elif choice == '7': sim_congestion()
        elif choice == '9':
            print("\n🚀 LANCEMENT DE TOUS LES SCÉNARIOS...")
            sim_auth_failure()
            time.sleep(1)
            sim_smf_crash()
            time.sleep(1)
            sim_slice_attack()
            time.sleep(1)
            sim_rogue_nf()
            print("\n✨ Simulation terminée.")
        elif choice == '0':
            print("Au revoir.")
            break
        else:
            print("Choix invalide.")
