from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from buzzer import Buzzer  # type: ignore


def main() -> None:
    with Buzzer() as bz:
        # 5 bips courts
        bz.beep(time_ms=150, power_pct=90, repeat=10, freq_hz=2000, gap_ms=100)

        time.sleep(0.5)

        # sonnerie démarrage
        bz.ringtone_startup()

        time.sleep(0.5)

        # test "continu" 2s
        bz.on(freq_hz=2000, power_pct=70)
        time.sleep(2.0)
        bz.off()


if __name__ == "__main__":
    main()