"""
_commun.py — Outils partagés par les scripts d'essai (V5/essais/).

Contraintes de terrain (Julien, 2026-11-09) :
    - les scripts sont lancés depuis Geany (F5) ;
    - Ctrl+C FERME le terminal Geany : on ne s'en sert jamais pour arrêter un
      script. Chaque question accepte « q » + Entrée pour quitter proprement ;
    - les résultats remontent par capture d'écran : affichage court, lignes
      ≤ 78 caractères, un résumé final encadré, et une pause avant fermeture ;
    - chaque résultat est aussi écrit dans V5/essais/resultats/ (non versionné).
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

ESSAIS_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = ESSAIS_DIR.parent
RESULTATS    = ESSAIS_DIR / "resultats"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

LARGEUR = 78


class Quitter(Exception):
    """L'opérateur a tapé q : arrêt propre du script."""


def titre(texte: str) -> None:
    print("=" * LARGEUR)
    print(f"  {texte}")
    print("=" * LARGEUR)


def cadre(lignes: list[str]) -> None:
    """Résumé final, fait pour une capture d'écran."""
    print()
    print("#" * LARGEUR)
    for l in lignes:
        print(f"#  {l}"[:LARGEUR])
    print("#" * LARGEUR)


def demander(question: str) -> str:
    """input() avec sortie propre sur « q ». Jamais de Ctrl+C."""
    rep = input(f"{question} (q = quitter) : ").strip().lower()
    if rep == "q":
        raise Quitter()
    return rep


def pause_fin() -> None:
    """Laisse le terminal ouvert le temps de la capture d'écran."""
    try:
        input("\n>>> Fais ta capture d'écran, puis Entrée pour fermer. ")
    except EOFError:
        pass


def console_silencieuse() -> None:
    """
    Le logger du projet écrit aussi dans la console : on n'y garde que les
    avertissements, pour des écrans lisibles. Le fichier de log reste complet.
    """
    try:
        from logger import log
    except Exception:
        return
    for h in log.handlers:
        if type(h) is logging.StreamHandler:
            h.setLevel(logging.WARNING)


def sauver(nom: str, lignes: list[str]) -> Path | None:
    """Écrit le résultat dans resultats/AAAAMMJJ_HHMMSS_<nom>.txt."""
    try:
        RESULTATS.mkdir(exist_ok=True)
        p = RESULTATS / f"{datetime.now():%Y%m%d_%H%M%S}_{nom}.txt"
        p.write_text("\n".join(lignes) + "\n", encoding="utf-8")
        return p
    except Exception as e:
        print(f"(résultat non sauvegardé : {e})")
        return None


def message_gpio_occupe(e: Exception) -> None:
    cadre([
        "IMPOSSIBLE D'OUVRIR LES SORTIES DE LA VIC",
        "Le programme machine (main.py) tourne probablement encore.",
        "Dans un terminal :",
        "  systemctl list-units --type=service | grep -i -E 'clean|serena|main'",
        "  sudo systemctl stop <nom-du-service>",
        "puis relancer ce script (F5).",
        f"Détail : {str(e)[:60]}",
    ])
