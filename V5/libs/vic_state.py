"""
vic_state.py — Mémorisation de la position VIC sur la carte SD — V5.

Objectif : au démarrage machine, ancrer la VIC depuis sa dernière position
connue au lieu de toute la course (beaucoup moins de forçage contre la pige).

Le fichier (JSON) contient :
    version      : format du fichier
    total_steps  : course configurée au moment de l'écriture
    position     : dernière position connue (pas)
    moving       : True pendant un mouvement VIC
    safe         : True si la position est fiable même après une coupure
                   brutale (aucun mouvement en cours ET pompe arrêtée depuis
                   au moins VIC_STATE_SAFE_DELAY_S)

Règle de sûreté : en cas de doute, load() retourne None → l'appelant fait
l'ancrage sur toute la course, exactement comme sans ce module.
    - fichier absent, illisible, corrompu, format inconnu  → None
    - course différente de la course configurée            → None
    - mouvement en cours au moment de la coupure           → None
    - position non marquée « sûre » (pompe récemment ON)   → None

Écriture atomique : fichier temporaire + fsync + os.replace. Une coupure de
courant pendant l'écriture laisse soit l'ancien fichier, soit le nouveau,
jamais un fichier à moitié écrit.

Aucune exception ne sort de ce module : un défaut de carte SD ne doit jamais
arrêter la machine. En cas d'échec d'écriture, le fichier est supprimé si
possible (pour ne jamais laisser une ancienne position « sûre » périmée).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from logger import log

_VERSION = 1


class VICStateStore:
    """Lecture / écriture du fichier de position VIC. Ne lève jamais d'exception."""

    def __init__(self, path: str, total_steps: int) -> None:
        self._path  = Path(path)
        self._tmp   = self._path.with_name(self._path.name + ".tmp")
        # Côté du prochain ancrage initial du homing (alternance entre démarrages)
        self._side  = self._path.with_name(self._path.name + ".homing")
        self._total = int(total_steps)
        self._last: Optional[dict] = None   # dernier état écrit avec succès

    # ---- côté du homing (alternance DEPART / RETOUR d'un démarrage à l'autre) ----

    def homing_side(self) -> str:
        """
        Côté de l'ancrage initial de CE homing : "DEPART" ou "RETOUR".
        Fichier absent ou illisible → "DEPART". Ne lève jamais d'exception.
        """
        try:
            side = self._side.read_text(encoding="utf-8").strip().upper()
            return side if side in ("DEPART", "RETOUR") else "DEPART"
        except Exception:
            return "DEPART"

    def save_homing_side(self, side: str) -> None:
        """Mémorise le côté du PROCHAIN homing. Échec → journalisé, sans exception."""
        try:
            self._side.parent.mkdir(parents=True, exist_ok=True)
            self._side.write_text(side, encoding="utf-8")
        except Exception as e:
            log.warning(f"VIC homing — côté suivant non mémorisé ({e})")

    # ---- lecture ----

    def load(self) -> Optional[int]:
        """
        Retourne la position mémorisée si elle est fiable, sinon None.
        Journalise la raison du choix.
        """
        try:
            if not self._path.exists():
                log.info("VIC position mémorisée — aucun fichier → ancrage pleine course")
                return None
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"VIC position mémorisée — fichier illisible ({e}) → ancrage pleine course")
            return None

        reason = self._invalid_reason(data)
        if reason is not None:
            log.info(f"VIC position mémorisée — non utilisée ({reason}) → ancrage pleine course")
            return None

        pos = int(data["position"])
        log.info(f"VIC position mémorisée — {pos} pas, fiable → ancrage depuis cette position")
        return pos

    def _invalid_reason(self, data) -> Optional[str]:
        if not isinstance(data, dict):
            return "format inconnu"
        if data.get("version") != _VERSION:
            return f"version {data.get('version')!r}"
        total = data.get("total_steps")
        if type(total) is not int or total != self._total:
            return f"course {total!r} ≠ course configurée {self._total}"
        pos = data.get("position")
        if type(pos) is not int or not (0 <= pos <= self._total):
            return f"position {pos!r} hors course"
        if data.get("moving") is not False:
            return "mouvement en cours lors de l'arrêt"
        if data.get("safe") is not True:
            return "pompe en marche ou arrêtée depuis trop peu de temps lors de l'arrêt"
        return None

    # ---- écriture ----

    def save(self, position: int, moving: bool, safe: bool) -> None:
        """Écrit l'état (atomique). Ne fait rien si l'état est identique au dernier écrit."""
        data = {
            "version":     _VERSION,
            "total_steps": self._total,
            "position":    int(max(0, min(self._total, int(position)))),
            "moving":      bool(moving),
            "safe":        bool(safe),
        }
        if data == self._last:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(self._tmp, self._path)
            self._fsync_dir()
            self._last = data
        except Exception as e:
            self._last = None
            log.warning(f"VIC position mémorisée — écriture impossible ({e}), fichier supprimé")
            self._remove()

    def _fsync_dir(self) -> None:
        """Rend le renommage durable (Linux). Sans effet ailleurs."""
        try:
            fd = os.open(str(self._path.parent), os.O_RDONLY)
        except Exception:
            return
        try:
            os.fsync(fd)
        except Exception:
            pass
        finally:
            os.close(fd)

    def _remove(self) -> None:
        for p in (self._path, self._tmp):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
            except Exception as e:
                log.error(f"VIC position mémorisée — suppression impossible de {p} ({e})")
