"""
essai_3_logs.py — Résumé lisible d'un log machine, page par page, pour captures d'écran.

Lancer avec Geany (F5). Ne touche à AUCUNE sortie : utilisable pendant que
main.py tourne (le log en cours est lu tel quel).

Garde les lignes utiles au diagnostic VIC : homing, ancrages, réarmement driver,
démarrage / arrêt de programme, sélecteur PRG5, purge, sécurités, erreurs.
Le débit instantané (toutes les 10 s) est masqué par défaut.
"""

from __future__ import annotations

import re

from _commun import LARGEUR, PROJECT_ROOT, Quitter, cadre, demander, pause_fin, sauver, titre

PAGE = 22
MOTS = re.compile(
    r"VIC|PRG\d|Homing|homing|driver|Purge|Sécurité|Débit insuffisant|Cuve vide|"
    r"WARNING|ERROR|Arrêt|arrêt|Machine prête|démarrage|Log ouvert",
)


def main() -> None:
    titre("ESSAI 3 — RESUME D'UN LOG MACHINE")
    logs = sorted((PROJECT_ROOT / "logs").glob("run_*.log"))
    if not logs:
        cadre(["Aucun log dans V5/logs/."])
        return
    derniers = logs[-8:]
    for i, p in enumerate(derniers, start=1):
        print(f"  {i}. {p.name}  ({p.stat().st_size // 1024} ko)")
    rep = demander(f"\n  Numéro du log (Entrée = {len(derniers)}, le plus récent)")
    try:
        choix = derniers[int(rep) - 1] if rep else derniers[-1]
    except (ValueError, IndexError):
        choix = derniers[-1]
    debit = demander("  Afficher aussi le débit instantané ? o = oui, Entrée = non") == "o"

    lignes = []
    for l in choix.read_text(encoding="utf-8", errors="replace").splitlines():
        if MOTS.search(l) or (debit and "Debit instantane" in l):
            # date retirée (l'heure suffit) pour gagner de la place à l'écran
            l = re.sub(r"^\d{4}-\d{2}-\d{2} ", "", l).replace("[INFO   ]  ", "")
            lignes.append(l[:LARGEUR])
    sauver(f"log_{choix.stem}", lignes)

    print(f"\n  {choix.name} : {len(lignes)} lignes retenues, {PAGE} par page.")
    n_pages = max(1, (len(lignes) + PAGE - 1) // PAGE)
    page = n_pages - 1 if demander("  Commencer par la fin ? o = oui, Entrée = début") == "o" else 0
    while True:
        print("\n" + "-" * LARGEUR)
        print(f"  {choix.name} — page {page + 1}/{n_pages}")
        print("-" * LARGEUR)
        for l in lignes[page * PAGE:(page + 1) * PAGE]:
            print(l)
        rep = demander("\n  Entrée = page suivante, p = précédente, numéro = aller à la page")
        if rep == "p":
            page = max(0, page - 1)
        elif rep.isdigit():
            page = min(n_pages - 1, max(0, int(rep) - 1))
        elif page + 1 < n_pages:
            page += 1
        else:
            print("  (dernière page)")


if __name__ == "__main__":
    try:
        main()
    except Quitter:
        pass
    except Exception as e:
        print(f"\nERREUR : {e}")
    pause_fin()
