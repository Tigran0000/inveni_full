from datetime import datetime
import pytz
from typing import Dict, Tuple

def get_current_times() -> Dict[str, str]:
    """Get both UTC and local time."""
    now_utc = datetime.now(pytz.UTC)
    now_local = now_utc.astimezone()
    
    return {
        "utc": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "local": now_local.strftime("%Y-%m-%d %H:%M:%S %Z")
    }

def format_timestamp_dual(timestamp_str: str) -> Tuple[str, str]:
    """Convert UTC timestamp to both UTC and local time strings."""
    try:
        dt_utc = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        dt_utc = pytz.UTC.localize(dt_utc)
        dt_local = dt_utc.astimezone()
        
        return (
            dt_utc.strftime("%Y-%m-%d %H:%M:%S"),
            dt_local.strftime("%Y-%m-%d %H:%M:%S %Z")
        )
    except Exception:
        return ("Unknown", "Unknown")

def get_formatted_time() -> str:
    """Get current UTC time."""
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")