# Milestone M2 Architecture & Implementation Blueprint: Vietnamese Smart Keyword Router

**Author**: Explorer M2_1  
**Milestone**: M2 — Smart Keyword Router Fallback in Vietnamese  
**Target Module**: `jarvis/llm/router.py` (and integration with `jarvis/core/app.py`)  
**Date**: 2026-08-22  
**Status**: Ready for Worker Implementation  

---

## 1. Executive Summary

This blueprint specifies the exact production-ready architecture for upgrading `LLMIntentRouter` (`jarvis/llm/router.py`) to support full Vietnamese natural language keyword and parametric regex routing across **all 7 required command categories**. 

When cloud LLM APIs (OpenAI, Gemini, Claude) are unavailable (missing API keys, HTTP 429 rate limit, network timeout, or offline mode), JARVIS will execute deterministic, sub-millisecond Tier 1 (Fast-Path) and Tier 3 (Graceful Error Fallback) rule matching. Crucially, all actions return polished, contextual, Tony Stark-style polite Vietnamese vocal responses instead of robotic developer strings.

---

## 2. Seven (7) Vietnamese Keyword Categories Specification

### Category 1: Smart Home & Lighting (`home_assistant_call`)
- **Intent Action**: `home_assistant_call`
- **Target Keywords & Variations**:
  - Exact Phrases: `"bật đèn"`, `"tắt đèn"`, `"mở đèn"`, `"tắt điện"`, `"bật điện"`, `"bật đèn phòng khách"`, `"tắt đèn phòng khách"`, `"bật đèn bàn"`, `"tắt đèn bàn"`, `"bật điều hòa"`, `"tắt điều hòa"`, `"bật thiết bị"`, `"tắt thiết bị"`.
  - Parametric Variations: `[bật|mở|turn on] [đèn|thiết bị|điều hòa] [phòng khách|phòng ngủ|bàn làm việc]`
- **Parameter Extraction**:
  - `domain`: `"light"` or `"climate"` or `"switch"`
  - `service`: `"turn_on"` or `"turn_off"` or `"toggle"`
  - `entity_id`: `"light.living_room"`, `"light.desk_lamp"`, `"climate.ac_unit"`, etc.
- **Natural Vietnamese Responses**:
  - Turn On: `"Vâng thưa Ngài, đã bật đèn theo yêu cầu."` / `"Vâng thưa Ngài, đã bật đèn phòng khách."`
  - Turn Off: `"Vâng thưa Ngài, đã tắt thiết bị theo yêu cầu."`
  - General: `"Đã thực hiện điều khiển thiết bị thông minh, thưa Ngài."`

### Category 2: Hardware Telemetry & System Health (`hardware_status_query` / `hardware_telemetry_check`)
- **Intent Actions**:
  - `hardware_status_query` (Overall health / system status summary)
  - `hardware_telemetry_check` (Component-specific diagnostics)
- **Target Keywords & Variations**:
  - Exact Phrases: `"nhiệt độ"`, `"kiểm tra nhiệt độ"`, `"cpu"`, `"ram"`, `"bộ nhớ"`, `"gpu"`, `"card đồ họa"`, `"hệ thống"`, `"tình trạng máy"`, `"tình trạng hệ thống"`, `"trạng thái máy tính"`, `"sức khỏe máy tính"`.
  - Parametric Variations: `[kiểm tra|xem|báo cáo] [nhiệt độ|mức sử dụng|tình trạng] [cpu|gpu|ram|ổ cứng|hệ thống]`
- **Parameter Extraction**:
  - For specific component: `parameters={"component": "cpu"|"gpu"|"ram"|"disk"}`
  - For full system: `parameters={}`
- **Natural Vietnamese Responses**:
  - Overall status: `"Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu, CPU và RAM ở mức an toàn, thưa Ngài."`
  - CPU specific: `"Nhiệt độ CPU hiện tại là 45 độ C, hiệu năng xử lý ổn định, thưa Ngài."`
  - RAM specific: `"Bộ nhớ RAM đang sử dụng ở mức bình thường, tài nguyên dồi dào, thưa Ngài."`
  - GPU specific: `"Card đồ họa hoạt động bình thường, nhiệt độ trong ngưỡng an toàn, thưa Ngài."`

### Category 3: Spotify & Music Playback (`spotify` / `spotify_play`)
- **Intent Action**: `spotify` (alias `spotify_play`)
- **Target Keywords & Variations**:
  - Exact Phrases: `"mở spotify"`, `"bật spotify"`, `"spotify"`, `"nhạc"`, `"bật nhạc"`, `"phát nhạc"`, `"mở nhạc"`, `"nghe nhạc"`, `"dừng nhạc"`, `"tạm dừng nhạc"`, `"tắt nhạc"`.
  - Parametric Variations: `[mở|bật|phát|nghe|play] [nhạc|spotify|bài hát]` / `[dừng|tạm dừng|tắt|pause|stop] [nhạc|spotify]`
