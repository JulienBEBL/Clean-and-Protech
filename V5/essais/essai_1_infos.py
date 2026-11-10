"""
essai_1_infos.py — Photo de l'état du logiciel sur le Raspberry (aucun mouvement).

Lancer avec Geany (F5). Ne touche à AUCUNE sortie : peut tourner pendant que
main.py tourne. Une seule capture d'écran suffit.

Affiche : commit installé, fichiers modifiés localement (doit être vide),
réglages VIC / PRG3 / LCD actifs, position VIC mémorisée, derniers logs.
"""

from __future__ import annotations

import json
import platform
import subprocess

from _commun import PROJECT_ROOT, cadre, pause_fin, sauver, titre


def _cmd(args: list[str]) -> str:
    try:
        r = subprocess.run(args, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=10)
        return (r.stdout or r.stderr).strip()
    except Exception as e:
        return f"(erreur : {e})"


def main() -> None:
    titre("ESSAI 1 — ETAT DU LOGICIEL")
    import config

    commit  = _cmd(["git", "log", "-1", "--format=%h %ad %s", "--date=short"])
    modifs  = _cmd(["git", "status", "--short"]) or "aucune (propre)"
    service = _cmd(["bash", "-c",
                    "systemctl list-units --type=service --no-pager --plain "
                    "| grep -i -E 'clean|serena|main' || echo '(aucun service trouvé)'"])

    etat = "absent"
    p = PROJECT_ROOT / "state" / "vic_state.json"
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            etat = f"pos={d.get('position')} sûr={d.get('safe')} mouvement={d.get('moving')}"
        except Exception as e:
            etat = f"illisible ({e})"

    cote = PROJECT_ROOT / "state" / "vic_state.json.homing"
    try:
        prochain_homing = cote.read_text(encoding="utf-8").strip() or "?"
    except Exception:
        prochain_homing = "absent (→ DEPART)"
    etat += f" | prochain homing côté {prochain_homing}"

    logs = sorted((PROJECT_ROOT / "logs").glob("run_*.log"))[-3:]

    lignes = [
        f"Commit      : {commit}",
        f"Modifs RPi  : {modifs}",
        f"Python      : {platform.python_version()}",
        f"Service     : {service[:60]}",
        "",
        f"VIC course / NEUTRE      : {config.VIC_TOTAL_STEPS} / {config.VIC_NEUTRE_STEPS} pas",
        f"VIC vitesse              : {config.VIC_SPEED_SPS} pas/s",
        f"Driver toujours actif    : {config.VIC_HOLD_ENABLED}",
        f"Réarmement driver        : {getattr(config, 'VIC_DRIVER_RESET_ENABLED', 'ABSENT')}"
        f" ({getattr(config, 'VIC_DRIVER_RESET_OFF_S', '?')} s coupé)",
        f"PRG3 inversion VIC       : {getattr(config, 'PRG3_VIC_INVERT_ENABLED', 'ABSENT')}"
        f"  (False = DEPART fixe)",
        f"Cache LCD                : {getattr(config, 'LCD_LINE_CACHE_ENABLED', 'ABSENT')}",
        f"Position mémorisée       : {config.VIC_STATE_ENABLED} — {etat}",
        f"K-factor débitmètre      : {config.DEBITMETRE_K_FACTOR}",
        "",
        "Derniers logs :",
        *[f"  {l.name}  ({l.stat().st_size // 1024} ko)" for l in logs],
    ]
    for l in lignes:
        print(l)
    cadre(["Attendu : commit = celui poussé depuis le PC, Modifs RPi = aucune,",
           "Réarmement driver True, PRG3 inversion False, Cache LCD True."])
    sauver("infos", lignes)
    pause_fin()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERREUR : {e}")
        pause_fin()
