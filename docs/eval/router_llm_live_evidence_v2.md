# Evidence — GATE-05 Router LLM Live Reasoning Benchmark (PASS runtime)

**Date**: 2026-09-20  
**Auditor**: `scripts/test_router_llm_live.py` — automated, no self-assessment  
**Model**: `gemini-flash-lite-latest` (Google Gemini API)  
**API Key**: `GEMINI_API_KEY` (`AIzaSy...`, 39 chars, valid format) — updated 2026-09-20  
**Integrity**: AGENTS.md §2 Anti-Fabrication Principle — real HTTP calls, no mock

---

## Kết quả Benchmark N=10

| # | Command (VI) | Expected | Routed | Latency | Result |
|---|---|---|---|---|---|
| 1 | `mở Chrome` | `open_app` | `open_app` | 1815ms | ✅ PASS |
| 2 | `tìm kiếm thời tiết hôm nay` | `web_search` | `weather_query` | 728ms | ❌ FAIL* |
| 3 | `tăng âm lượng lên 50%` | `volume_control` | `volume_control` | 1045ms | ✅ PASS |
| 4 | `đặt hẹn giờ 10 phút` | `set_timer` | `set_timer` | 759ms | ✅ PASS |
| 5 | `ghi chú mua sữa` | `note_taking` | `note_taking` | 805ms | ✅ PASS |
| 6 | `thời tiết Hà Nội` | `weather_query` | `weather_query` | 870ms | ✅ PASS |
| 7 | `bật nhạc` | `media_control` | `media_control` | 962ms | ✅ PASS |
| 8 | `chụp màn hình` | `screenshot` | `screenshot` | 1139ms | ✅ PASS |
| 9 | `nhắc tôi họp lúc 3 giờ` | `set_reminder` | `set_reminder` | 949ms | ✅ PASS |
| 10 | `mở cài đặt Windows` | `open_settings` | `open_settings` | 713ms | ✅ PASS |

> [!NOTE]
> **\*Intent #2 "tìm kiếm thời tiết hôm nay"**: LLM phân loại thành `weather_query` — đây là quyết định ngữ nghĩa đúng (từ "thời tiết" trong câu), không phải lỗi kỹ thuật. Label benchmark cần cập nhật từ `web_search` → `weather_query` cho intent này trong phiên benchmark kế tiếp.

---

## Summary

| Chỉ số | Giá trị |
|---|---|
| N (số lượng intents) | 10 |
| Passed | **9/10** |
| Pass rate | **90.0%** |
| Avg latency | **979ms** (real API call, network round-trip) |
| Model | `gemini-flash-lite-latest` |
| Free tier rate limit | 5 RPM — test chạy với 15s delay giữa mỗi request |
| **Verdict** | **`PASS runtime`** |

---

## Môi trường

- **OS**: Windows 11
- **Python**: 3.13
- **SDK**: `google-generativeai` (deprecated but functional)
- **Mock used**: `false` — real HTTP calls to `generativelanguage.googleapis.com`
- **Live credentials**: `GEMINI_API_KEY=AIzaSy...` (39 chars) in `.env`
- **Rate limiting**: Free tier 5 RPM for gemini-flash models

---

## Ghi chú cho lần đo tiếp theo

1. Tăng N ≥ 30 intents và cân bằng distribution các action labels
2. Cập nhật intent #2: "tìm kiếm thời tiết hôm nay" → label `weather_query` (hoặc thêm câu "tìm kiếm [non-weather topic]" riêng)
3. Xem xét upgrade lên paid tier để loại bỏ rate limit constraint
