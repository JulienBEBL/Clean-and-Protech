#!/usr/bin/env python3
from __future__ import annotations

import os
import time
import signal
from pathlib import Path

import yaml

from core.logging_setup import setup_logging
from core.fsm import MachineFSM

from hal.i2c_bus import I2CBus, I2CConfig, scan_i2c
from hal.gpio_lgpio import GpioLgpio

from hw.mcp_hub import MCPHub, McpAddressing
from hw.inputs import Inputs
from hw.leds import ProgramLeds

from driver.motors import Motors, MotorsConfig

from libs.lcd_i2c_20x4 import LCDI2C_backpack
from libs.flowmeter_yfdn50 import FlowMeterYFDN50, FlowMeterConfig
from libs.relays_critical import CriticalRelays


# -------------------------
# Config
# -------------------------

DEFAULT_CONFIG = {
    "logging": {"dir": "/var/log/machine_ctrl", "level": "INFO"},
    "i2c": {"bus": 1, "mcp1": 0x24, "mcp2": 0x25, "mcp3": 0x26, "lcd": 0x27},
    "gpio": {
        "step_pins": {"M1": 17, "M2": 27, "M3": 22, "M4": 5, "M5": 18, "M6": 23, "M7": 24, "M8": 25},
        "relays": {"air": 16, "pump": 20},
        "flowmeter": 21,
        "lgpio_chip": 0,
    },
    "motors": {"microsteps_per_rev": 3200, "ena_settle_ms": 10, "dir_setup_us": 5, "invert_dir": {}},
    "inputs": {"poll_hz": 100, "debounce_ms": 30},
    "flowmeter": {"pulses_per_liter": 12.0, "sample_period_s": 1.0, "edge": "FALLING"},
}


def load_config(path: str) -> dict:
    if not Path(path).exists():
        return DEFAULT_CONFIG
    with open(path, "r", encoding="utf-8") as f:
        user_cfg = yaml.safe_load(f) or {}

    # merge simple (profondeur 1-2, suffisant pour démarrer)
    cfg = DEFAULT_CONFIG.copy()
    for k, v in user_cfg.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k] = {**cfg[k], **v}
        else:
            cfg[k] = v
    return cfg


# -------------------------
# SAFE & arrêt propre
# -------------------------

_stop = False


def _handle_sigterm(_signum, _frame):
    global _stop
    _stop = True


def apply_safe(log, relays: CriticalRelays, motors: Motors, leds: ProgramLeds) -> None:
    """
    SAFE demandé:
      - pompe OFF
      - air OFF
      - moteurs OFF (ENA désactivés)
      - LEDs OFF
    """
    try:
        relays.all_off()
    except Exception as e:
        log.error("SAFE: erreur relays.all_off(): %s", e)

    try:
        motors.stop_all()
        motors.disable_all()
    except Exception as e:
        log.error("SAFE: erreur moteurs stop/disable: %s", e)

    try:
        leds.all_off()
    except Exception as e:
        log.error("SAFE: erreur leds.all_off(): %s", e)


# -------------------------
# Main
# -------------------------