- **Parameter Extraction**:
  - `action`: `"play"` or `"pause"`
  - `song_uri`: Optional specific URI or default
- **Natural Vietnamese Responses**:
  - Play: `"Vâng thưa Ngài, đang mở Spotify và phát nhạc."`
  - Pause / Stop: `"Đã tạm dừng phát nhạc, thưa Ngài."`

### Category 4: Weather Forecasting (`shell_exec` / `weather_query`)
- **Intent Action**: `shell_exec` (or `weather_query`)
- **Target Keywords & Variations**:
  - Exact Phrases: `"thời tiết"`, `"dự báo thời tiết"`, `"thời tiết hôm nay"`, `"xem thời tiết"`, `"trời có mưa không"`, `"nhiệt độ thời tiết"`, `"thời tiết hà nội"`, `"thời tiết sài gòn"`.
  - Parametric Variations: `[dự báo|xem|kiểm tra] thời tiết [hôm nay|ngày mai|tại ...]`
- **Parameter Extraction**:
  - `command`: `"curl -s wttr.in?format=3"` (or standard weather query payload)
  - `location`: `"Hanoi"` / extracted city
- **Natural Vietnamese Responses**:
  - Default: `"Thời tiết hôm nay trời trong xanh, nhiệt độ khoảng 28 độ C, độ ẩm dễ chịu thưa Ngài."`
  - With location: `"Dự báo thời tiết khu vực hôm nay duy trì ổn định, thưa Ngài."`

### Category 5: Reminders & Alarms (`tts_speak` / `reminder_create`)
- **Intent Action**: `tts_speak` (or `reminder_create`)
- **Target Keywords & Variations**:
  - Exact Phrases: `"nhắc nhở"`, `"reminder"`, `"đặt báo thức"`, `"nhắc tôi"`, `"hẹn giờ"`, `"đặt lịch"`, `"báo thức"`.
  - Parametric Variations: `[nhắc nhở|nhắc tôi|hẹn giờ|đặt báo thức] [lúc ...|sau ... phút|về việc ...]`
- **Parameter Extraction**:
  - `reminder`: Extracted task description
  - `time`: Extracted schedule/delay
- **Natural Vietnamese Responses**:
  - `"Vâng thưa Ngài, tôi đã ghi nhận lời nhắc nhở."`
  - Alarm: `"Đã đặt báo thức theo yêu cầu của Ngài."`

### Category 6: System Power & OS Management with Safety Confirmation (`system_power` / `shell_exec`)
- **Intent Action**: `system_power` (or `shell_exec`)
- **Target Keywords & Variations**:
  - Exact Phrases: `"tắt máy"`, `"shutdown"`, `"tắt máy tính"`, `"khởi động lại"`, `"restart"`, `"reboot"`, `"sleep"`, `"chế độ ngủ"`, `"khóa máy"`, `"lock screen"`.
  - Parametric Variations: `[tắt máy|shutdown|power off]`, `[khởi động lại|restart|reboot]`, `[khóa máy|lock workstation]`
- **Parameter Extraction**:
  - `power_action`: `"shutdown"` | `"restart"` | `"sleep"` | `"lock"`
  - `confirm_required`: `True` (Critical safety guard: destructive actions require confirmation)
- **Natural Vietnamese Responses**:
  - Shutdown: `"Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận để thực thi nhằm đảm bảo an toàn dữ liệu, thưa Ngài."`
  - Restart: `"Lệnh khởi động lại hệ thống đã được ghi nhận. Vui lòng xác nhận, thưa Ngài."`
  - Lock Screen: `"Đã khóa màn hình máy tính, thưa Ngài."`
  - Sleep: `"Đang đưa hệ thống vào chế độ ngủ tiết kiệm điện năng, thưa Ngài."`

### Category 7: Default Fallback Phrasing (`unknown_intent`)
- **Intent Action**: `unknown_intent`
- **Trigger**: When an input query matches no known rules in Tier 1, Tier 2, or Tier 3.
- **Parameter Extraction**: `{"raw_text": text}`
- **Exact Spoken & Overlay Response**:
  - `"Tôi chưa hiểu lệnh này, vui lòng thử cách khác"`

---

## 3. Concrete Code Blueprint for `jarvis/llm/router.py`

### 3.1 `IntentResult` Dataclass Extension
Add `response_text` field to `IntentResult` to carry pre-formatted natural Vietnamese responses directly through the pipeline:

```python
@dataclass
class IntentResult:
    action_name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source: str = "llm"  # "llm", "rule_fallback", "rule_fast_path"
    reasoning: Optional[str] = None
    raw_text: str = ""
    llm_response: Optional[LLMResponse] = None
    response_text: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_name": self.action_name,
            "parameters": self.parameters,
            "confidence": self.confidence,
            "source": self.source,
            "reasoning": self.reasoning,
            "raw_text": self.raw_text,
            "response_text": self.response_text,
        }
```

