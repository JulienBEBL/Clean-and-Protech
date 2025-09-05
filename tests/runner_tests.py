#!/usr/bin/python3
# runner_tests.py

import os
import sys
import subprocess
import shutil
import time

TESTS = {
    "1": ("Moteurs : ouverture/fermeture + V4V positions/tours", "test_moteurs.py"),
    "2": ("LEDs : 1 par 1, double, cycle ON/OFF",                "test_leds.py"),
    "3": ("Entrées : boutons programmes, sélecteur, air",        "test_inputs.py"),
    "4": ("LCD : affichages avec/sans clear (padding)",          "test_lcd.py"),
    "5": ("Relais : air ON/OFF + impulsion variateur (VFD)",     "test_relays.py"),
    "6": ("Débitmètre : Hz, L/min, volumes cumulés",             "test_flowmeter.py"),
}

PYTHON = shutil.which("python3") or sys.executable

def header():
    os.system("clear")
    print("="*72)
    print("   RUNNER TESTS — Plateforme RPi / GPIO (un test à la fois)")
    print("="*72)
    print("Conseils :")
    print(" - Lance ce runner en sudo si nécessaire (GPIO).")
    print(" - Chaque test s'arrête avec Ctrl+C.")
    print(" - Évite de lancer plusieurs tests en parallèle.")
    print("-"*72)
    print()

def print_menu():
    for k, (label, _) in TESTS.items():
        print(f"  {k}. {label}")
    print("  q. Quitter")
    print()

def run_test(script_name: str):
    if not os.path.exists(script_name):
        print(f"[ERREUR] Fichier introuvable : {script_name}")
        input("Appuie sur Entrée pour revenir au menu…")
        return

    print(f"\n[INFO] Lancement : {script_name}")
    print("      (Ctrl+C pour arrêter le test et revenir au menu)\n")

    try:
        # Lance le test en subprocess (hérite du TTY pour afficher en direct)
        proc = subprocess.Popen([PYTHON, script_name])
        proc.wait()
        rc = proc.returncode
        if rc == 0:
            print(f"\n[OK] Test terminé : {script_name}")
        else:
            print(f"\n[WARN] Test terminé avec code {rc} : {script_name}")
    except KeyboardInterrupt:
        print("\n[INFO] Interruption demandée (Ctrl+C). Tentative d'arrêt du test…")
        try:
            proc.terminate()
            time.sleep(1)
        except Exception:
            pass
    except FileNotFoundError:
        print(f"[ERREUR] Impossible d'exécuter {script_name} (python introuvable?)")
    except Exception as e:
        print(f"[ERREUR] Exception durant l'exécution : {e}")

    input("\nAppuie sur Entrée pour revenir au menu…")

def main():
    while True:
        header()
        print_menu()
        choice = input("Sélectionne un test (1-6) ou 'q' pour quitter : ").strip().lower()
        if choice == "q":
            print("\n[INFO] Au revoir.")
            break
        if choice in TESTS:
            _, script = TESTS[choice]
            run_test(script)
        else:
            print("[WARN] Choix invalide.")
            time.sleep(1.2)

if __name__ == "__main__":
    main()
