from time import monotonic

def format_mmss(seconds: int) -> str:
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"

def throttle(last_call_time: float, interval: float) -> bool:
    return (monotonic() - last_call_time) >= interval
