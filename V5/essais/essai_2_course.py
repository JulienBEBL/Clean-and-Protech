"""
essai_2_course.py — Mesure de la course réelle de la VIC, dans les DEUX sens.

Lancer avec Geany (F5), SERVICE main.py ARRÊTÉ, pompe à l'arrêt.
Durée ≈ 10 min. Ctrl+C est inutile (et ferme le terminal) : « q » + Entrée.

Principe : la VIC part d'une butée et avance de INCREMENT pas à chaque Entrée.
Au premier contact avec la pige opposée (claquement, ou repère de l'axe moteur
qui ne tourne plus), taper « c ». Mesure faite DEPART → RETOUR, puis RETOUR → DEPART.

Pourquoi deux sens : la détection au bruit arrive un peu en retard (le moteur ne
claque qu'après quelques pas contre la pige). Ce retard est le même dans les deux
sens ; l'écart entre les deux mesures donne la répétabilité.

À quoi sert la valeur :
    - VIC_TOTAL_STEPS dans config.py (NEUTRE = moitié, RETOUR = course) ;
    - décider l'ancrage alterné DEPART / RETOUR : il ne décale pas NEUTRE si la
      course configurée est la course réelle ;
    - suivre une éventuelle usure des piges : refaire la mesure à chaque visite.
"""

from __future__ import annotations

from _commun import (Quitter, cadre, console_silencieuse, demander,
                     message_gpio_occupe, pause_fin, sauver, titre)

APPROCHE_PAS: int  = 440   # montée rapide, AVANT la pige opposée (course ≥ ≈ 460 attendue)
INCREMENT_PAS: int = 2     # pas par Entrée (2 pas = 0,36° de VIC)
LIMITE_PAS: int    = 620   # sécurité : jamais au-delà
ANCRAGE_PAS: int   = 560   # ancrage initial, position inconnue (couvre une course ≤ 100°)
MARGE_BUTEE: int   = 40    # poussée courte pour être sûr d'être plaqué en butée


def _approche(vic, sens: int, nom_butee: str) -> int:
    """Avance vers la butée opposée ; retourne le nombre de pas au contact."""
    vic.move_relative(sens * APPROCHE_PAS)
    pos = APPROCHE_PAS
    print(f"\n  Approche faite ({APPROCHE_PAS} pas). Avance de {INCREMENT_PAS} pas par Entrée.")
    print(f"  Au premier contact avec la butée {nom_butee} : tape  c  puis Entrée.\n")
    while True:
        rep = demander(f"  {pos:4d} pas | Entrée = +{INCREMENT_PAS}, c = contact")
        if rep == "c":
            return pos - INCREMENT_PAS // 2          # contact pendant le dernier incrément
        if pos + INCREMENT_PAS > LIMITE_PAS:
            print(f"  Limite de sécurité {LIMITE_PAS} pas atteinte sans contact.")
            raise Quitter()
        vic.move_relative(sens * INCREMENT_PAS)
        pos += INCREMENT_PAS


def main() -> None:
    titre("ESSAI 2 — MESURE DE LA COURSE REELLE VIC")
    print("  Avant de commencer :")
    print("   - service main.py arrêté, pompe à l'arrêt (sélecteur variateur OFF)")
    print("   - être près de la VIC pour ENTENDRE / VOIR le contact")
    print("   - si possible : repère (feutre, adhésif) sur l'axe ou l'accouplement moteur")
    print("   - arrêt d'urgence réel = coupure électrique, pas le clavier\n")
    demander("  Entrée pour démarrer")

    import config
    import libs.gpio_handle as gpio_handle
    from libs.vic import VICController
    console_silencieuse()

    try:
        gpio_handle.init()
        vic = VICController()
        vic.open()
    except Exception as e:
        message_gpio_occupe(e)
        pause_fin()
        return

    mesures: list[tuple[str, int]] = []
    connue = False      # position approximative connue (après le 1er ancrage)
    try:
        while True:
            print("\n  1/4 Ancrage DEPART (claquement normal, jusqu'à 14 s)...")
            vic.move_relative(-((max(0, vic.position) + MARGE_BUTEE) if connue else ANCRAGE_PAS))
            vic.set_position(0)
            connue = True

            print("  2/4 Mesure DEPART → RETOUR")
            c1 = _approche(vic, +1, "RETOUR")
            mesures.append(("DEPART->RETOUR", c1))
            print(f"      → {c1} pas")

            print("\n  3/4 Plaquage en butée RETOUR, puis mesure RETOUR → DEPART")
            vic.move_relative(+MARGE_BUTEE)
            c2 = _approche(vic, -1, "DEPART")
            mesures.append(("RETOUR->DEPART", c2))
            print(f"      → {c2} pas")

            rep = demander("\n  Refaire une mesure aller-retour ? o = oui, Entrée = non")
            if rep != "o":
                break
    except Quitter:
        print("\n  Arrêt demandé.")
    finally:
        try:
            print("\n  4/4 Retour en NEUTRE (ancrage DEPART puis "
                  f"{config.VIC_NEUTRE_STEPS} pas)...")
            # Position approximative connue → ancrage court ; sinon ancrage complet.
            dist = (max(0, vic.position) + MARGE_BUTEE) if connue else ANCRAGE_PAS
            vic.move_relative(-dist)
            vic.set_position(0)
            vic.move_to(config.VIC_NEUTRE_STEPS)
        except Exception as e:
            print(f"  (retour NEUTRE impossible : {e})")
        vic.disable()
        vic.close()
        gpio_handle.close()

    if not mesures:
        cadre(["Aucune mesure."])
        pause_fin()
        return

    valeurs = [v for _, v in mesures]
    moy     = sum(valeurs) / len(valeurs)
    ecart   = max(valeurs) - min(valeurs)
    diff    = moy - config.VIC_TOTAL_STEPS
    lignes  = [f"{n:15s} : {v} pas  ({v * 0.18:.1f}°)" for n, v in mesures]
    lignes += [
        f"Moyenne         : {moy:.1f} pas  ({moy * 0.18:.1f}°)",
        f"Écart max       : {ecart} pas  ({ecart * 0.18:.2f}°)  = répétabilité",
        f"Config actuelle : VIC_TOTAL_STEPS = {config.VIC_TOTAL_STEPS}"
        f"  → écart {diff:+.1f} pas ({diff * 0.18:+.2f}°)",
        "Rappel : contact détecté au bruit = valeur un peu forte (même biais",
        "dans les deux sens). Envoyer cette capture à Claude.",
    ]
    cadre(["RESULTAT COURSE VIC", *lignes])
    p = sauver("course_vic", lignes)
    if p:
        print(f"\n  Sauvegardé : {p}")
    pause_fin()


if __name__ == "__main__":
    try:
        main()
    except Quitter:
        pause_fin()
    except Exception as e:
        print(f"\nERREUR : {e}")
        pause_fin()
