# config/config_loader.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class ConfigError(Exception):
    pass


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fusion récursive simple:
      - si deux valeurs sont des dict: merge récursif
      - sinon: override écrase base
    """
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _require(cfg: Dict[str, Any], path: str) -> Any:
    """
    Récupère une clé via "a.b.c". Lève ConfigError si absent.
    """
    cur: Any = cfg
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise ConfigError(f"Clé manquante dans config: {path}")
        cur = cur[part]
    return cur


def _get(cfg: Dict[str, Any], path: str, default: Any) -> Any:
    cur: Any = cfg
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


@dataclass(frozen=True)
class LoadedConfig:
    """
    Contient:
      - raw: dict complet (facile à inspecter)
      - helpers: getters typés
    """
    raw: Dict[str, Any]

    def get(self, path: str, default: Any = None) -> Any:
        return _get(self.raw, path, default)

    def require(self, path: str) -> Any:
        return _require(self.raw, path)

    # Helpers typés (les plus courants)
    def get_int(self, path: str, default: int) -> int:
        return int(self.get(path, default))

    def get_float(self, path: str, default: float) -> float:
        return float(self.get(path, default))

    def get_str(self, path: str, default: str) -> str:
        return str(self.get(path, default))


DEFAULT_CONFIG: Dict[str, Any] = {
    "logging": {"dir": "/var/log/machine_ctrl", "level": "INFO"},
    "i2c": {"bus": 1, "mcp1": 0x24, "mcp2": 0x25, "mcp3": 0x26, "lcd": 0x27},
    "gpio": {
        "lgpio_chip": 0,
        "step_pins": {"M1": 17, "M2": 27, "M3": 22, "M4": 5, "M5": 18, "M6": 23, "M7": 24, "M8": 25},
        "relays": {"air": 16, "pump": 20},
        "flowmeter": 21,
    },
    "motors": {
        "microsteps_per_rev": 3200,
        "ena_settle_ms": 10,
        "dir_setup_us": 5,
        "invert_dir": {},  # {"M1": true}
    },
    "inputs": {"poll_hz": 100, "debounce_ms": 30},
    "flowmeter": {"pulses_per_liter": 12.0, "sample_period_s": 1.0, "edge": "FALLING"},
}


def load_config(path: str = "config/config.yaml", defaults: Optional[Dict[str, Any]] = None) -> LoadedConfig:
    """
    Charge un YAML et fusionne avec des defaults.
    - Si le fichier n'existe pas: retourne defaults.
    - Si YAML invalide: lève ConfigError.

    Utilisation:
        from config.config_loader import load_config
        cfg = load_config("config/config.yaml")
        i2c_bus = cfg.get_int("i2c.bus", 1)
    """
    base = dict(DEFAULT_CONFIG if defaults is None else defaults)

    p = Path(path)
    if not p.exists():
        return LoadedConfig(raw=base)

    try:
        with p.open("r", encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
    except Exception as e:
        raise ConfigError(f"Impossible de lire {path}: {e}") from e

    if not isinstance(user_cfg, dict):
        raise ConfigError(f"Le fichier {path} doit contenir un dictionnaire YAML à la racine")

    merged = _deep_merge(base, user_cfg)

    # Validations minimales
    step_pins = _get(merged, "gpio.step_pins", {})
    if not isinstance(step_pins, dict) or len(step_pins) == 0:
        raise ConfigError("gpio.step_pins doit être un dict non vide")

    # Convertit quelques champs au bon type (robustesse)
    merged["i2c"]["bus"] = int(_get(merged, "i2c.bus", 1))
    merged["i2c"]["mcp1"] = int(_get(merged, "i2c.mcp1", 0x24))
    merged["i2c"]["mcp2"] = int(_get(merged, "i2c.mcp2", 0x25))
    merged["i2c"]["mcp3"] = int(_get(merged, "i2c.mcp3", 0x26))
    merged["i2c"]["lcd"] = int(_get(merged, "i2c.lcd", 0x27))

    merged["gpio"]["lgpio_chip"] = int(_get(merged, "gpio.lgpio_chip", 0))
    merged["gpio"]["flowmeter"] = int(_get(merged, "gpio.flowmeter", 21))
    merged["gpio"]["relays"]["air"] = int(_get(merged, "gpio.relays.air", 16))
    merged["gpio"]["relays"]["pump"] = int(_get(merged, "gpio.relays.pump", 20))

    for k, v in list(merged["gpio"]["step_pins"].items()):
        merged["gpio"]["step_pins"][k] = int(v)

    merged["motors"]["microsteps_per_rev"] = int(_get(merged, "motors.microsteps_per_rev", 3200))
    merged["motors"]["ena_settle_ms"] = int(_get(merged, "motors.ena_settle_ms", 10))
    merged["motors"]["dir_setup_us"] = int(_get(merged, "motors.dir_setup_us", 5))

    merged["inputs"]["poll_hz"] = int(_get(merged, "inputs.poll_hz", 100))
    merged["inputs"]["debounce_ms"] = int(_get(merged, "inputs.debounce_ms", 30))

    merged["flowmeter"]["pulses_per_liter"] = float(_get(merged, "flowmeter.pulses_per_liter", 12.0))
    merged["flowmeter"]["sample_period_s"] = float(_get(merged, "flowmeter.sample_period_s", 1.0))
    merged["flowmeter"]["edge"] = str(_get(merged, "flowmeter.edge", "FALLING")).upper()

    return LoadedConfig(raw=merged)
