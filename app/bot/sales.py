"""What was sold in the last week, day by day.

Every sale is written down as it happens (card, wallet, weekly credit, invoice),
because none of those leave a usable trail on their own: a card sale is only an
approved receipt, a wallet sale touches nothing but two balances, and weekly
credit shows up as a debt that later disappears when it is paid.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import texts
from .. import db

TEHRAN = ZoneInfo("Asia/Tehran")
DAYS = 7

# Python's weekday(): Monday is 0.
WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه", "شنبه", "یک‌شنبه"]

_GREGORIAN_MONTH_DAYS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]


def to_jalali(year: int, month: int, day: int) -> tuple[int, int, int]:
    """Gregorian to Jalali. The dates in this report are read by someone working
    in the Persian calendar, so they are shown in it."""
    leap_reference = year + 1 if month > 2 else year
    days = (
        355666
        + (365 * year)
        + ((leap_reference + 3) // 4)
        - ((leap_reference + 99) // 100)
        + ((leap_reference + 399) // 400)
        + day
        + _GREGORIAN_MONTH_DAYS[month - 1]
    )
    jalali_year = -1595 + (33 * (days // 12053))
    days %= 12053
    jalali_year += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jalali_year += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jalali_year, 1 + (days // 31), 1 + (days % 31)
    return jalali_year, 7 + ((days - 186) // 30), 1 + ((days - 186) % 30)


def format_day(day) -> str:
    year, month, date = to_jalali(day.year, day.month, day.day)
    return f"{year}/{month:02d}/{date:02d} · {WEEKDAYS[day.weekday()]}"


def record(*, telegram_id: int | None, username: str | None, gb: float, amount: int, method: str) -> None:
    db.record_sale(
        telegram_id=telegram_id, username=username, gb=gb, amount=amount, method=method
    )


def report(now: datetime | None = None, days: int = DAYS) -> str:
    now = now or datetime.now(TEHRAN)
    first_day = (now - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    sales = db.list_sales_since(first_day.astimezone(timezone.utc).isoformat())
    if not sales:
        return texts.SALES_EMPTY

    per_day: dict[object, dict] = {}
    per_method: dict[str, int] = {}
    for sale in sales:
        try:
            when = datetime.fromisoformat(sale.created_at).astimezone(TEHRAN).date()
        except Exception:
            continue
        bucket = per_day.setdefault(when, {"amount": 0, "gb": 0.0, "count": 0})
        bucket["amount"] += sale.amount
        bucket["gb"] += sale.gb
        bucket["count"] += 1
        per_method[sale.method] = per_method.get(sale.method, 0) + 1

    text = texts.SALES_HEADER
    # Today first: the most recent day is the one being checked on.
    for offset in range(days):
        day = (now - timedelta(days=offset)).date()
        bucket = per_day.get(day)
        if bucket:
            text += texts.SALES_DAY_LINE.format(
                day=format_day(day),
                amount=bucket["amount"],
                gb=round(bucket["gb"], 2),
                count=bucket["count"],
            )
        else:
            text += texts.SALES_DAY_EMPTY.format(day=format_day(day))

    total = sum(b["amount"] for b in per_day.values())
    total_gb = round(sum(b["gb"] for b in per_day.values()), 2)
    breakdown = " · ".join(
        f"{texts.SALES_METHOD_LABELS.get(method, method)} {count}"
        for method, count in sorted(per_method.items(), key=lambda kv: kv[1], reverse=True)
    )
    return text + texts.SALES_FOOTER.format(
        total=total,
        gb=total_gb,
        average=round(total / days),
        count=sum(b["count"] for b in per_day.values()),
        methods=breakdown,
    )
