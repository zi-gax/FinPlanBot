import re
import json
from datetime import date
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
    today = str(date.today())  # مثال: 2025-01-15

    # اگر فایل وجود داره
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # اگر مال امروز بود
        if data.get("date") == today:
            return data.get("price")

    # اگر فایل نبود یا تاریخ قدیمی بود → قیمت جدید
    price = fetch_usd_price()

    if price is None:
        return 135000

    # ذخیره قیمت جدید
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"date": today, "price": price},
            f,
            ensure_ascii=False
        )

    return price

# from dollarprice import get_usd_price
# usdprice = get_usd_price()