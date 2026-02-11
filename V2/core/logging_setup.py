# core/logging_setup.py
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path


def setup_logging(log_dir: str = "/var/log/machine_ctrl", level: str = "INFO") -> logging.Logger:
    """
    Crée un logger 'machine' avec :
      - sortie console
      - 1 fichier log par boot, nommé boot_YYYYMMDD_HHMMSS.log

    Usage :
      log = setup_logging(...)
      log.info("message")
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(log_dir, f"boot_{ts}.log")

    logger = logging.getLogger("machine")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    fmt = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")

    # Console
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(logger.level)

    # Fichier
    fh = logging.FileHandler(filename, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.setLevel(logger.level)

    logger.addHandler(ch)
    logger.addHandler(fh)

    logger.info("Logging démarré: %s", filename)
    return logger
