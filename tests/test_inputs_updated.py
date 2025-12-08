#!/usr/bin/python3
# -*- coding: utf-8 -*-

import time
import RPi.GPIO as GPIO

from libs_tests.MCP3008_0 import MCP3008_0
from libs_tests.MCP3008_1 import MCP3008_1


class MCPButtonFilter:
    def __init__(self, mcp, channel_count=8,
                 seuil_haut=1000, seuil_bas=700,
                 samples=15, stable_ms=300):
        self.mcp = mcp
        self.N = channel_count
        self.samples = samples
        self.seuil_haut = seuil_haut
        self.seuil_bas = seuil_bas
        self.stable_ms = stable_ms / 1000.0

        self.raw_values = [0] * self.N
        self.state = [0] * self.N
        self.last_change_ts = [0] * self.N

    def read_raw_avg(self, ch):
        total = 0
        for _ in range(self.samples):
            total += self.mcp.read(ch)
        return total // self.samples

    def update(self):
        now = time.monotonic()
        for ch in range(self.N):
            v = self.read_raw_avg(ch)
            self.raw_values[ch] = v

            target_state = self.state[ch]
            if v > self.seuil_haut:
                target_state = 1
            elif v < self.seuil_bas:
                target_state = 0

            if target_state != self.state[ch]:
                if self.last_change_ts[ch] == 0:
                    self.last_change_ts[ch] = now
                elif now - self.last_change_ts[ch] >= self.stable_ms:
                    self.state[ch] = target_state
                    self.last_change_ts[ch] = 0
            else:
                self.last_change_ts[ch] = 0

        return self.state

    def get_single_pressed(self):
        st = self.update()
        if st.count(1) == 1:
            return st.index(1) + 1
        return 0


class MCPSelectorFilter:
    def __init__(self, mcp, channel_count=5,
                 seuil_haut=1000, seuil_bas=400,
                 samples=15, stable_ms=300):
        self.mcp = mcp
        self.N = channel_count
        self.samples = samples
        self.seuil_haut = seuil_haut
        self.seuil_bas = seuil_bas
        self.stable_ms = stable_ms / 1000.0

        self.raw_values = [0] * self.N
        self.state = [0] * self.N
        self.last_change_ts = [0] * self.N

    def read_raw_avg(self, ch):
        total = 0
        for _ in range(self.samples):
            total += self.mcp.read(ch)
        return total // self.samples

    def update(self):
        now = time.monotonic()
        for ch in range(self.N):
            v = self.read_raw_avg(ch)
            self.raw_values[ch] = v

            target_state = self.state[ch]
            if v > self.seuil_haut:
                target_state = 1
            elif v < self.seuil_bas:
                target_state = 0

            if target_state != self.state[ch]:
                if self.last_change_ts[ch] == 0:
                    self.last_change_ts[ch] = now
                elif now - self.last_change_ts[ch] >= self.stable_ms:
                    self.state[ch] = target_state
                    self.last_change_ts[ch] = 0
            else:
                self.last_change_ts[ch] = 0

        if self.state.count(1) == 1:
            return self.state.index(1)
        return None


def main():
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)

    mcp1 = MCP3008_0()  # sélecteur V4V
    mcp2 = MCP3008_1()  # boutons programmes

    btn_filter = MCPButtonFilter(mcp2)
    sel_filter = MCPSelectorFilter(mcp1)

    print("Test MCP : CTRL-C pour quitter.")
    try:
        while True:
            # Boutons programmes
            btn_state = btn_filter.update()
            if btn_state.count(1) == 1:
                num_prg = btn_state.index(1) + 1
            else:
                num_prg = 0

            # Sélecteur V4V
            sel_idx = sel_filter.update()  # 0..4 ou None

            print(
                f"BTN_RAW={btn_filter.raw_values}  "
                f"BTN_STATE={btn_state}  num_prg={num_prg} | "
                f"SEL_RAW={sel_filter.raw_values}  SEL_STATE={sel_filter.state}  SEL_IDX={sel_idx}"
            )

            time.sleep(0.2)

    except KeyboardInterrupt:
        print("\n[STOP] Test interrompu par l'utilisateur.")
    finally:
        mcp1.close()
        mcp2.close()
        GPIO.cleanup()


if __name__ == "__main__":
    main()
