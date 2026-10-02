# 10-workflow Windows acceptance matrix — 2026-09-23

## Scope and evidence rule

This matrix separates deterministic routing/dispatcher evidence from real Windows
process/window evidence. The command probe below used the production
`LLMIntentRouter` with `llm_client=None` (rule fallback), so it proves intent
mapping only. It does **not** prove that a microphone, browser, media account or
device performed the action. A row is `PASS engineering` unless a real process,
window or URL is observed.

## Deterministic routing probe

Probe command: `LLMIntentRouter(llm_client=None).parse_intent(command)`.

| # | User command | Intent/action | Parameters observed | Verdict |
|---:|---|---|---|---|
| 1 | `mở cài đặt` | `app_open` | `app_name=Settings`, `app=ms-settings:` | PASS engineering |
| 2 | `mở chrome` | `app_open` | `name=chrome`, `installed_only=True` | PASS engineering |
| 3 | `tìm kiếm thời tiết Hà Nội` | `shell_exec` | `topic=weather`, `location=Hà Nội` | PASS engineering |
| 4 | `mở spotify và phát nhạc` | `spotify` | `query=''` | PASS engineering; playback account not verified |
| 5 | `tăng âm lượng 10` | `system_volume` | `delta=10` | PASS engineering; hardware not verified |
| 6 | `thời tiết hôm nay` | `shell_exec` | `topic=weather`, `location=current` | PASS engineering |
| 7 | `hẹn giờ 5 phút` | `reminder` | `action=timer` | PASS engineering |
| 8 | `nhắc tôi uống nước lúc 9 giờ` | `reminder` | `message=uống nước`, `time_str=9 giờ` | PASS engineering |
| 9 | `ghi chú mua sữa` | `skill_note_taker` | `action=add`, `content=mua sữa` | PASS engineering |
| 10 | `chụp màn hình` | `screen_capture` | `{}` | PASS engineering; capture backend not verified here |

Routing score: **10/10 (100%)**. This is not the Beta runtime score.

## Real Windows evidence available on this host

The installed-app probe in `docs/eval/app_catalog_verified_20260922.md` recorded
8/8 checks passed on 2026-09-22: Calculator and Notepad launch/window identity,
repeat rate limiting, missing-app failure, negation/compound guards and a
minimized Calculator reuse check. That evidence is valid for those two apps on
that host only; it is not a 10-workflow or clean-machine result.

## Runtime gate status

| Gate | Current status | Reason |
|---|---|---|
| Real microphone/STT/wake/TTS | `PENDING runtime` | No live voice capture run was performed in this verification pass. |
| Spotify authenticated playback | `PENDING runtime` | No authenticated Spotify account/session evidence. |
| Volume and screenshot hardware | `PENDING runtime` | Routing and fail-closed tests pass; physical output not measured here. |
| Cross-machine installed-app discovery | `PENDING runtime` | Catalog is Windows-specific; only one host inventory is evidenced. |
| Installer/update/rollback on clean machine | `PENDING runtime` | Unit coverage exists, but no clean-machine install artifact was exercised. |

Therefore the 10-workflow product gate remains **NO-GO for release**, while the
engineering/routing gate is green and safety remains fail-closed.
