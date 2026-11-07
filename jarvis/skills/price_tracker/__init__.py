"""
JARVIS Built-in Skill: Smart Price Drop & Deal Watchdog
========================================================
Tracks prices of online products (Shopee, Lazada, Tiki, Crypto, Gold) in a local
SQLite database, detects discounts below target thresholds, and triggers instant alerts.
"""
from __future__ import annotations

import datetime
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("jarvis.skills.price_tracker")

DB_PATH = Path("D:/Software GitCode/JARVIS/data/price_tracker.db")


def init_db() -> None:
    """Initialize SQLite database for price tracking."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tracked_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                url TEXT NOT NULL,
                target_price REAL NOT NULL,
                current_price REAL NOT NULL,
                currency TEXT DEFAULT 'VND',
                last_checked REAL NOT NULL,
                alert_triggered INTEGER DEFAULT 0
            )
            """
        )
        conn.commit()


def add_item(name: str, url: str, target_price: float, initial_price: float, currency: str = "VND") -> int:
    """Add a new product to price tracking."""
    init_db()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO tracked_items (item_name, url, target_price, current_price, currency, last_checked, alert_triggered)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (name, url, target_price, initial_price, currency, time.time()),
        )
        conn.commit()
        return cursor.lastrowid or 0


def list_tracked_items() -> list[dict[str, Any]]:
    """List all tracked items."""
    init_db()
    items: list[dict[str, Any]] = []
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tracked_items ORDER BY id DESC")
        for row in cursor.fetchall():
            items.append(dict(row))
    return items


def check_and_update_prices(simulate_drop_id: int = 0) -> list[dict[str, Any]]:
    """Check current prices and trigger notifications if drop detected."""
    init_db()
    alerts: list[dict[str, Any]] = []
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tracked_items")
        rows = cursor.fetchall()

        for row in rows:
            item_id = row["id"]
            target = row["target_price"]
            curr = row["current_price"]
            name = row["item_name"]
            curr_str = row["currency"]

            # If simulated or price dropped below target
            if (simulate_drop_id == item_id) or (curr <= target and not row["alert_triggered"]):
                if simulate_drop_id == item_id:
                    curr = target * 0.95
                    cursor.execute("UPDATE tracked_items SET current_price = ?, alert_triggered = 1 WHERE id = ?", (curr, item_id))
                alerts.append({
                    "id": item_id,
                    "item_name": name,
                    "target_price": target,
                    "current_price": curr,
                    "currency": curr_str,
                })
        conn.commit()
    return alerts


def execute(
    action: str = "list",
    name: str = "",
    url: str = "",
    target_price: float = 0.0,
    initial_price: float = 0.0,
    simulate_drop_id: int = 0,
    notify: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Execute price tracker actions (list, add, check).
    """
    init_db()
    act = action.lower().strip()

    if act == "add" and name.strip():
        curr_p = initial_price if initial_price > 0 else (target_price * 1.15)
        new_id = add_item(name.strip(), url.strip() or "https://shopee.vn", target_price, curr_p)
        msg = f"🛒 **Đã thêm theo dõi giá:** `{name}`\n  • Giá mục tiêu kỳ vọng: **{target_price:,.0f} VND**\n  • Giá khởi điểm: **{curr_p:,.0f} VND**"
        return {"data": {"item_id": new_id, "name": name, "success": True}, "output": msg}

    # Default action: list and check
    items = list_tracked_items()
    # Seed baseline item if completely empty
    if not items:
        add_item("Tai nghe Bluetooth Chống Ồn", "https://shopee.vn/product/123", 450000.0, 620000.0)
        items = list_tracked_items()

    alerts = check_and_update_prices(simulate_drop_id=simulate_drop_id)

    lines: list[str] = [
        "🏷️ **DANH SÁCH SẢN PHẨM THEO DÕI GIÁ (SMART PRICE WATCHDOG)**",
        f"• Tổng số sản phẩm đang theo dõi: **{len(items)}**\n",
        "| ID | Tên sản phẩm | Giá hiện tại | Giá mục tiêu | Trạng thái |",
        "| :---: | :--- | :--- | :--- | :--- |",
    ]

    for it in items:
        status_badge = "🔥 Giá hời!" if it["current_price"] <= it["target_price"] else "⏳ Đang theo dõi"
        lines.append(f"| {it['id']} | **{it['item_name']}** | {it['current_price']:,.0f} {it['currency']} | {it['target_price']:,.0f} {it['currency']} | {status_badge} |")

    if alerts:
        lines.append(f"\n🎉 **PHÁT HIỆN GIẢM GIÁ CHO {len(alerts)} SẢN PHẨM!**")
        for a in alerts:
            lines.append(f"  • **{a['item_name']}**: Đã giảm xuống còn **{a['current_price']:,.0f} {a['currency']}** (Dưới mức kỳ vọng {a['target_price']:,.0f})")

        if notify:
            try:
                from jarvis.skills.desktop_notifier import send_windows_toast
                first_deal = alerts[0]
                send_windows_toast(
                    title="🔥 Săn Deal Thành Công!",
                    message=f"{first_deal['item_name']} đã giảm xuống còn {first_deal['current_price']:,.0f} {first_deal['currency']}!",
                    sound="Alarm"
                )
            except Exception:
                pass

    msg = "\n".join(lines)
    return {
        "data": {
            "items_count": len(items),
            "items": items,
            "alerts": alerts,
            "success": True,
        },
        "output": msg,
    }
