def seconds_to_hhmmss(seconds: float) -> str:
    """Converts a float of seconds to HH:MM:SS format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02}:{minutes:02}:{secs:02}"

def hhmmss_to_seconds(ts: str) -> float:
    """Converts HH:MM:SS string to a float of seconds."""
    parts = list(map(int, ts.split(':')))
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2: # MM:SS
        return parts[0] * 60 + parts[1]
    elif len(parts) == 1: # SS
        return parts[0]
    else:
        raise ValueError("Invalid time format. Expected HH:MM:SS, MM:SS, or SS.")
