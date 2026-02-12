#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Point d'entrée principal.

Objectifs :
- Code simple, lisible, modifiable.
- Pas de sur-architecture : juste ce fichier + quelques petites libs.
- MODE_TEST activable facilement pour vérifier le câblage.

Principe général :
- La configuration est dans config.yaml.
- On initialise I2C, MCP23017, LCD, moteurs, relais.
- Si mode test : on lance des tests interactifs.
- Sinon : on gère la logique "programme = chrono + pompe ON".
"""

import os
import sys
import time
import logging
from datetime import datetime
from typing import Dict, Any, Tuple

import RPi.GPIO as GPIO

try:
    import yaml  # type: ignore
except ImportError:
    print("Le module 'yaml' (PyYAML) est requis. Installe-le avec :")
    print("  pip install pyyaml")
    sys.exit(1)

from i2c_devices import MCP23017, LCD20x4, SMBus
from motors import StepperConfig, MotorManager
from tests import test_basic


CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config", "config.yaml")


def load_config() -> Dict[str, Any]:
    """
    Charge config.yaml et renvoie un dict Python.
    """
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(cfg: Dict[str, Any]) -> logging.Logger:
    """
    Configure le logging dans un sous-dossier.
    """
    log_cfg = cfg.get("logging", {})
    enabled = log_cfg.get("enabled", True)
    log_dir = log_cfg.get("directory", "logs")
    level_name = log_cfg.get("level", "INFO").upper()

    level = getattr(logging, level_name, logging.INFO)

    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = os.path.join(log_dir, f"{timestamp}.log")

    logging.basicConfig(
        filename=log_file,
        level=level,
        format="%(asctime)s;%(levelname)s;%(message)s",
    )
    log = logging.getLogger("main")
    if enabled:
        log.info("==== Démarrage log ====")
    return log


def gpio_setup_common(cfg: Dict[str, Any]) -> Tuple[Dict[str, int], Dict[str, int], int, int]:
    """
    Configure le mode GPIO et retourne :
    - step_pins : dict Mx -> GPIO
    - relay_pins : dict nom -> GPIO
    - flowmeter_pin
    - buzzer_pin
    """
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)

    gpio_cfg = cfg["gpio"]

    step_pins: Dict[str, int] = {
        name: int(pin) for name, pin in gpio_cfg["step_pins"].items()
    }
    relay_pins: Dict[str, int] = {
        name: int(pin) for name, pin in gpio_cfg["relays"].items()
    }
    flowmeter_pin = int(gpio_cfg["flowmeter"])
    buzzer_pin = int(gpio_cfg["buzzer"])

    # Sorties relais + buzzer
    for pin in relay_pins.values():
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(buzzer_pin, GPIO.OUT, initial=GPIO.LOW)

    # Flowmètre en entrée avec pull-up (à ajuster selon le capteur réel)
    GPIO.setup(flowmeter_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    return step_pins, relay_pins, flowmeter_pin, buzzer_pin


def init_i2c_and_devices(cfg: Dict[str, Any]) -> Tuple[MCP23017, MCP23017, MCP23017, LCD20x4, SMBus]:
    """
    Initialise le bus I2C, les 3 MCP23017 et le LCD.
    Retourne (mcp1, mcp2, mcp3, lcd, bus).
    """
    i2c_cfg = cfg["i2c"]
    bus_id = int(i2c_cfg.get("bus", 1))

    bus = SMBus(bus_id)

    mcp1 = MCP23017(bus, int(i2c_cfg["mcp1"]), name="MCP1_programs")
    mcp2 = MCP23017(bus, int(i2c_cfg["mcp2"]), name="MCP2_selectors")
    mcp3 = MCP23017(bus, int(i2c_cfg["mcp3"]), name="MCP3_drivers")

    lcd = LCD20x4(bus, int(i2c_cfg["lcd"]), width=20)

    # Configuration de base des MCP selon config.yaml
    mcp_cfg = cfg["mcp23017"]

    # MCP1 : boutons/LEDs programmes
    m1_cfg = mcp_cfg["mcp1_programs"]
    btn_bank = m1_cfg["buttons_bank"]
    leds_bank = m1_cfg["leds_bank"]
    btn_bits = m1_cfg["buttons_bits"]
    leds_bits = m1_cfg["leds_bits"]

    # Direction : boutons en entrée, LEDs en sortie.
    # On part de 0xFF (tout en entrée) et on met 0 sur les bits LEDs.
    dir_a = 0xFF
    dir_b = 0xFF
    if leds_bank.upper() == "A":
        for bit in leds_bits:
            dir_a &= ~(1 << bit)
    else:
        for bit in leds_bits:
            dir_b &= ~(1 << bit)

    if btn_bank.upper() == "A":
        for bit in btn_bits:
            dir_a |= (1 << bit)  # entrée
    else:
        for bit in btn_bits:
            dir_b |= (1 << bit)

    pullup_a = 0x00
    pullup_b = 0x00
    if m1_cfg.get("buttons_pullup", True):
        if btn_bank.upper() == "A":
            for bit in btn_bits:
                pullup_a |= (1 << bit)
        else:
            for bit in btn_bits:
                pullup_b |= (1 << bit)

    mcp1.configure_bank("A", dir_a, pullup_a)
    mcp1.configure_bank("B", dir_b, pullup_b)

    # MCP2 : sélecteurs VIC / AIR (tout en entrée avec pull-up)
    m2_cfg = mcp_cfg["mcp2_selectors"]
    pullup = 0xFF if m2_cfg.get("pullup", True) else 0x00
    mcp2.configure_bank("A", 0xFF, pullup)
    mcp2.configure_bank("B", 0xFF, pullup)

    # MCP3 : drivers moteurs (tout en sortie, ENA désactivés par défaut)
    m3_cfg = mcp_cfg["mcp3_drivers"]
    dir_bank = m3_cfg["dir_bank"]
    ena_bank = m3_cfg["ena_bank"]
    ena_active_low = bool(m3_cfg.get("ena_active_low", True))
    motors_bits = m3_cfg["motors"]

    # direction : DIR / ENA en sortie sur leurs banques respectives
    if dir_bank.upper() == "A":
        dir_a3 = 0x00
        dir_b3 = 0xFF
    else:
        dir_a3 = 0xFF
        dir_b3 = 0x00

    if ena_bank.upper() == "A":
        dir_a3 = 0x00
    else:
        dir_b3 = 0x00

    mcp3.configure_bank("A", dir_a3, 0x00)
    mcp3.configure_bank("B", dir_b3, 0x00)

    # ENA désactivés (HIGH si actif bas)
    for name, bit in motors_bits.items():
        if ena_active_low:
            level = 1  # désactivé
        else:
            level = 0
        mcp3.write_bit(ena_bank, bit, level)

    # LCD : message de démarrage
    lcd.clear()
    lcd.write_line(1, "Clean & Protech")
    lcd.write_line(2, "Init I2C/MCP...")

    return mcp1, mcp2, mcp3, lcd, bus


def init_motor_manager(cfg: Dict[str, Any], step_pins: Dict[str, int], mcp3: MCP23017) -> MotorManager:
    """
    Crée l'objet MotorManager à partir de la config.
    """
    m_cfg = cfg["motors"]
    m3_cfg = cfg["mcp23017"]["mcp3_drivers"]

    step_cfg = StepperConfig(
        steps_per_rev=int(m_cfg["steps_per_rev"]),
        default_rpm=float(m_cfg["default_rpm"]),
        min_rpm=float(m_cfg["min_rpm"]),
        max_rpm=float(m_cfg["max_rpm"]),
        accel_rpm_per_s=float(m_cfg["accel_rpm_per_s"]),
    )

    dir_bank = m3_cfg["dir_bank"]
    ena_bank = m3_cfg["ena_bank"]
    motors_bits = {name: int(bit) for name, bit in m3_cfg["motors"].items()}
    ena_active_low = bool(m3_cfg.get("ena_active_low", True))

    return MotorManager(
        config=step_cfg,
        step_pins=step_pins,
        mcp_dir_ena=mcp3,
        dir_bank=dir_bank,
        ena_bank=ena_bank,
        motor_bits=motors_bits,
        ena_active_low=ena_active_low,
    )


def read_program_buttons(
    mcp1: MCP23017,
    buttons_bank: str,
    buttons_bits: list[int],
) -> int:
    """
    Lit les boutons programmes et renvoie :
    - 0 si aucun ou plusieurs boutons pressés (cas bruit / erreur)
    - n (1..N) si exactement un bouton est pressé.

    Hypothèse : boutons câblés en actif bas avec pull-up.
    """
    val = mcp1.read_bank(buttons_bank)
    pressed_indices = []
    for idx, bit in enumerate(buttons_bits, start=1):
        is_pressed = (val & (1 << bit)) == 0  # 0 => appuyé
        if is_pressed:
            pressed_indices.append(idx)
    if len(pressed_indices) == 1:
        return pressed_indices[0]
    return 0


def run_program(
    prog_num: int,
    prog_cfg: Dict[str, Any],
    lcd: LCD20x4,
    relay_pins: Dict[str, int],
    flowmeter_pin: int,
    flow_cfg: Dict[str, Any],
    log: logging.Logger,
    buttons_reader,
) -> None:
    """
    Exécution d'un programme simple :
    - pompe ON tant que le programme tourne
    - affichage temps écoulé + volume total estimé (via débitmètre)
    - arrêt si bouton du programme rappuyé.

    buttons_reader : fonction sans argument qui renvoie le numéro de programme appuyé.
    """

    def mmss(t: float) -> str:
        t = max(0, int(t))
        m, s = divmod(t, 60)
        return f"{m:02d}:{s:02d}"

    pulses_per_liter = float(flow_cfg.get("pulses_per_liter", 450.0))
    debounce_ms = int(flow_cfg.get("debounce_ms", 5))

    # Compteurs internes au programme
    total_pulses = 0
    last_pulse_ts = 0.0

    def on_flow_pulse(channel):
        nonlocal total_pulses, last_pulse_ts
        now = time.monotonic()
        if (now - last_pulse_ts) * 1000.0 < debounce_ms:
            return
        last_pulse_ts = now
        total_pulses += 1

    # Active callback sur front descendant
    GPIO.add_event_detect(flowmeter_pin, GPIO.FALLING, callback=on_flow_pulse, bouncetime=debounce_ms)

    name = prog_cfg.get("name", f"Programme {prog_num}")
    default_duration = int(prog_cfg.get("default_duration_sec", 0))
    safety_cfg = prog_cfg.get("safety", {})
    air_cfg = safety_cfg.get("air", {})
    vic_cfg = safety_cfg.get("vic", {})  # réservé pour une implémentation future
    pump_cfg = safety_cfg.get("pump", {})

    air_mode = str(air_cfg.get("mode", "manual")).lower()
    pump_mode = str(pump_cfg.get("mode", "auto")).lower()
    pump_start = bool(pump_cfg.get("start_on_program", True))
    pump_stop = bool(pump_cfg.get("stop_on_program_end", True))

    log.info(f"PRG_START;{prog_num};name={name}")

    lcd.clear()
    lcd.write_line(1, f"Prog {prog_num}")
    lcd.write_line(2, name[:20])
    time.sleep(2)

    # Gestion AIR en début de programme
    air_pin = relay_pins.get("air")
    if air_pin is not None:
        if air_mode == "blocked":
            # Sécurité : AIR toujours OFF dans ce programme
            GPIO.output(air_pin, GPIO.LOW)
        # en mode manual : on ne touche pas au relais AIR

    # Pompe ON (relais pump actif HIGH) si autorisé par la config
    pump_pin = relay_pins.get("pump")
    if pump_pin is not None and pump_mode == "auto" and pump_start:
        GPIO.output(pump_pin, GPIO.HIGH)

    start_ts = time.monotonic()
    last_display = -1

    try:
        while True:
            now = time.monotonic()
            elapsed = now - start_ts

            # Calcul débit et volume
            liters = total_pulses / pulses_per_liter if pulses_per_liter > 0 else 0.0
            l_per_min = (total_pulses * 60.0) / pulses_per_liter / elapsed if elapsed > 0 and pulses_per_liter > 0 else 0.0

            if int(elapsed) != last_display:
                last_display = int(elapsed)
                lcd.write_line(1, f"P{prog_num} {mmss(elapsed)}")
                lcd.write_line(2, f"{l_per_min:4.0f} L/m {liters:5.1f}L")
                pompe_txt = "AUTO" if pump_mode == "auto" else "MANU"
                air_txt = "BLQ" if air_mode == "blocked" else "MANU"
                lcd.write_line(3, f"Pompe:{pompe_txt} AIR:{air_txt}")
                lcd.write_line(4, "Stop: bouton PRG")

            # Arrêt sur bouton du programme
            btn = buttons_reader()
            if btn == prog_num:
                log.info(f"PRG_STOP_BTN;{prog_num};elapsed={elapsed:.1f};liters={liters:.2f}")
                lcd.write_line(3, "Demande ARRET   ")
                time.sleep(1.5)
                break

            # Arrêt sur durée maximale si > 0
            if default_duration > 0 and elapsed >= default_duration:
                log.info(f"PRG_STOP_TIMEOUT;{prog_num};elapsed={elapsed:.1f};liters={liters:.2f}")
                lcd.write_line(3, "Temps ecoule    ")
                time.sleep(1.5)
                break

            time.sleep(0.1)

    finally:
        GPIO.remove_event_detect(flowmeter_pin)
        if pump_pin is not None and pump_mode == "auto" and pump_stop:
            GPIO.output(pump_pin, GPIO.LOW)
        lcd.write_line(3, "Pompe: OFF      ")
        time.sleep(1.0)


def main() -> None:
    exit_code = 0
    cfg = load_config()

    log = setup_logging(cfg)

    print("Initialisation GPIO...")
    step_pins, relay_pins, flowmeter_pin, buzzer_pin = gpio_setup_common(cfg)

    try:
        print("Initialisation I2C / MCP / LCD...")
        mcp1, mcp2, mcp3, lcd, bus = init_i2c_and_devices(cfg)

        motors = init_motor_manager(cfg, step_pins, mcp3)

        mode_test = bool(cfg.get("mode", {}).get("test", False))

        m1_cfg = cfg["mcp23017"]["mcp1_programs"]
        buttons_bank = m1_cfg["buttons_bank"]
        leds_bank = m1_cfg["leds_bank"]
        buttons_bits = m1_cfg["buttons_bits"]
        leds_bits = m1_cfg["leds_bits"]

        if mode_test:
            print("=== MODE TEST ===")
            lcd.clear()
            lcd.write_line(1, "MODE TEST")
            lcd.write_line(2, "Voir console Pi")

            # Suite de tests simple (tu peux en ajouter dans tests/test_basic.py)
            from i2c_devices import SMBus as _SMBus  # pour typer bus si besoin

            test_basic.test_i2c_scan(bus)
            test_basic.test_lcd(lcd)
            test_basic.test_relays(relay_pins)
            test_basic.test_buzzer(buzzer_pin)
            test_basic.test_single_motor(motors, "M1")
            test_basic.test_dual_motors(motors, "M1", "M2")

            print("Pour tester boutons/LEDs programmes :")
            print("  - Appuie sur CTRL+C pour sortir du test.")
            time.sleep(1)
            test_basic.test_program_leds_buttons(
                mcp1=mcp1,
                buttons_bank=buttons_bank,
                leds_bank=leds_bank,
                buttons_bits=buttons_bits,
                leds_bits=leds_bits,
            )

            lcd.clear()
            lcd.write_line(1, "Fin MODE TEST")
            time.sleep(2)
            return

        # --- Mode "production" ---
        progs_cfg: Dict[int, Dict[str, Any]] = {
            int(k): v for k, v in cfg.get("programs", {}).items()
        }

        lcd.clear()
        lcd.write_line(1, "Choix programme")
        lcd.write_line(2, "1..N sur bouton")

        def buttons_reader() -> int:
            return read_program_buttons(mcp1, buttons_bank, buttons_bits)

        while True:
            prog_num = buttons_reader()
            if prog_num == 0 or prog_num not in progs_cfg or not progs_cfg[prog_num].get("enabled", True):
                # IDLE : affichage périodique
                lcd.write_line(1, "Choix programme ")
                lcd.write_line(2, "1..6 PRG        ")
                time.sleep(0.1)
                continue

            prog_cfg = progs_cfg[prog_num]
            name = prog_cfg.get("name", f"Programme {prog_num}")
            print(f"Lancement programme {prog_num} - {name}")
            lcd.clear()
            lcd.write_line(1, f"Lancement P{prog_num}")
            lcd.write_line(2, name[:20])
            time.sleep(1.5)

            run_program(
                prog_num=prog_num,
                prog_cfg=prog_cfg,
                lcd=lcd,
                relay_pins=relay_pins,
                flowmeter_pin=flowmeter_pin,
                flow_cfg=cfg.get("flowmeter", {}),
                log=log,
                buttons_reader=buttons_reader,
            )

    except KeyboardInterrupt:
        print("\nInterruption par l'utilisateur (CTRL+C).")
        log.info("Interruption utilisateur (CTRL+C).")
        exit_code = 0

    except Exception as e:
        print("ERREUR :", e)
        log.exception("ERREUR fatale", exc_info=e)
        exit_code = 1

    finally:
        try:
            GPIO.cleanup()
        except Exception:
            pass
        log.info("Arrêt du programme.")
        print("Programme terminé.")
        sys.exit(exit_code)


if __name__ == "__main__":
    main()