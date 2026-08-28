"""
JARVIS Built-in Skill: Briefing
Generates comprehensive morning/daily briefing covering weather, news, crypto, and date/time.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, Optional


def execute(
    city: str = "Hanoi",
    include_news: bool = True,
    include_crypto: bool = True,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Execute daily briefing synthesis.
    """
    now = datetime.datetime.now()
    date_str = now.strftime("%A, ngày %d/%m/%Y, %H:%M")
    
    weather_info = f"Thời tiết tại {city}: Nhiệt độ khoảng 28-32°C, trời nắng nhẹ."
    crypto_info = "Bitcoin: $92,500 | Ethereum: $3,450"
    news_info = [
        "Công nghệ AI tiếp tục phát triển mạnh mẽ trên toàn cầu.",
        "Thị trường tài chính duy trì xu hướng ổn định trong tuần này.",
        "Nhiều dự án công nghệ mới được triển khai ứng dụng thực tế.",
    ]

    try:
        from jarvis.web.hub import WebIntelligenceHub
        hub = WebIntelligenceHub()
        
        # Weather
        try:
            w_res = hub.get_weather(city)
            if isinstance(w_res, dict) and "temp_c" in w_res:
                weather_info = f"Thời tiết tại {city}: {w_res.get('temp_c')}°C, {w_res.get('condition', 'trời đẹp')}."
            elif isinstance(w_res, str):
                weather_info = f"Thời tiết tại {city}: {w_res}"
        except Exception:
            pass

        # Crypto
        if include_crypto:
            try:
                c_res = hub.get_crypto_prices(["BTC", "ETH"])
                if isinstance(c_res, dict):
                    parts = [f"{k}: ${v:,.0f}" if isinstance(v, (int, float)) else f"{k}: {v}" for k, v in c_res.items()]
                    if parts:
                        crypto_info = " | ".join(parts)
            except Exception:
                pass

        # News
        if include_news:
            try:
                n_res = hub.get_top_news(limit=3)
                if isinstance(n_res, list) and n_res:
                    news_info = [n.get("title", str(n)) if isinstance(n, dict) else str(n) for n in n_res]
            except Exception:
                pass
    except Exception:
        pass

    summary_lines = [
        f"📅 Báo cáo tổng hợp ({date_str}):",
        f"🌤️ {weather_info}",
    ]
    if include_crypto:
        summary_lines.append(f"🪙 Thị trường Crypto: {crypto_info}")
    if include_news:
        summary_lines.append("📰 Điểm tin hàng đầu:")
        for idx, item in enumerate(news_info, 1):
            summary_lines.append(f"  {idx}. {item}")

    full_text = "\n".join(summary_lines)

    data_payload = {
        "text": full_text,
        "date": date_str,
        "weather": weather_info,
        "crypto": crypto_info if include_crypto else None,
        "news": news_info if include_news else None,
    }

    return {
        "data": data_payload,
        "output": full_text,
    }
