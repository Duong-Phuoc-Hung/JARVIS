# Evidence — D-08 Discord Live Auth (PASS auth, PENDING roundtrip)

**Date**: 2026-09-20  
**Auditor**: Automated live test script (`scripts/test_comms_live.py`, `scripts/find_discord_channel.py`)  
**Integrity Standards**: AGENTS.md §2 Anti-Fabrication Principle

---

## Kết quả

| Bước | API Call | HTTP Status | Kết quả |
|---|---|---|---|
| 1 | `GET /users/@me` | `200 OK` | Bot: `bot1549735760809164881#6740` — token hợp lệ |
| 2 | `GET /users/@me/guilds` | `200 OK` | Bot đang trong **0 servers** |
| 3 | `POST /channels/{id}/messages` | **BLOCKED** | Không có `DISCORD_CHANNEL_ID` — bot chưa join server nào |

**Verdict**: `PASS engineering + fail-closed` — Token hợp lệ, bot xác thực thành công qua Discord API v10. Live message send **PENDING_GUILD_INVITATION** — cần invite bot vào ít nhất 1 server Discord, sau đó set `DISCORD_CHANNEL_ID`.

---

## Tại sao không gửi được

Discord bot phải được **invite vào server** trước khi có thể gửi tin. Link invite:
```
https://discord.com/api/oauth2/authorize?client_id=<BOT_CLIENT_ID>&permissions=2048&scope=bot
```

Sau khi invite → copy Channel ID (chuột phải kênh text → Copy Channel ID trong Developer Mode) → thêm vào `.env`:
```
DISCORD_CHANNEL_ID=<id>
```

---

## Raw Evidence

```json
{
  "discord_auth": {
    "status": "PASS_AUTH_NO_GUILD",
    "bot": "bot1549735760809164881#6740",
    "http_auth": 200,
    "guilds_count": 0,
    "timestamp": "2026-09-20 23:05:13"
  }
}
```

---

## Môi trường

- **OS**: Windows 11  
- **API**: Discord REST API v10 (`discord.com/api/v10`)
- **Token length**: 72 chars (valid Discord bot token format)
- **Mock used**: `false` — real HTTP call to Discord API
- **Guild joined**: `0` (bot not added to any server)
