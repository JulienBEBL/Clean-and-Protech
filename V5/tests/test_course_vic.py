"""
test_course_vic.py — Mesure de la course réelle de la VIC (entre les 2 piges) — V5.

À lancer sur le Raspberry, service main.py ARRÊTÉ, pompe à l'arrêt.
Procédure complète : V5/memoire/procedure-mesure-course.md

Déroulé :
    1. Ancrage en butée DEPART sur 500 + 60 pas (position inconnue, et la course
       réelle peut dépasser 500 pas) → claquement attendu, jusqu'à ≈ 14 s si la
       VIC est déjà en DEPART.
    2. Montée rapide jusqu'à APPROCHE_PAS (sans toucher la pige RETOUR).
    3. Puis, à chaque appui sur Entrée : INCREMENT_PAS pas de plus vers RETOUR.
       Écouter : au premier claquement, taper  c  puis Entrée.
       La course mesurée s'affiche (dernière valeur sans claquement + 1/2 incrément).
    q + Entrée : quitter à tout moment.  Ctrl+C : arrêt immédiat.

Le résultat est à reporter dans config.VIC_TOTAL_STEPS (NEUTRE suit automatiquement).
Ce script n'est utilisé par aucun programme machine.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
import libs.gpio_handle as gpio_handle
from libs.vic import VICController

# ── Paramètres de la mesure ───────────────────────────────────────────────────
APPROCHE_PAS: int  = 400   # montée rapide initiale (doit rester AVANT la pige RETOUR)
INCREMENT_PAS: int = 2     # pas par appui (2 pas = 0,36°)
LIMITE_PAS: int    = 600   # sécurité : on n'avance jamais au-delà
# Ancrage initial : la course réelle peut dépasser 500 pas, l'ancrage se fait donc
# sur 500 + MARGE_ANCRAGE_PAS (couvre une course réelle jusqu'à ≈ 100°).
MARGE_ANCRAGE_PAS: int = 60
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 58)
    print("  MESURE DE LA COURSE REELLE VIC")
    print("=" * 58)
    print("  Service main.py arrete ? Pompe a l'arret ?")
    print(f"  Approche {APPROCHE_PAS} pas, puis +{INCREMENT_PAS} pas par appui sur Entree.")
    print("  Au premier claquement en butee RETOUR : taper  c  puis Entree.")
    print("  q = quitter, Ctrl+C = arret immediat.\n")
    if input("  Entree pour demarrer (q pour quitter) : ").strip().lower() == "q":
        return

    gpio_handle.init()
    vic = VICController()
    vic.open()
    try:
        print("\n  1. Ancrage DEPART (claquement normal)...")
        vic.move_relative(-(config.VIC_TOTAL_STEPS + MARGE_ANCRAGE_PAS))
        vic.set_position(0)
        time.sleep(0.5)

        print(f"  2. Montee jusqu'a {APPROCHE_PAS} pas...")
        vic.move_relative(APPROCHE_PAS)
        pos = APPROCHE_PAS

        print("  3. Avance pas a pas — ecouter le claquement.\n")
        while pos + INCREMENT_PAS <= LIMITE_PAS:
            rep = input(f"  pos = {pos:4d} pas | Entree = +{INCREMENT_PAS}, c = claquement, q = quitter : ").strip().lower()
            if rep == "q":
                print("  Arret sans mesure.")
                break
            if rep == "c":
                course = pos - INCREMENT_PAS + INCREMENT_PAS // 2
                print()
                print("  " + "=" * 54)
                print(f"  Claquement au passage {pos - INCREMENT_PAS} → {pos} pas")
                print(f"  COURSE REELLE ≈ {course} pas  (±{INCREMENT_PAS} pas, ≈ {course * 0.18:.1f}°)")
                print(f"  Valeur actuelle config.VIC_TOTAL_STEPS = {config.VIC_TOTAL_STEPS}")
                print("  " + "=" * 54)
                break
            vic.move_relative(INCREMENT_PAS)
            pos += INCREMENT_PAS
        else:
            print(f"  Limite de securite {LIMITE_PAS} pas atteinte sans claquement signale.")

        print("\n  Retour vers DEPART...")
        vic.move_relative(-(vic.position + config.VIC_ANCHOR_OVERCOURSE_STEPS))
        vic.set_position(0)
    except KeyboardInterrupt:
        print("\n  Arrete par l'utilisateur.")
    finally:
        vic.disable()
        vic.close()
        gpio_handle.close()
    print("=== FIN MESURE ===")


if __name__ == "__main__":
    main()