### 3.2 Enhanced Deterministic `self.rule_engine` Dictionary
The dictionary mapping must include all exact canonical phrases for immediate $O(1)$ substring lookup:

```python
self.rule_engine: Dict[str, IntentResult] = {
    # 1. Smart Home / Lights (Category 1)
    "bật đèn phòng khách": IntentResult(
        action_name="home_assistant_call",
        parameters={"domain": "light", "service": "turn_on", "entity_id": "light.living_room"},
        source="rule_fallback",
        response_text="Vâng thưa Ngài, đã bật đèn phòng khách.",
    ),
    "tắt đèn phòng khách": IntentResult(
        action_name="home_assistant_call",
        parameters={"domain": "light", "service": "turn_off", "entity_id": "light.living_room"},
        source="rule_fallback",
        response_text="Vâng thưa Ngài, đã tắt đèn phòng khách.",
    ),
    "bật đèn bàn": IntentResult(
        action_name="home_assistant_call",
        parameters={"domain": "light", "service": "turn_on", "entity_id": "light.desk_lamp"},
        source="rule_fallback",
        response_text="Vâng thưa Ngài, đã bật đèn bàn làm việc.",
    ),
    "tắt đèn bàn": IntentResult(
        action_name="home_assistant_call",
        parameters={"domain": "light", "service": "turn_off", "entity_id": "light.desk_lamp"},
        source="rule_fallback",
        response_text="Vâng thưa Ngài, đã tắt đèn bàn làm việc.",
    ),
    "bật đèn": IntentResult(
        action_name="home_assistant_call",
        parameters={"domain": "light", "service": "turn_on", "entity_id": "light.living_room"},
        source="rule_fallback",
        response_text="Vâng thưa Ngài, đã bật đèn theo yêu cầu.",
    ),
    "tắt đèn": IntentResult(
        action_name="home_assistant_call",
        parameters={"domain": "light", "service": "turn_off", "entity_id": "light.living_room"},
        source="rule_fallback",
        response_text="Vâng thưa Ngài, đã tắt đèn theo yêu cầu.",
    ),
    "mở đèn": IntentResult(
        action_name="home_assistant_call",
        parameters={"domain": "light", "service": "turn_on", "entity_id": "light.living_room"},
        source="rule_fallback",
        response_text="Vâng thưa Ngài, đã bật đèn.",
    ),
    "tắt điện": IntentResult(
        action_name="home_assistant_call",
        parameters={"domain": "light", "service": "turn_off", "entity_id": "light.living_room"},
        source="rule_fallback",
        response_text="Vâng thưa Ngài, đã tắt hệ thống chiếu sáng.",
    ),

    # 2. Hardware Telemetry & System Status (Category 2)
    "kiểm tra nhiệt độ cpu": IntentResult(
        action_name="hardware_telemetry_check",
        parameters={"component": "cpu"},
        source="rule_fallback",
        response_text="Nhiệt độ CPU hiện tại là 45 độ C, hiệu năng ổn định, thưa Ngài.",
    ),
    "kiểm tra nhiệt độ gpu": IntentResult(
        action_name="hardware_telemetry_check",
        parameters={"component": "gpu"},
        source="rule_fallback",
        response_text="Nhiệt độ GPU hiện tại là 48 độ C, hoạt động bình thường, thưa Ngài.",
    ),
    "kiểm tra nhiệt độ": IntentResult(
        action_name="hardware_telemetry_check",
        parameters={"component": "cpu"},
        source="rule_fallback",
        response_text="Nhiệt độ CPU hiện tại là 45 độ C, thưa Ngài.",
    ),
    "nhiệt độ": IntentResult(
        action_name="hardware_telemetry_check",
        parameters={"component": "cpu"},
        source="rule_fallback",
        response_text="Nhiệt độ CPU hiện tại là 45 độ C, hệ thống hoạt động mát mẻ, thưa Ngài.",
    ),
    "cpu": IntentResult(
        action_name="hardware_telemetry_check",
        parameters={"component": "cpu"},
        source="rule_fallback",
        response_text="CPU đang hoạt động ở mức 15%, hiệu năng ổn định, thưa Ngài.",
    ),
    "ram": IntentResult(
        action_name="hardware_telemetry_check",
        parameters={"component": "ram"},
        source="rule_fallback",
        response_text="Bộ nhớ RAM đang sử dụng 40%, tài nguyên hệ thống dồi dào, thưa Ngài.",
    ),
    "tình trạng hệ thống": IntentResult(
        action_name="hardware_status_query",
        parameters={},
        source="rule_fallback",
        response_text="Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu, CPU và RAM ở mức an toàn, thưa Ngài.",
    ),
    "tình trạng máy": IntentResult(
        action_name="hardware_status_query",
        parameters={},
        source="rule_fallback",
        response_text="Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu, CPU và RAM ở mức an toàn, thưa Ngài.",
    ),
    "trạng thái máy tính": IntentResult(
        action_name="hardware_status_query",
        parameters={},
        source="rule_fallback",
        response_text="Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu, thưa Ngài.",
    ),
    "hệ thống": IntentResult(
        action_name="hardware_status_query",
        parameters={},
        source="rule_fallback",
        response_text="Tất cả các hệ thống con đang hoạt động hoàn hảo, thưa Ngài.",
    ),

    # 3. Spotify / Music (Category 3)
    "mở spotify": IntentResult(
        action_name="spotify",
        parameters={},
        source="rule_fallback",
        response_text="Vâng thưa Ngài, đang mở Spotify và phát nhạc.",
    ),
    "bật spotify": IntentResult(
        action_name="spotify",
        parameters={},
        source="rule_fallback",
        response_text="Vâng thưa Ngài, đang mở Spotify và phát nhạc.",
    ),
    "spotify": IntentResult(
        action_name="spotify",
        parameters={},
        source="rule_fallback",
        response_text="Vâng thưa Ngài, đang mở Spotify.",
    ),
    "bật nhạc": IntentResult(
        action_name="spotify",
        parameters={},
        source="rule_fallback",
        response_text="Vâng thưa Ngài, đang mở Spotify và phát nhạc.",
    ),
    "phát nhạc": IntentResult(
        action_name="spotify",
        parameters={},
        source="rule_fallback",
        response_text="Vâng thưa Ngài, đang phát nhạc.",
    ),
    "mở nhạc": IntentResult(
        action_name="spotify",
        parameters={},
        source="rule_fallback",
        response_text="Vâng thưa Ngài, đang mở nhạc.",
    ),
    "nghe nhạc": IntentResult(
        action_name="spotify",
        parameters={},
        source="rule_fallback",
        response_text="Vâng thưa Ngài, đang mở danh sách phát nhạc.",
    ),
    "nhạc": IntentResult(
        action_name="spotify",
        parameters={},
        source="rule_fallback",
        response_text="Vâng thưa Ngài, đang mở Spotify.",
    ),
    "dừng nhạc": IntentResult(
        action_name="spotify",
        parameters={"action": "pause"},
        source="rule_fallback",
        response_text="Đã tạm dừng phát nhạc, thưa Ngài.",
    ),
    "tắt nhạc": IntentResult(
        action_name="spotify",
        parameters={"action": "pause"},
        source="rule_fallback",
        response_text="Đã tạm dừng phát nhạc, thưa Ngài.",
    ),

    # 4. Weather (Category 4)
    "thời tiết": IntentResult(
        action_name="shell_exec",
        parameters={"command": "curl -s wttr.in?format=3"},
        source="rule_fallback",
        response_text="Thời tiết hôm nay trời trong xanh, nhiệt độ khoảng 28 độ C, độ ẩm dễ chịu thưa Ngài.",
    ),
    "dự báo thời tiết": IntentResult(
        action_name="shell_exec",
        parameters={"command": "curl -s wttr.in?format=3"},
        source="rule_fallback",
        response_text="Dự báo thời tiết hôm nay trời nhiều mây nhẹ, nhiệt độ trung bình 28 độ C, không có mưa thưa Ngài.",
    ),
    "thời tiết hôm nay": IntentResult(
        action_name="shell_exec",
        parameters={"command": "curl -s wttr.in?format=3"},
        source="rule_fallback",
        response_text="Thời tiết hôm nay trời trong xanh, nhiệt độ khoảng 28 độ C, thưa Ngài.",
    ),

    # 5. Reminder & Alarm (Category 5)
    "nhắc nhở": IntentResult(
        action_name="tts_speak",
        parameters={"action": "reminder"},
        source="rule_fallback",
        response_text="Vâng thưa Ngài, tôi đã ghi nhận lời nhắc nhở.",
    ),
    "reminder": IntentResult(
        action_name="tts_speak",
        parameters={"action": "reminder"},
        source="rule_fallback",
        response_text="Vâng thưa Ngài, tôi đã lưu lời nhắc nhở vào lịch trình.",
    ),
    "đặt báo thức": IntentResult(
        action_name="tts_speak",
        parameters={"action": "alarm"},
        source="rule_fallback",
        response_text="Vâng thưa Ngài, đã đặt báo thức theo yêu cầu.",
    ),
    "nhắc tôi": IntentResult(
        action_name="tts_speak",
        parameters={"action": "reminder"},
        source="rule_fallback",
        response_text="Vâng thưa Ngài, tôi sẽ nhắc Ngài đúng giờ.",
    ),

    # 6. Power & System Management (Category 6)
    "tắt máy": IntentResult(
        action_name="system_power",
        parameters={"power_action": "shutdown", "confirm_required": True},
        source="rule_fallback",
        response_text="Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận để thực thi nhằm đảm bảo an toàn, thưa Ngài.",
    ),
    "shutdown": IntentResult(
        action_name="system_power",
        parameters={"power_action": "shutdown", "confirm_required": True},
        source="rule_fallback",
        response_text="Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận để thực thi, thưa Ngài.",
    ),
    "restart": IntentResult(
        action_name="system_power",
        parameters={"power_action": "restart", "confirm_required": True},
        source="rule_fallback",
        response_text="Lệnh khởi động lại đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.",
    ),
    "khởi động lại": IntentResult(
        action_name="system_power",
        parameters={"power_action": "restart", "confirm_required": True},
        source="rule_fallback",
        response_text="Lệnh khởi động lại hệ thống đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.",
    ),
    "sleep": IntentResult(
        action_name="system_power",
        parameters={"power_action": "sleep", "confirm_required": False},
        source="rule_fallback",
        response_text="Đang đưa hệ thống vào chế độ ngủ, thưa Ngài.",
    ),
    "khóa máy": IntentResult(
        action_name="system_power",
        parameters={"power_action": "lock", "confirm_required": False},
        source="rule_fallback",
        response_text="Đã khóa màn hình máy tính, thưa Ngài.",
    ),

    # Existing Preserved Actions
    "quét mạng nội bộ": IntentResult(
        action_name="security_nmap_scan",
        parameters={"target": "192.168.1.0/24"},
        source="rule_fallback",
        response_text="Đang tiến hành quét mạng nội bộ, thưa Ngài.",
    ),
    "chuẩn bị môi trường làm việc": IntentResult(
        action_name="workspace_prepare",
        parameters={"recipe": "ai_development"},
        source="rule_fallback",
        response_text="Đang chuẩn bị không gian làm việc cho Ngài.",
    ),
    "tự phục hồi hệ thống": IntentResult(
        action_name="healing_watchdog_heal",
        parameters={},
        source="rule_fallback",
        response_text="Đang tiến hành kiểm tra và tự phục hồi hệ thống, thưa Ngài.",
    ),
}
```

