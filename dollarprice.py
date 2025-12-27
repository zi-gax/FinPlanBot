import re
import json
from datetime import date, datetime
import os
import requests

DATA_FILE = "usd_price_data.json"


def fetch_usd_price():
    """Attempt to fetch USD price (Toman) using a lightweight HTTP request.

    This avoids using Selenium/webdriver_manager at runtime which requires network
    access to download drivers. Returns integer price (Toman) or None on failure.
    """
    url = "https://alanchand.com/currencies-price/usd"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; FinPlanBot/1.0; +https://example.com)"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        html = resp.text
        # Look for numbers like 123,456 or 1,234,567
        match = re.search(r"(\d{1,3}(?:,\d{3})+)", html)
        if match:
            return int(match.group(1).replace(",", ""))
    except Exception:
        # network failure or parsing failure; fall through to return None
        return None
    return None


def get_usd_price():
    """Return cached USD price if present for the current hour, otherwise fetch.

    The cache now uses an hourly `timestamp` (YYYY-MM-DDTHH). For backward
    compatibility we also accept the older daily `date` key.
    """
    today = str(date.today())  # مثال: 2025-01-15
    now = datetime.now()
    current_hour = now.strftime("%Y-%m-%dT%H")

    # اگر فایل وجود داره
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception:
                data = {}

        # If we have an hourly timestamp, check its age (in seconds)
        ts = data.get("timestamp")
        if ts:
            try:
                stored_dt = datetime.strptime(ts, "%Y-%m-%dT%H")
                age_seconds = (now - stored_dt).total_seconds()
                if age_seconds < 3600:
                    return data.get("price")
            except Exception:
                # parsing error => ignore and fetch new price
                pass

        # Backward-compatibility: if only daily `date` exists and it's today,
        # return it (older installs) — otherwise we'll fetch new price.
        if not ts and data.get("date") == today and data.get("price") is not None:
            return data.get("price")

    # فایل وجود ندارد یا cache قدیمی است → قیمت جدید
    price = fetch_usd_price()

    if price is None:
        return 135000

    # ذخیره قیمت جدید with hourly timestamp
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({"date": today, "timestamp": current_hour, "price": price}, f, ensure_ascii=False)

    return price

# from dollarprice import get_usd_price
# usdprice = get_usd_price()