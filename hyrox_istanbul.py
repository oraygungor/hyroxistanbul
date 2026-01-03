#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
import sys
from datetime import datetime
from pathlib import Path

import requests

try:
    # Python 3.9+
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None


DEFAULT_URL = "https://turkiye.hyrox.com/checkout/hyrox-istanbul-season-25-26-y3v06t"
EXCLUDE_KEYWORDS = ["SPECTATOR", "RELAY"]  # n8n ile aynı mantık


def now_copenhagen() -> datetime:
    if ZoneInfo is None:
        # Fallback: timezone bilgisi yoksa local time kullan
        return datetime.now()
    return datetime.now(ZoneInfo("Europe/Copenhagen"))


def date_filename(dt: datetime) -> str:
    # 03.01.2026.json formatı
    return dt.strftime("%d.%m.%Y") + ".json"


def fetch_html(url: str, timeout: int = 20) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.7,en;q=0.6",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text


def extract_next_data(html: str) -> dict:
    # <script id="__NEXT_DATA__" type="application/json"> ... </script>
    m = re.search(
        r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not m:
        raise ValueError("__NEXT_DATA__ script tag bulunamadı.")
    raw = m.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"__NEXT_DATA__ JSON parse hatası: {e}") from e


def build_inventory(next_data: dict) -> dict:
    event = (
        next_data.get("props", {})
        .get("pageProps", {})
        .get("event", {})
    )

    tickets = event.get("tickets", []) or []
    categories = event.get("categories", []) or []

    cat_map = {c.get("ref"): (c.get("name") or "Unknown") for c in categories}

    rows = []
    for t in tickets:
        name = (t.get("name") or "").strip()
        if not name:
            continue

        upper = name.upper()
        if any(k in upper for k in EXCLUDE_KEYWORDS):
            continue

        active = bool(t.get("active"))
        stock = int(t.get("v") or 0)
        style = t.get("styleOptions") or {}
        hidden = bool(style.get("hiddenInSelectionArea"))

        if active and stock > 0 and not hidden:
            parkur = cat_map.get(t.get("categoryRef"), "Unknown")
            rows.append({"parkur": parkur, "ticket": name, "stock": stock})

    # parkur -> ticket -> stock
    by_parkur = {}
    for r in rows:
        p = r["parkur"]
        n = r["ticket"]
        s = r["stock"]
        by_parkur.setdefault(p, {})
        # aynı ticket birden fazla kez gelirse toplasın:
        by_parkur[p][n] = by_parkur[p].get(n, 0) + s

    return {"tickets": rows, "by_parkur": by_parkur}


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")

    dt = now_copenhagen()
    out_path = out_dir / date_filename(dt)

    html = fetch_html(url)
    next_data = extract_next_data(html)
    inv = build_inventory(next_data)

    payload = {
        "event_url": url,
        "fetched_at": dt.isoformat(),
        **inv,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Konsola kısa özet
    total = sum(len(v) for v in payload["by_parkur"].values())
    print(f"OK: {out_path} yazıldı. (parkur içi ticket çeşit sayısı: {total})")
    for parkur, items in payload["by_parkur"].items():
        print(f"- {parkur}: {len(items)} çeşit")

if __name__ == "__main__":
    main()