def main() -> None:
    global _stop

    # signaux (systemd stop -> SIGTERM)
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    cfg = load_config("config/config.yaml")

    log = setup_logging(cfg["logging"]["dir"], level=cfg["logging"]["level"])
    log.info("Démarrage machine_ctrl (main.py)")

    # I2C
    i2c_bus_num = int(cfg["i2c"]["bus"])
    bus = I2CBus(I2CConfig(bus=i2c_bus_num, retries=3, retry_delay_s=0.01))
    found = scan_i2c(bus)
    log.info("I2C détectés: %s", [hex(a) for a in found])

    # MCP Hub
    addrs = McpAddressing(
        mcp1=int(cfg["i2c"]["mcp1"]),
        mcp2=int(cfg["i2c"]["mcp2"]),
        mcp3=int(cfg["i2c"]["mcp3"]),
    )
    mcp = MCPHub(bus, addrs)
    mcp.init_all()
    log.info("MCPHub initialisé")

    # LEDs programmes (via MCPHub)
    leds = ProgramLeds(mcp, active_high=True)
    leds.all_off()

    # Inputs (thread interne, via MCPHub)
    inputs = Inputs(
        mcp=mcp,
        poll_hz=int(cfg["inputs"]["poll_hz"]),
        debounce_ms=int(cfg["inputs"]["debounce_ms"]),
        active_low_buttons=True,
        active_low_selectors=True,
    )
    inputs.start()
    log.info("Inputs démarré (poll + debounce)")

    # LCD (ta lib) - I2C direct, indépendant du MCPHub
    lcd_addr = int(cfg["i2c"]["lcd"])
    lcd = LCDI2C_backpack(I2C_ADDR=lcd_addr)
    lcd.clear()
    log.info("LCD initialisé sur 0x%02X", lcd_addr)

    # Relais critiques (ta lib, RPi.GPIO)
    pin_air = int(cfg["gpio"]["relays"]["air"])
    pin_pump = int(cfg["gpio"]["relays"]["pump"])
    relays = CriticalRelays(pin_air=pin_air, pin_pump=pin_pump, active_high_air=True, active_high_pump=True)
    log.info("Relais critiques initialisés (air=%d, pump=%d)", pin_air, pin_pump)

    # Flowmeter (ta lib, RPi.GPIO)
    # edge string -> valeur GPIO
    edge_str = str(cfg["flowmeter"]["edge"]).upper()
    try:
        import RPi.GPIO as GPIO
        edge_val = GPIO.FALLING if edge_str == "FALLING" else GPIO.RISING
    except Exception:
        edge_val = None  # fallback, mais en pratique RPi.GPIO sera dispo

    fm_cfg = FlowMeterConfig(
        gpio_bcm=int(cfg["gpio"]["flowmeter"]),
        pulses_per_liter=float(cfg["flowmeter"]["pulses_per_liter"]),
        sample_period_s=float(cfg["flowmeter"]["sample_period_s"]),
        edge=edge_val,  # FALLING
    )
    flow = FlowMeterYFDN50(cfg=fm_cfg)
    flow.start()
    log.info("Flowmeter démarré (GPIO%d, K=%.3f pulses/L)", fm_cfg.gpio_bcm, fm_cfg.pulses_per_liter)

    # Moteurs (STEP via lgpio, DIR/ENA via MCPHub)
    gpio = GpioLgpio(chip=int(cfg["gpio"]["lgpio_chip"]))
    step_pins = {k: int(v) for k, v in cfg["gpio"]["step_pins"].items()}

    motors = Motors(
        gpio=gpio,
        mcp=mcp,
        step_pins=step_pins,
        cfg=MotorsConfig(
            microsteps_per_rev=int(cfg["motors"]["microsteps_per_rev"]),
            ena_settle_ms=int(cfg["motors"]["ena_settle_ms"]),
            dir_setup_us=int(cfg["motors"]["dir_setup_us"]),
            invert_dir=dict(cfg["motors"].get("invert_dir", {})),
        ),
    )
    log.info("Moteurs initialisés (lgpio STEP + MCP DIR/ENA)")

    # SAFE au boot (demandé)
    apply_safe(log, relays, motors, leds)

    # FSM (IDLE/RUN)
    fsm = MachineFSM(
        inputs=inputs,
        leds=leds,
        lcd=lcd,
        relays=relays,
        flowmeter=flow,
        logger=log,
    )

    # Affichage initial (FSM fera ensuite les mises à jour)
    lcd.lcd_string("Choix programme", lcd.LCD_LINE_1)
    lcd.lcd_string("1..5", lcd.LCD_LINE_2)
    lcd.lcd_string("Debit: ----.- L/m", lcd.LCD_LINE_3)
    lcd.lcd_string("Total: ----.- L", lcd.LCD_LINE_4)

    log.info("Boucle principale démarrée")

    try:
        # Tick régulier : assez rapide pour capter les events, mais léger CPU
        tick_period_s = 0.05  # 50 ms
        while not _stop:
            fsm.tick()
            time.sleep(tick_period_s)

    finally:
        log.info("Arrêt en cours -> SAFE + shutdown modules")
        try:
            apply_safe(log, relays, motors, leds)
        except Exception:
            pass

        # stop inputs
        try:
            inputs.stop()
        except Exception:
            pass

        # stop flowmeter (sans GPIO.cleanup global)
        try:
            flow.stop()
        except Exception:
            pass

        # Important: éviter relays.cleanup() si d'autres modules RPi.GPIO tournent,
        # mais ici on arrête tout, donc c'est OK si tu veux.
        # Par sécurité, on ne fait pas cleanup global automatiquement.
        try:
            relays.all_off()
        except Exception:
            pass

        try:
            bus.close()
        except Exception:
            pass

        try:
            gpio.close()
        except Exception:
            pass

        log.info("Arrêt terminé")


if __name__ == "__main__":
    main()