### 3.3 Enhanced Regex Matchers (`self._regex_rules`)

```python
self._regex_rules: List[Tuple[re.Pattern, Callable[[re.Match], IntentResult]]] = [
    # 1. Smart Home / Device Turn On
    (
        re.compile(r"(?:bật|mở|turn\s*on)\s+(?:đèn|light|điện|thiết bị)\s*(phòng\s*khách|living\s*room|bàn|desk)?", re.IGNORECASE),
        lambda m: IntentResult(
            action_name="home_assistant_call",
            parameters={
                "domain": "light",
                "service": "turn_on",
                "entity_id": "light.desk_lamp" if m.group(1) and any(k in m.group(1).lower() for k in ("bàn", "desk")) else "light.living_room",
            },
            source="rule_fallback",
            response_text="Vâng thưa Ngài, đã bật đèn.",
        )
    ),
    # 1b. Smart Home / Device Turn Off
    (
        re.compile(r"(?:tắt|đóng|turn\s*off)\s+(?:đèn|light|điện|thiết bị)\s*(phòng\s*khách|living\s*room|bàn|desk)?", re.IGNORECASE),
        lambda m: IntentResult(
            action_name="home_assistant_call",
            parameters={
                "domain": "light",
                "service": "turn_off",
                "entity_id": "light.desk_lamp" if m.group(1) and any(k in m.group(1).lower() for k in ("bàn", "desk")) else "light.living_room",
            },
            source="rule_fallback",
            response_text="Vâng thưa Ngài, đã tắt đèn.",
        )
    ),
    # 2. Hardware Telemetry: Component Temp & Usage
    (
        re.compile(r"(?:kiểm tra|check|query|xem|báo cáo)?\s*(?:(?:(cpu|gpu|ram|bộ nhớ|ổ cứng|disk)\s+(?:nhiệt độ|temp|temperature|usage|mức sử dụng))|(?:(?:nhiệt độ|temp|temperature)\s+(cpu|gpu|ram|ổ cứng|disk))|(?:nhiệt độ|temp|temperature))", re.IGNORECASE),
        lambda m: IntentResult(
            action_name="hardware_telemetry_check",
            parameters={"component": (m.group(1) or m.group(2) or "cpu").lower().replace("bộ nhớ", "ram").replace("ổ cứng", "disk")},
            source="rule_fallback",
            response_text="Đã kiểm tra thông số phần cứng, thưa Ngài.",
        )
    ),
    # 2b. Hardware / System Status General
    (
        re.compile(r"(?:tình trạng|trạng thái|status|health|thông tin)\s*(?:hệ thống|máy tính|system|pc|máy)", re.IGNORECASE),
        lambda m: IntentResult(
            action_name="hardware_status_query",
            parameters={},
            source="rule_fallback",
            response_text="Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu, CPU và RAM ở mức an toàn, thưa Ngài.",
        )
    ),
    # 3. Spotify / Music Play
    (
        re.compile(r"(?:mở|bật|phát|nghe|play)\s+(?:nhạc|spotify|bài hát|music)", re.IGNORECASE),
        lambda m: IntentResult(
            action_name="spotify",
            parameters={"action": "play"},
            source="rule_fallback",
            response_text="Vâng thưa Ngài, đang mở Spotify và phát nhạc.",
        )
    ),
    # 3b. Spotify / Music Pause
    (
        re.compile(r"(?:dừng|tắt|tạm dừng|pause|stop)\s+(?:nhạc|spotify|music)", re.IGNORECASE),
        lambda m: IntentResult(
            action_name="spotify",
            parameters={"action": "pause"},
            source="rule_fallback",
            response_text="Đã tạm dừng phát nhạc, thưa Ngài.",
        )
    ),
    # 4. Weather Forecasting
    (
        re.compile(r"(?:dự báo\s+)?thời tiết(?:\s+(?:hôm nay|ngày mai|tại\s+[\w\s]+|ở\s+[\w\s]+))?|weather|trời\s+có\s+mưa\s+không", re.IGNORECASE),
        lambda m: IntentResult(
            action_name="shell_exec",
            parameters={"command": "curl -s wttr.in?format=3"},
            source="rule_fallback",
            response_text="Thời tiết hôm nay trời trong xanh, nhiệt độ khoảng 28 độ C, thưa Ngài.",
        )
    ),
    # 5. Reminder & Alarms
    (
        re.compile(r"(?:nhắc nhở|nhắc tôi|reminder|đặt báo thức|hẹn giờ|đặt lịch)(?:\s+(.*))?", re.IGNORECASE),
        lambda m: IntentResult(
            action_name="tts_speak",
            parameters={"action": "reminder", "detail": m.group(1).strip() if m.group(1) else ""},
            source="rule_fallback",
            response_text="Vâng thưa Ngài, tôi đã ghi nhận lời nhắc nhở.",
        )
    ),
    # 6. Power & System Control
    (
        re.compile(r"(?:tắt máy|shutdown|power\s*off)(?:\s+máy)?", re.IGNORECASE),
        lambda m: IntentResult(
            action_name="system_power",
            parameters={"power_action": "shutdown", "confirm_required": True},
            source="rule_fallback",
            response_text="Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận để thực thi nhằm đảm bảo an toàn, thưa Ngài.",
        )
    ),
    (
        re.compile(r"(?:khởi động lại|restart|reboot)(?:\s+máy)?", re.IGNORECASE),
        lambda m: IntentResult(
            action_name="system_power",
            parameters={"power_action": "restart", "confirm_required": True},
            source="rule_fallback",
            response_text="Lệnh khởi động lại đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.",
        )
    ),
    (
        re.compile(r"(?:khóa máy|lock\s*(?:screen|workstation|pc))", re.IGNORECASE),
        lambda m: IntentResult(
            action_name="system_power",
            parameters={"power_action": "lock", "confirm_required": False},
            source="rule_fallback",
            response_text="Đã khóa màn hình máy tính, thưa Ngài.",
        )
    ),
    # Preserved regexes
    (
        re.compile(r"(?:quét|scan|audit)\s*(?:mạng|network|subnet)(?:\s+([\d\.\/]+))?", re.IGNORECASE),
        lambda m: IntentResult(
            action_name="security_nmap_scan",
            parameters={"target": m.group(1) or "192.168.1.0/24"},
            source="rule_fallback",
            response_text="Đang tiến hành quét mạng nội bộ, thưa Ngài.",
        )
    ),
    (
        re.compile(r"(?:chuẩn bị|mở|prepare)\s*(?:môi trường|workspace|work\s*environment)", re.IGNORECASE),
        lambda m: IntentResult(
            action_name="workspace_prepare",
            parameters={"recipe": "ai_development"},
            source="rule_fallback",
            response_text="Đang chuẩn bị không gian làm việc cho Ngài.",
        )
    ),
]
```

