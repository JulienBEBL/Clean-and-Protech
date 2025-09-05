#!/usr/bin/python3
import time
from lib.MCP3008_0 import MCP3008_0
from lib.MCP3008_1 import MCP3008_1

SEUIL = 1000  # à ajuster si besoin

if __name__ == "__main__":
    mcp1 = MCP3008_0()
    mcp2 = MCP3008_1()
    print("[TEST] Entrées : programmes (MCP2: ch 0..7), sélecteur (MCP1: ch 0..4), air (MCP1: ch 5)")
    try:
        while True:
            btn_raw   = [mcp2.read(i) for i in range(8)]
            selec_raw = [mcp1.read(i) for i in range(5)]
            air_raw   = mcp1.read(5)

            btn_state   = [1 if v>SEUIL else 0 for v in btn_raw]
            selec_state = [1 if v>SEUIL else 0 for v in selec_raw]
            air_state   = 1 if air_raw>SEUIL else 0

            print(f"BTN raw   : {btn_raw}   -> {btn_state}")
            print(f"SELEC raw : {selec_raw} -> {selec_state}")
            print(f"AIR  raw  : {air_raw:4d} -> {air_state}")
            print("-"*80)
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        mcp1.close(); mcp2.close()
