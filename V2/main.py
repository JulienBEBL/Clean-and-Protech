# main.py
from __future__ import annotations

import time

from core.logging_setup import setup_logging

from hal.i2c_bus import I2CBus, I2CConfig, scan_i2c
from hw.mcp_hub import MCPHub, McpAddressing

from hal.gpio_lgpio import GpioLgpio
from driver.motors import Motors, MotorsConfig

# Tes libs existantes (mets-les dans un dossier libs/ par exemple)
from relays_critical import CriticalRelays  # :contentReference[oaicite:4]{index=4}
from flowmeter_yfdn50 import FlowMeterYFDN50, FlowMeterConfig  # :contentReference[oaicite:5]{index=5}
from lcd_i2c_20x4 import LCDI2C_backpack  # :contentReference[oaicite:6]{index=6}


def appliquer_safe(log, relays: CriticalRelays, motors: Motors) -> None:
    # SAFE : pompe off, EV off, moteurs OFF
    relays.all_off()
    motors.stop_all()
    motors.disable_all()
    log.info("SAFE appliqué (relais OFF, moteurs OFF)")


def main() -> None:
    log = setup_logging("/var/log/machine_ctrl", level="INFO")

    # --- I2C + MCPHub ---
    bus = I2CBus(I2CConfig(bus=1, retries=3, retry_delay_s=0.01))
    found = scan_i2c(bus)
    log.info("I2C détectés: %s", [hex(a) for a in found])

    # Adresses actuelles (à déplacer ensuite dans config.yaml)
    addrs = McpAddressing(mcp1=0x24, mcp2=0x25, mcp3=0x26)
    mcp = MCPHub(bus, addrs)
    mcp.init_all()
    log.info("MCPHub initialisé")

    # --- LCD (ta lib) ---
    lcd = LCDI2C_backpack(I2C_ADDR=0x27)
    lcd.clear()

    # --- Relais critiques (ta lib) ---
    # Dans ta lib: pin_air=16, pin_pump=20 par défaut, active_high=True OK. :contentReference[oaicite:7]{index=7}
    relays = CriticalRelays(pin_air=16, pin_pump=20, active_high_air=True, active_high_pump=True)

    # --- Débitmètre (ta lib) ---
    # pulses_per_liter à ajuster plus tard (K). Ici valeur placeholder.
    fm_cfg = FlowMeterConfig(
        gpio_bcm=21,
        pulses_per_liter=12.0,
        sample_period_s=1.0,
    )
    flow = FlowMeterYFDN50(cfg=fm_cfg)
    flow.start()
    log.info("Flowmeter démarré")

    # --- Moteurs (lgpio STEP + MCP DIR/ENA) ---
    gpio = GpioLgpio(chip=0)
    step_pins = {
        "M1": 17, "M2": 27, "M3": 22, "M4": 5,
        "M5": 18, "M6": 23, "M7": 24, "M8": 25,
    }
    motors = Motors(
        gpio=gpio,
        mcp=mcp,
        step_pins=step_pins,
        cfg=MotorsConfig(microsteps_per_rev=3200),
    )
    log.info("Moteurs initialisés (STEP lgpio, DIR/ENA MCP)")

    # SAFE au boot
    appliquer_safe(log, relays, motors)

    # --- UI IDLE ---
    lcd.lcd_string("Choix programme", lcd.LCD_LINE_1)
    lcd.lcd_string("1..5", lcd.LCD_LINE_2)
    lcd.lcd_string("Volume total: --.-L", lcd.LCD_LINE_3)
    lcd.lcd_string("Pompe: OFF", lcd.LCD_LINE_4)

    # --- Boucle minimale ---
    try:
        while True:
            # Affichage débit/total (exemple, sans gestion programme pour l'instant)
            flow_l_min = flow.get_flow_l_min()
            total_l = flow.get_total_liters()

            lcd.lcd_string(f"Debit: {flow_l_min:6.1f} L/min", lcd.LCD_LINE_3)
            lcd.lcd_string(f"Total: {total_l:6.1f} L", lcd.LCD_LINE_4)

            time.sleep(1.0)

    except KeyboardInterrupt:
        log.info("Arrêt demandé (Ctrl+C)")

    finally:
        # SAFE avant sortie
        try:
            appliquer_safe(log, relays, motors)
        except Exception as e:
            log.error("Erreur pendant SAFE: %s", e)

        # Stop flowmeter (ne fait pas cleanup global GPIO par défaut)
        try:
            flow.stop()
        except Exception:
            pass

        # IMPORTANT: relays.cleanup() fait GPIO.cleanup() global (risque de perturber d'autres modules RPi.GPIO)
        # Ici on évite cleanup global; à faire seulement si tu es sûr que plus rien n'utilise RPi.GPIO.
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

        log.info("Arrêt propre terminé")


if __name__ == "__main__":
    main()