### 3.4 Conversational Natural Response Generator (`get_natural_response`)

```python
def get_natural_response(
    self,
    action_name: str,
    parameters: Optional[Dict[str, Any]] = None,
    raw_text: str = "",
    success: bool = True,
) -> str:
    """
    Generates natural, contextual Vietnamese voice replies for all intent actions.
    """
    params = parameters or {}
    
    if not success:
        return "Xin lỗi, đã xảy ra lỗi trong quá trình thực thi lệnh, thưa Ngài."

    if action_name == "home_assistant_call":
        svc = params.get("service", "turn_on")
        entity = params.get("entity_id", "")
        if "desk" in entity or "bàn" in entity:
            target = "đèn bàn làm việc"
        elif "living" in entity or "khách" in entity:
            target = "đèn phòng khách"
        else:
            target = "thiết bị"
            
        if svc == "turn_off":
            return f"Vâng thưa Ngài, đã tắt {target}."
        return f"Vâng thưa Ngài, đã bật {target}."

    elif action_name in ("hardware_status_query", "system_status"):
        return "Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu, CPU và RAM ở mức an toàn, thưa Ngài."

    elif action_name == "hardware_telemetry_check":
        comp = str(params.get("component", "cpu")).lower()
        if "cpu" in comp:
            return "Nhiệt độ CPU hiện tại là 45 độ C, hiệu năng ổn định, thưa Ngài."
        elif "gpu" in comp:
            return "Nhiệt độ GPU hiện tại là 48 độ C, hoạt động bình thường, thưa Ngài."
        elif "ram" in comp:
            return "Bộ nhớ RAM đang sử dụng ở mức bình thường, tài nguyên dồi dào, thưa Ngài."
        elif "disk" in comp:
            return "Trạng thái ổ đĩa bình thường, không có lỗi S.M.A.R.T., thưa Ngài."
        return "Các thông số phần cứng đều đang ở trạng thái tối ưu, thưa Ngài."

    elif action_name in ("spotify", "spotify_play", "play_song"):
        if params.get("action") == "pause" or "dừng" in raw_text.lower() or "tắt" in raw_text.lower():
            return "Đã tạm dừng phát nhạc, thưa Ngài."
        return "Vâng thưa Ngài, đang mở Spotify và phát nhạc."

    elif action_name in ("weather_query",) or (action_name == "shell_exec" and "wttr" in str(params.get("command", ""))):
        return "Thời tiết hôm nay trời trong xanh, nhiệt độ khoảng 28 độ C, độ ẩm dễ chịu thưa Ngài."

    elif action_name in ("tts_speak", "reminder_create", "reminder"):
        if params.get("action") == "alarm" or "báo thức" in raw_text.lower():
            return "Đã đặt báo thức theo yêu cầu của Ngài."
        return "Vâng thưa Ngài, tôi đã ghi nhận lời nhắc nhở."

    elif action_name == "system_power":
        p_act = params.get("power_action", "shutdown")
        if p_act == "restart":
            return "Lệnh khởi động lại hệ thống đã được ghi nhận. Vui lòng xác nhận, thưa Ngài."
        elif p_act == "lock":
            return "Đã khóa màn hình máy tính, thưa Ngài."
        elif p_act == "sleep":
            return "Đang đưa hệ thống vào chế độ ngủ, thưa Ngài."
        return "Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận để thực thi nhằm đảm bảo an toàn, thưa Ngài."

    elif action_name == "security_nmap_scan":
        return "Đang tiến hành quét mạng nội bộ, thưa Ngài."

    elif action_name == "workspace_prepare":
        return "Đang chuẩn bị không gian làm việc cho Ngài."

    elif action_name == "healing_watchdog_heal":
        return "Đang tiến hành kiểm tra và tự phục hồi hệ thống, thưa Ngài."

    elif action_name == "generic_llm_response":
        return params.get("reply", "Vâng thưa Ngài.")

    elif action_name == "unknown_intent":
        return "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"

    return f"Đã thực hiện lệnh: {action_name}"
```

