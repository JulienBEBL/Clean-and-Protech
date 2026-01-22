#!/usr/bin/env python3
import time

try:
    from smbus2 import SMBus
except ImportError:
    raise SystemExit("Installe smbus2:  sudo apt update && sudo apt install -y python3-smbus  ||  pip3 install smbus2")

# ---- Réglages ----
I2C_BUS = 1
MCP23017_ADDR = 0x20  # A2=A1=A0=0

# Registres MCP23017 (mode IOCON.BANK=0 par défaut)
IODIRA = 0x00  # Direction Port A
GPPUA  = 0x0C  # Pull-up Port A
GPIOA  = 0x12  # Lecture Port A (GPIO)

PIN_A7_MASK = 1 << 7

def set_bit(value, bit, state: bool):
    if state:
        return value | (1 << bit)
    return value & ~(1 << bit)

with SMBus(I2C_BUS) as bus:
    # 1) Mettre GPIOA7 en entrée (bit=1), laisser les autres inchangés
    iodira = bus.read_byte_data(MCP23017_ADDR, IODIRA)
    iodira = set_bit(iodira, 7, True)  # A7 input
    bus.write_byte_data(MCP23017_ADDR, IODIRA, iodira)

    # 2) Option: activer le pull-up interne sur A7 (utile si bouton vers GND, etc.)
    gppua = bus.read_byte_data(MCP23017_ADDR, GPPUA)
    gppua = set_bit(gppua, 7, True)    # pull-up A7 ON
    bus.write_byte_data(MCP23017_ADDR, GPPUA, gppua)

    print(f"IODIRA=0x{iodira:02X}  GPPUA=0x{gppua:02X}")
    print("Lecture continue de GPIOA7 (Ctrl+C pour arrêter)")

    while True:
        gpioa = bus.read_byte_data(MCP23017_ADDR, GPIOA)
        a7 = 1 if (gpioa & PIN_A7_MASK) else 0
        print(f"GPIOA=0x{gpioa:02X}  A7={a7}")
        time.sleep(0.05)  # 50 ms
