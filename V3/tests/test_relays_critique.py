from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from relays_critique import RelaysCritique  # type: ignore


def main() -> None:
    with RelaysCritique() as r:
        print("RelaysCritique test (Ctrl+C)")

        # 1) AIR ON 2s (non bloquant)
        print("AIR ON for 2s")
        r.set_air_on(time_s=5.0)
        t0 = time.monotonic()
        while time.monotonic() - t0 < 6.0:
            r.tick()
            time.sleep(0.05)

        # 2) AIR ON indéfini 2s puis OFF
        print("AIR ON (manual) 2s")
        r.set_air_on()
        time.sleep(2.0)
        print("AIR OFF")
        r.set_air_off()

        # 3) POMPE OFF pulse (bloquant, 250ms)
        print("POMPE OFF pulse 250ms (blocking)")
        r.set_pompe_off()

        # 4) POMPE OFF pulse async (non bloquant)
        print("POMPE OFF pulse 250ms (async)")
        r.set_pompe_off_async()
        t0 = time.monotonic()
        while time.monotonic() - t0 < 1.0:
            r.tick()
            time.sleep(0.02)

        print("Done.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user.")