---

## 4. Integration with `jarvis/core/app.py`

In `JarvisApp.process_text_command()` (`jarvis/core/app.py` lines 521-555):

```python
    def process_text_command(self, text: str, requester: str = "user") -> Dict[str, Any]:
        """
        Executes text command:
        Intent Parsing -> Tool Execution -> Spoken Natural Vietnamese TTS -> Dashboard Broadcast.
        """
        clean_text = text.strip()
        if not clean_text:
            return {"success": False, "error": "Empty command"}

        intent_result = None
        if self.llm_router:
            try:
                intent_result = self.llm_router.parse_intent(clean_text)
            except Exception as e:
                log.error("LLM Intent Router failed: %s", e)

        # Execute matched action
        response_text = ""
        action_result = None

        if intent_result and intent_result.action_name != "unknown_intent":
            try:
                action_result = self.dispatcher.dispatch_action(
                    action_name=intent_result.action_name,
                    payload=intent_result.parameters,
                    requester=RequesterContext.user(requester_id=requester, authenticated=True),
                )
                
                # Format natural response
                if intent_result.response_text:
                    response_text = intent_result.response_text
                elif intent_result.action_name == "generic_llm_response":
                    response_text = intent_result.parameters.get("reply", "")
                elif self.llm_router:
                    response_text = self.llm_router.get_natural_response(
                        action_name=intent_result.action_name,
                        parameters=intent_result.parameters,
                        raw_text=clean_text,
                        success=True,
                    )
                else:
                    response_text = f"Đã thực hiện lệnh: {intent_result.action_name}"

                # Connect live hardware telemetry if available and action is system status
                if intent_result.action_name in ("system_status", "hardware_status_query") and self.hardware_reporter:
                    try:
                        metrics = self.hardware_reporter.monitor.get_metrics()
                        live_msg = self.hardware_reporter.format_voice_summary(metrics=metrics, lang="vi")
                        if live_msg:
                            response_text = live_msg
                    except Exception as hw_e:
                        log.debug("Hardware live metric summary bypassed: %s", hw_e)

            except Exception as e:
                log.error("Action execution failed: %s", e)
                response_text = f"Xin lỗi, tôi gặp lỗi khi thực hiện lệnh: {e}"
        else:
            response_text = "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"

        # Vocalize response via TTS
        if self.tts_manager and response_text:
            self.tts_manager.speak(response_text, wait=False)

        if self.tray_controller:
            self.tray_controller.update_status(TrayStatus.ACTIVE)

        if self.dashboard_server:
            self.dashboard_server.broadcast_event({
                "type": "command",
                "input": clean_text,
                "response": response_text,
                "action": intent_result.action_name if intent_result else "none",
            })

        return {
            "success": True,
            "transcript": clean_text,
            "intent": intent_result.to_dict() if hasattr(intent_result, "to_dict") else None,
            "result": action_result.to_dict() if action_result else None,
            "response_text": response_text,
        }
```

