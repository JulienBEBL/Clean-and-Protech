"""
logger.py — Logging horodaté pour Clean & Protech V4.

Crée un fichier de log par run dans le dossier logs/ :
    logs/run_YYYYMMDD_HHMMSS.log

Niveaux utilisés :
    INFO   — événements normaux (démarrage, programme start/stop, VIC, AIR)
    WARNING — situations anormales non bloquantes
    ERROR  — erreurs matérielles ou exceptions

Usage :
    from logger import log

    log.info("PRG1 démarré")
    log.warning("Débit faible détecté")
    log.error(f"Erreur I2C : {e}")
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path


# ============================================================
# Configuration
# ============================================================

_LOG_DIR = Path(__file__).resolve().parent / "logs"
_FMT     = "%(asctime)s [%(levelname)-7s]  %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


# ============================================================
# Initialisation
# ============================================================

def _build_logger() -> logging.Logger:
    _LOG_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file  = _LOG_DIR / f"run_{timestamp}.log"

    logger = logging.getLogger("cleanprotech")
    logger.setLevel(logging.DEBUG)

    # Handler fichier — niveau DEBUG (tout)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_FMT, datefmt=_DATEFMT))

    # Handler console — niveau INFO
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(_FMT, datefmt=_DATEFMT))

    logger.addHandler(fh)
    logger.addHandler(ch)

    logger.info(f"Log ouvert : {log_file}")
    return logger


# Instance unique — importée directement par les modules
log: logging.Logger = _build_logger()
