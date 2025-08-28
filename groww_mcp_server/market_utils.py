"""
Market utilities for checking Indian stock market hours.
"""

from datetime import datetime, time
from typing import Dict, Any
import pytz

# Indian timezone
IST = pytz.timezone('Asia/Kolkata')

# Market hours (IST)
MARKET_OPEN = time(9, 15)  # 9:15 AM
MARKET_CLOSE = time(15, 30)  # 3:30 PM
PRE_MARKET_OPEN = time(9, 0)  # 9:00 AM
POST_MARKET_CLOSE = time(16, 0)  # 4:00 PM


def get_ist_now() -> datetime:
    """Get current time in IST."""
    return datetime.now(IST)


def is_market_day(dt: datetime = None) -> bool:
    """Check if the given date is a market trading day (Monday-Friday)."""
    if dt is None:
        dt = get_ist_now()

    # Monday=0, Sunday=6
    return dt.weekday() < 5  # Monday to Friday


def is_market_hours(dt: datetime = None) -> bool:
    """Check if current time is during regular market hours (9:15 AM - 3:30 PM IST)."""
    if dt is None:
        dt = get_ist_now()

    if not is_market_day(dt):
        return False

    current_time = dt.time()
    return MARKET_OPEN <= current_time <= MARKET_CLOSE


def is_pre_market_hours(dt: datetime = None) -> bool:
    """Check if current time is during pre-market hours (9:00 AM - 9:15 AM IST)."""
    if dt is None:
        dt = get_ist_now()

    if not is_market_day(dt):
        return False

    current_time = dt.time()
    return PRE_MARKET_OPEN <= current_time < MARKET_OPEN


def is_post_market_hours(dt: datetime = None) -> bool:
    """Check if current time is during post-market hours (3:30 PM - 4:00 PM IST)."""
    if dt is None:
        dt = get_ist_now()

    if not is_market_day(dt):
        return False

    current_time = dt.time()
    return MARKET_CLOSE < current_time <= POST_MARKET_CLOSE


def is_extended_hours(dt: datetime = None) -> bool:
    """Check if current time is during extended hours (pre + regular + post market)."""
    if dt is None:
        dt = get_ist_now()

    return is_pre_market_hours(dt) or is_market_hours(dt) or is_post_market_hours(dt)


def get_market_status(dt: datetime = None) -> Dict[str, Any]:
    """Get comprehensive market status information."""
    if dt is None:
        dt = get_ist_now()

    is_trading_day = is_market_day(dt)
    is_regular_hours = is_market_hours(dt)
    is_pre_market = is_pre_market_hours(dt)
    is_post_market = is_post_market_hours(dt)

    # Determine status
    if not is_trading_day:
        status = "CLOSED - Weekend/Holiday"
        next_session = get_next_market_open(dt)
    elif is_regular_hours:
        status = "OPEN - Regular Trading"
        next_session = get_next_market_close(dt)
    elif is_pre_market:
        status = "PRE-MARKET"
        next_session = get_next_market_open(dt)
    elif is_post_market:
        status = "POST-MARKET"
        next_session = get_next_market_open(dt)
    else:
        status = "CLOSED - After Hours"
        next_session = get_next_market_open(dt)

    return {
        "current_time": dt.strftime('%Y-%m-%d %H:%M:%S %Z'),
        "status": status,
        "is_trading_day": is_trading_day,
        "is_market_hours": is_regular_hours,
        "is_pre_market": is_pre_market,
        "is_post_market": is_post_market,
        "is_extended_hours": is_extended_hours(dt),
        "next_session": next_session,
        "market_open": "9:15 AM IST",
        "market_close": "3:30 PM IST"
    }


def get_next_market_open(dt: datetime = None) -> str:
    """Get the next market opening time."""
    if dt is None:
        dt = get_ist_now()

    # If it's a weekday and before market open, next open is today
    if is_market_day(dt) and dt.time() < MARKET_OPEN:
        return f"Today at 9:15 AM IST"

    # Otherwise, find next weekday
    current_weekday = dt.weekday()

    if current_weekday < 4:  # Monday to Thursday
        return "Tomorrow at 9:15 AM IST"
    elif current_weekday == 4:  # Friday
        return "Monday at 9:15 AM IST"
    elif current_weekday == 5:  # Saturday
        return "Monday at 9:15 AM IST"
    else:  # Sunday
        return "Tomorrow at 9:15 AM IST"


def get_next_market_close(dt: datetime = None) -> str:
    """Get the next market closing time."""
    if dt is None:
        dt = get_ist_now()

    if is_market_hours(dt):
        return "Today at 3:30 PM IST"

    return get_next_market_open(dt).replace("9:15 AM", "3:30 PM")


def should_monitor_alerts(dt: datetime = None) -> bool:
    """Determine if we should actively monitor alerts based on market hours."""
    if dt is None:
        dt = get_ist_now()

    # Monitor during regular market hours and slightly extended
    return is_market_hours(dt) or is_pre_market_hours(dt)


def get_monitoring_interval(dt: datetime = None) -> int:
    """Get appropriate monitoring interval in seconds based on market status."""
    if dt is None:
        dt = get_ist_now()

    if is_market_hours(dt):
        return 180  # 3 minutes during regular hours
    elif is_pre_market_hours(dt):
        return 300  # 5 minutes during pre-market
    else:
        return 3600  # 1 hour when market is closed (for minimal checking)


def time_until_next_session(dt: datetime = None) -> int:
    """Get seconds until next market session starts."""
    if dt is None:
        dt = get_ist_now()

    # This is a simplified version - in practice you'd calculate exact time differences
    if is_market_day(dt) and dt.time() < MARKET_OPEN:
        # Market opens today
        market_open_today = dt.replace(
            hour=9, minute=15, second=0, microsecond=0)
        return int((market_open_today - dt).total_seconds())

    # Default to checking in 1 hour
    return 3600