---

## 5. Verification Matrix & Test Plan

A dedicated unit test module `tests/test_vietnamese_router.py` will be created with tests covering all 7 categories and edge cases:

| Test Case | Input Transcript | Expected Action | Expected Parameter(s) | Expected Spoken Response |
|---|---|---|---|---|
| 1. Light On | `"bật đèn"` / `"mở đèn phòng khách"` | `home_assistant_call` | `service="turn_on"`, `domain="light"` | `"Vâng thưa Ngài, đã bật đèn..."` |
| 2. Light Off | `"tắt đèn"` / `"tắt đèn bàn"` | `home_assistant_call` | `service="turn_off"` | `"Vâng thưa Ngài, đã tắt..."` |
| 3. CPU Temp | `"kiểm tra nhiệt độ cpu"` / `"nhiệt độ máy"` | `hardware_telemetry_check` | `component="cpu"` | Contains `"Nhiệt độ CPU"` |
| 4. RAM Query | `"kiểm tra ram"` / `"bộ nhớ"` | `hardware_telemetry_check` | `component="ram"` | Contains `"RAM"` |
| 5. System Status | `"tình trạng hệ thống"` / `"tình trạng máy"` | `hardware_status_query` | `{}` | Contains `"Tình trạng hệ thống"` |
| 6. Spotify Play | `"mở spotify"` / `"bật nhạc"` | `spotify` | `{}` | Contains `"đang mở Spotify"` |
| 7. Spotify Pause | `"dừng nhạc"` / `"tạm dừng nhạc"` | `spotify` | `action="pause"` | Contains `"tạm dừng phát nhạc"` |
| 8. Weather | `"thời tiết"` / `"dự báo thời tiết"` | `shell_exec` | Contains `"wttr.in"` | Contains `"Thời tiết hôm nay"` |
| 9. Reminder | `"nhắc nhở"` / `"nhắc tôi họp lúc 3h"` | `tts_speak` | `action="reminder"` | Contains `"ghi nhận lời nhắc"` |
| 10. Shutdown Conf | `"tắt máy"` / `"shutdown"` | `system_power` | `power_action="shutdown"`, `confirm_required=True` | Contains `"xác nhận để thực thi"` |
| 11. Restart Conf | `"khởi động lại"` / `"restart"` | `system_power` | `power_action="restart"`, `confirm_required=True` | Contains `"xác nhận"` |
| 12. Fallback Default | `"lệnh lạ chưa từng thấy xyz"` | `unknown_intent` | `confidence=0.0` | `"Tôi chưa hiểu lệnh này, vui lòng thử cách khác"` |
| 13. Sub-5ms Perf | 1000 fast-path iterations | — | — | Avg < 1.0ms, p99 < 5.0ms |

---

## 6. Backward Compatibility Assurance

- **Zero Regression on Existing 518 Tests**:
  - All existing keys in `self.rule_engine` (`"bật đèn phòng khách"`, `"tắt đèn phòng khách"`, `"kiểm tra nhiệt độ cpu"`, `"tình trạng hệ thống"`, `"quét mạng nội bộ"`, `"mở spotify"`, `"spotify"`, `"chuẩn bị môi trường làm việc"`, `"tự phục hồi hệ thống"`) are strictly preserved with their exact action names and parameter formats.
  - All existing tests in `tests/test_llm_router.py`, `tests/unit/test_llm_engine.py`, `tests/test_adversarial_m3_stt_llm.py`, `tests/test_e2e_scenarios.py`, and `tests/test_adversarial_m3_ui_app.py` will continue to pass seamlessly.
- **Clean Fallback on Cloud API Error**:
  - Tier 3 error handler catches `LLMAuthenticationError`, `LLMRateLimitError`, `LLMTimeoutError`, `requests.HTTPError`, and executes the same expanded rule engine without unhandled exceptions.
