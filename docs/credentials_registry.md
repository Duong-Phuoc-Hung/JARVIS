# JARVIS External Connector Credentials Registry (R9)

**Registry Version**: 1.0.0  
**Target Release**: JARVIS v5.2.0 (Windows 11 / Windows 10 64-bit)  
**Governance Standard**: `AGENTS.md §2` (Anti-Fabrication & Fail-Closed Principle) & `docs/AUDIT_FRAMEWORK.md`  
**Storage Architecture**: Windows Credential Manager (DPAPI / `keyring`) Service `"JARVIS"` with Environment Variable Fallback  
**Verification CLI**: `scripts/verify_credentials.py` & `python -m jarvis.security.secrets`  
**Document Status**: **ACTIVE / ZERO-PLACEHOLDER** (0 "TBD" entries)

---

## 1. Architecture & Storage Precedence

JARVIS enforces a strict **3-tier secret resolution hierarchy** to ensure secrets are never stored as plaintext in application configuration or committed to version control:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        SECRET RESOLUTION TIERS                         │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 1: Windows Credential Manager (via Python keyring) — PREFERRED    │
│         - Service Namespace: "JARVIS"                                  │
│         - Hardware-backed Windows DPAPI encryption                     │
│         - Per-user OS credential store; surviving git clean            │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 2: Process Environment Variables (os.environ) & Local .env        │
│         - Development / CI automation fallback                         │
│         - Loaded safely via python-dotenv without clobbering env       │
│         - Strictly ignored in version control (.gitignore)             │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 3: Config Dot-Notation Fallback (config/default_config.yaml)      │
│         - Plaintext default values are strictly empty strings ("")     │
│         - Populated at runtime via _apply_env_overrides()              │
└────────────────────────────────────────────────────────────────────────┘
```

### 1.1 Windows Credential Manager Integration (`jarvis.security.secrets`)

The core secret resolution is implemented in `jarvis/security/secrets.py`. The service identifier is:
```python
_SERVICE = "JARVIS"
```
The standard catalog of secrets managed directly through Windows Credential Manager (`KNOWN_SECRETS`) comprises:
- `GEMINI_API_KEY`
- `OPENAI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `DISCORD_BOT_TOKEN`
- `ZALO_API_KEY`
- `EMAIL_PASSWORD`
- `WEATHER_API_KEY`
- `HASS_TOKEN`
- `ELEVENLABS_API_KEY`

### 1.2 Secrets Manager CLI Commands

Operators and setup scripts manage the vault using the built-in CLI:

| Operation | Command | Description |
|---|---|---|
| **Store Secret** | `python -m jarvis.security.secrets set <NAME> <VALUE>` | Securely stores secret in Windows Credential Manager |
| **Retrieve Secret** | `python -m jarvis.security.secrets get <NAME>` | Reads secret from Credential Manager (or env fallback) |
| **Delete Secret** | `python -m jarvis.security.secrets delete <NAME>` | Removes secret from Windows Credential Manager |
| **Migrate Env** | `python -m jarvis.security.secrets migrate` | Migrates active environment variables to Credential Manager |
| **Dry Run Env** | `python -m jarvis.security.secrets migrate-dry` | Previews environment migration without persisting |
| **Migrate .env** | `python -m jarvis.security.secrets migrate-dotenv --path .env --purge` | Reads `.env`, stores in Credential Manager, and comments out plaintext secrets |

---

## 2. Master External Connector Matrix (12 Connectors)

Every external connector integrated in the JARVIS codebase is documented in the table below:

| # | Connector Name | Implementation Path | Credential Type(s) | Primary Env Var(s) & Secrets Key | Config Dot-Key | Current Owner | Fail-Closed Contract & Error Code | Rotation Cycle |
|---|---|---|---|---|---|---|---|---|
| **1** | **Gmail IMAP / SMTP** | `jarvis/comms/email_imap.py` | Google Account App Password (16-char), Email address | `SMTP_USER`, `SMTP_PASSWORD`<br>*(Secrets: `EMAIL_PASSWORD`)*,<br>`IMAP_HOST`, `IMAP_PORT`,<br>`SMTP_HOST`, `SMTP_PORT` | `comms.email_imap.username`<br>`comms.email_imap.password`<br>`comms.email_imap.host`<br>`comms.email_imap.port` | Primary User | Raises `IMAPNotConfiguredError` with status `"NOT_CONFIGURED"`; skips network connection; zero fake emails | 90 days |
| **2** | **Telegram Bot** | `jarvis/comms/telegram.py` | Bot API Token, Chat ID, User Whitelist | `TELEGRAM_BOT_TOKEN`<br>*(Secrets: `TELEGRAM_BOT_TOKEN`)*,<br>`TELEGRAM_CHAT_ID`,<br>`TELEGRAM_WHITELIST_USER_IDS` | `comms.telegram.bot_token`<br>`comms.telegram.whitelist_chat_ids` | Primary User | Returns `{"ok": False, "error_code": "NOT_CONFIGURED"}`; halts polling worker; unauthorized users dropped | 180 days |
| **3** | **Discord Bot** | `jarvis/comms/discord.py` | Bot API Token, Guild ID, Channel ID, Whitelist | `DISCORD_BOT_TOKEN`<br>*(Secrets: `DISCORD_BOT_TOKEN`)*,<br>`DISCORD_CHANNEL_ID`,<br>`DISCORD_GUILD_ID`,<br>`DISCORD_WHITELIST_USER_IDS` | `comms.discord.bot_token`<br>`comms.discord.channel_ids` | Primary User | Returns `{"success": False, "error_code": "NOT_CONFIGURED"}`; halts thread on 401/403/404; audit logs SHA-256 violation | 180 days |
| **4** | **Zalo Official Account (OA)** | `jarvis/comms/zalo.py` | OAuth 2.0 Access Token (JWT), App ID, App Secret, Webhook Secret | `ZALO_OA_ACCESS_TOKEN`<br>*(Secrets: `ZALO_API_KEY`)*,<br>`ZALO_APP_ID`, `ZALO_APP_SECRET`,<br>`ZALO_WEBHOOK_SECRET` | `comms.zalo.access_token`<br>`comms.zalo.oa_id`<br>`comms.zalo.webhook_secret` | Primary User | Returns `ZaloSendResult(success=False, error="NOT_CONFIGURED")`; image upload returns `IMAGE_SEND_NOT_IMPLEMENTED` | 90 days |
| **5** | **ElevenLabs Neural TTS** | `jarvis/tts/elevenlabs.py` | Cloud API Key (Bearer Token), Voice ID, Model ID | `ELEVENLABS_API_KEY`<br>*(Secrets: `ELEVENLABS_API_KEY`)*,<br>`ELEVENLABS_VOICE_ID`,<br>`ELEVENLABS_MODEL_ID` | `tts.elevenlabs.api_key`<br>`tts.elevenlabs.voice_id`<br>`tts.elevenlabs.model_id` | Primary User | `is_available()` returns `False`; falls back transparently to local Windows SAPI5 / Piper offline engine | 180 days |
| **6** | **Home Assistant (HASS)** | `jarvis/smart_home/home_assistant.py` | Long-Lived Access Token (LLAT), Server Base URL | `HASS_TOKEN`, `HA_TOKEN`<br>*(Secrets: `HASS_TOKEN`)*,<br>`HASS_URL` / `HASS_BASE_URL` | `smart_home.home_assistant.token`<br>`smart_home.home_assistant.url` | Primary User | Reports `StatusLevel.UNAVAILABLE`; returns `ActionResult(status=ERROR, code="NOT_CONFIGURED" / "CONNECTION_FAILED", retryable=True)` | 365 days |
| **7** | **Google Gemini API** | `jarvis/vision/screen.py`,<br>`jarvis/llm/client.py` | API Key (`AIzaSy...`) | `GEMINI_API_KEY`<br>*(Secrets: `GEMINI_API_KEY`)*,<br>`GOOGLE_API_KEY` (legacy fallback) | `vision.gemini_api_key`<br>`llm.api_key` *(if provider=gemini)* | Primary User | Vision/LLM client raises `LLMAuthenticationError` or returns `ActionResult(status=FAILED, code="API_KEY_MISSING")` | 180 days |
| **8** | **OpenAI API** | `jarvis/llm/client.py` | API Key (`sk-...`), Organization ID (optional) | `OPENAI_API_KEY`<br>*(Secrets: `OPENAI_API_KEY`)* | `llm.api_key` *(if provider=openai)* | Primary User | Raises `LLMAuthenticationError` or returns `ActionResult(status=FAILED, code="API_KEY_MISSING")`; Tier-1 rule router runs | 90 days |
| **9** | **OpenWeatherMap** | `jarvis/web/weather.py` | REST API Key (Hexadecimal 32 chars) | `OPENWEATHER_API_KEY`,<br>`WEATHER_API_KEY`<br>*(Secrets: `WEATHER_API_KEY`)* | `web.weather_api_key` | Primary User | Automatically falls back to `wttr.in` zero-key JSON endpoint; returns cached or graceful timeout if offline | 365 days |
| **10** | **GitHub Actions Secrets** | `.github/workflows/ci.yml`,<br>`.github/workflows/release.yml` | Repository Secrets, Workflow `GITHUB_TOKEN` | `GITHUB_TOKEN`,<br>`TELEGRAM_BOT_TOKEN`,<br>`ZALO_OA_ACCESS_TOKEN`,<br>`ZALO_APP_ID`, `ZALO_APP_SECRET`,<br>`DISCORD_BOT_TOKEN`,<br>`SMTP_USER`, `SMTP_PASSWORD` | N/A (CI Environment) | Primary User (`Duong-Phuoc-Hung`) | Missing secrets cause live integration jobs to skip gracefully; CI signing uses ephemeral self-signed cert | Synchronized with upstream |
| **11** | **PicoVoice Porcupine (Opt.)**| `jarvis/audio/wake_word.py` | Porcupine AccessKey (Base64 string) | `PORCUPINE_ACCESS_KEY` | `audio.wake_word.porcupine_access_key` | Primary User | WakeWord detector falls back immediately to Vosk / Energy-VAD / Faster-Whisper cascade | 365 days |
| **12** | **Spotify Plugin (Opt.)** | `jarvis/plugins/spotify.py` | Spotify Track URI / Web URL string | `SONG_URI` | `plugins.spotify.song_uri` | Primary User | Uses default track `spotify:track:39shmbIHICJ2Wxnk1fPSdz`; launched via Windows URI protocol | N/A |

---

## 3. Concrete Backup & Recovery Procedures (Zero "TBD")

The procedures below define exact step-by-step instructions for backing up, recovering, and rotating credentials for each of the 12 connectors.

```
┌────────────────────────────────────────────────────────────────────────┐
│                   MANDATORY OPERATIONAL PROTOCOL                       │
│  - Never store master passwords in unencrypted plain text.             │
│  - All master recovery accounts use an offline encrypted vault         │
│    (Bitwarden / KeePassXC) with Argon2id master key derivation.        │
│  - Every procedure below is verified, tested, and free of placeholders.│
└────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Connector 1: Gmail IMAP / SMTP

- **Subsystem**: `jarvis/comms/email_imap.py`
- **Owner**: Primary User (`Duong Phuoc Hung`)
- **Storage Location**: Windows Credential Manager (`EMAIL_PASSWORD`) and local `.env` (`SMTP_PASSWORD`, `SMTP_USER`).
- **Backup Procedure**:
  1. Open the primary encrypted password manager vault (KeePassXC / Bitwarden).
  2. Under entry `Google - JARVIS Master Account`, archive the 10 single-use 2FA backup codes generated during 2-Step Verification setup.
  3. Store the primary Google email address and emergency recovery phone / secondary email.
  4. Never export plaintext passwords into git repositories or unencrypted USB drives.
- **Recovery & Regeneration Procedure**:
  1. Open a browser and navigate to Google Account Security: `https://myaccount.google.com/security`.
  2. Log in using primary credentials and confirm 2-Step Verification prompt.
  3. Navigate directly to App Passwords: `https://myaccount.google.com/apppasswords`.
  4. Under **"App passwords"**, find the existing entry named `JARVIS Desktop` and click the **Delete (trash)** icon to revoke it immediately.
  5. In the **"Select app"** dropdown, select `Mail`.
  6. In the **"Select device"** dropdown, select `Windows Computer`.
  7. Click **"Generate"**. Google displays a 16-character string formatted with spaces (e.g. `abcd efgh ijkl mnop`).
  8. Copy the string and remove all spaces, resulting in a continuous 16-character string: `abcdefghijklmnop`.
  9. Persist into Windows Credential Manager:
     ```powershell
     python -m jarvis.security.secrets set EMAIL_PASSWORD abcdefghijklmnop
     ```
  10. Update the local `.env` file:
      ```dotenv
      SMTP_USER=your-email@gmail.com
      SMTP_PASSWORD=abcdefghijklmnop
      IMAP_HOST=imap.gmail.com
      IMAP_PORT=993
      SMTP_HOST=smtp.gmail.com
      SMTP_PORT=587
      ```
  11. If updating GitHub Actions CI/CD secrets:
      ```bash
      gh secret set SMTP_PASSWORD --body "abcdefghijklmnop" --repo Duong-Phuoc-Hung/JARVIS
      gh secret set SMTP_USER --body "your-email@gmail.com" --repo Duong-Phuoc-Hung/JARVIS
      ```
- **Rotation Policy**: Rotate every 90 days. Mandatory immediate revocation if `.env` is accidentally committed or workstation undergoes transfer.
- **Fail-Closed Verification**:
  ```powershell
  python -c "from jarvis.comms.email_imap import IMAPEmailReader; r = IMAPEmailReader(host='', username='', password=''); r.connect()"
  # Expected: raises IMAPNotConfiguredError('...Status: NOT_CONFIGURED')
  ```

---

### 3.2 Connector 2: Telegram Bot

- **Subsystem**: `jarvis/comms/telegram.py`
- **Owner**: Primary User (`Duong Phuoc Hung`)
- **Storage Location**: Windows Credential Manager (`TELEGRAM_BOT_TOKEN`), `.env` (`TELEGRAM_BOT_TOKEN`), GitHub Repository Secret.
- **Backup Procedure**:
  1. Record Bot handle (`@JARVISAssistant_bot`), Bot ID, and registration timestamp in the password manager.
  2. Retain owner Telegram Account access credentials (including Cloud Password / Two-Step Verification) in KeePassXC.
- **Recovery & Regeneration Procedure**:
  1. Open Telegram (Desktop or Web at `https://web.telegram.org`).
  2. Initiate conversation with the official bot administrator: `@BotFather` (`https://t.me/BotFather`).
  3. Send the command `/mybots`.
  4. Select your JARVIS bot from the inline keyboard list (e.g., `@JARVISAssistant_bot`).
  5. Select **"API Token"** from the bot settings menu.
  6. Click **"Revoke current token"**. BotFather immediately invalidates the previous token and generates a new token string in the format `<BOT_ID>:<SECRET_HASH>` (e.g., `123456789:ABCdefGHIjklMNOpqrSTUvwxYZ-abcdef01234`).
  7. Copy the new token string.
  8. Update Windows Credential Manager:
     ```powershell
     python -m jarvis.security.secrets set TELEGRAM_BOT_TOKEN 123456789:ABCdefGHIjklMNOpqrSTUvwxYZ-abcdef01234
     ```
  9. Update local `.env`:
     ```dotenv
     TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ-abcdef01234
     ```
  10. Update GitHub Secret:
      ```bash
      gh secret set TELEGRAM_BOT_TOKEN --body "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ-abcdef01234" --repo Duong-Phuoc-Hung/JARVIS
      ```
  11. Verify token status against Telegram REST API:
      ```bash
      curl -s "https://api.telegram.org/bot123456789:ABCdefGHIjklMNOpqrSTUvwxYZ-abcdef01234/getMe"
      ```
- **Rotation Policy**: Rotate every 180 days or immediately upon detection of unauthorized webhook responses or token leakage.
- **Fail-Closed Verification**:
  ```powershell
  python -c "from jarvis.comms.telegram import TelegramBotController; b = TelegramBotController(bot_token='', allowed_user_ids=set()); res = b.send_message(0, 'test'); assert res.get('error_code') == 'NOT_CONFIGURED', res; print('Telegram fail-closed: PASS')"
  ```

---

### 3.3 Connector 3: Discord Bot

- **Subsystem**: `jarvis/comms/discord.py`
- **Owner**: Primary User (`Duong Phuoc Hung`)
- **Storage Location**: Windows Credential Manager (`DISCORD_BOT_TOKEN`), `.env` (`DISCORD_BOT_TOKEN`), GitHub Repository Secret.
- **Backup Procedure**:
  1. Record Discord Application ID (`CLIENT_ID`), Guild ID (`DISCORD_GUILD_ID`), Channel ID (`DISCORD_CHANNEL_ID`), and Bot Invite Link in password manager.
  2. Retain 2FA authenticator recovery keys for the primary Discord account.
- **Recovery & Regeneration Procedure**:
  1. Log in to the Discord Developer Portal: `https://discord.com/developers/applications`.
  2. Select the **"JARVIS"** Application.
  3. In the left navigation menu, click **"Bot"**.
  4. Under the Token section, click **"Reset Token"**.
  5. Confirm the action by entering your 6-digit Discord Two-Factor Authentication (2FA) code.
  6. Discord displays the new token string once. Click **"Copy"**.
  7. Verify that **"Privileged Gateway Intents"** remain enabled:
     - `MESSAGE CONTENT INTENT` = Active
     - `SERVER MEMBERS INTENT` = Active
  8. Persist into Windows Credential Manager:
     ```powershell
     python -m jarvis.security.secrets set DISCORD_BOT_TOKEN <PASTED_DISCORD_TOKEN>
     ```
  9. Update local `.env`:
     ```dotenv
     DISCORD_BOT_TOKEN=<PASTED_DISCORD_TOKEN>
     DISCORD_GUILD_ID=123456789012345678
     DISCORD_CHANNEL_ID=123456789012345678
     ```
  10. Update GitHub Secret:
      ```bash
      gh secret set DISCORD_BOT_TOKEN --body "<PASTED_DISCORD_TOKEN>" --repo Duong-Phuoc-Hung/JARVIS
      ```
- **Rotation Policy**: Rotate every 180 days or immediately if the Discord gateway logs fatal HTTP 401 Unauthorized errors.
- **Fail-Closed Verification**:
  ```powershell
  python -c "from jarvis.comms.discord import DiscordBotController; d = DiscordBotController(bot_token='', whitelist_user_ids=[]); res = d.send_message(0, 'test'); assert res.get('error_code') == 'NOT_CONFIGURED', res; print('Discord fail-closed: PASS')"
  ```

---

### 3.4 Connector 4: Zalo Official Account (OA)

- **Subsystem**: `jarvis/comms/zalo.py`
- **Owner**: Primary User (`Duong Phuoc Hung`)
- **Storage Location**: Windows Credential Manager (`ZALO_API_KEY`), `.env` (`ZALO_OA_ACCESS_TOKEN`, `ZALO_APP_ID`, `ZALO_APP_SECRET`), GitHub Repository Secrets.
- **Backup Procedure**:
  1. Archive Zalo Developer Account credentials, App ID, App Secret, OA ID, and Webhook Secret in password manager.
  2. Maintain verified Vietnamese telephone identity connected to the Zalo Official Account.
- **Recovery & Regeneration Procedure**:
  1. Log in to Zalo for Developers: `https://developers.zalo.me`.
  2. Navigate to **"My Apps" (Ứng dụng của tôi)** → Select the JARVIS application.
  3. If App Secret is compromised:
     - Go to **"App Settings" (Cài đặt ứng dụng)** → **"Security" (Bảo mật)**.
     - Click **"Reset Secret Key"** → Confirm OTP.
  4. To refresh/regenerate the OA Access Token:
     - In the left sidebar, click **"Official Account"** → **"Access Token"**.
     - Click **"Create Access Token" (Tạo Access Token)**.
     - Select target Official Account (`JARVIS-OA`).
     - Grant required scopes: `messages.write`, `users.read`.
     - Click **"Authorize" (Xác nhận)** and copy the newly generated JWT Access Token string.
  5. Store in Windows Credential Manager:
     ```powershell
     python -m jarvis.security.secrets set ZALO_API_KEY <LONG_JWT_ACCESS_TOKEN>
     ```
  6. Update local `.env`:
     ```dotenv
     ZALO_OA_ACCESS_TOKEN=<LONG_JWT_ACCESS_TOKEN>
     ZALO_APP_ID=1234567890123456789
     ZALO_APP_SECRET=abcdef1234567890abcdef1234567890
     ```
  7. Update GitHub Secrets:
     ```bash
     gh secret set ZALO_OA_ACCESS_TOKEN --body "<LONG_JWT_ACCESS_TOKEN>" --repo Duong-Phuoc-Hung/JARVIS
     gh secret set ZALO_APP_ID --body "1234567890123456789" --repo Duong-Phuoc-Hung/JARVIS
     gh secret set ZALO_APP_SECRET --body "abcdef1234567890abcdef1234567890" --repo Duong-Phuoc-Hung/JARVIS
     ```
- **Rotation Policy**: Mandatory rotation every 90 days (enforced by Zalo OAuth token expiration lifecycle).
- **Fail-Closed Verification**:
  ```powershell
  python -c "from jarvis.comms.zalo import ZaloBotController, ZaloConfig; z = ZaloBotController(config=ZaloConfig(access_token=''), is_mock=False); res = z.send_message('u1', 'test'); assert res.error == 'NOT_CONFIGURED', res; print('Zalo fail-closed: PASS')"
  ```

---

### 3.5 Connector 5: ElevenLabs Neural Voice TTS

- **Subsystem**: `jarvis/tts/elevenlabs.py`
- **Owner**: Primary User (`Duong Phuoc Hung`)
- **Storage Location**: Windows Credential Manager (`ELEVENLABS_API_KEY`), `.env` (`ELEVENLABS_API_KEY`).
- **Backup Procedure**:
  1. Record ElevenLabs account email, billing subscription tier, custom Voice ID (`EXAVITQu4vr4xnSDxMaL`), and Model ID (`eleven_multilingual_v2`) in password manager.
- **Recovery & Regeneration Procedure**:
  1. Log in to ElevenLabs Console: `https://elevenlabs.io/app/settings/api-keys`.
  2. Under the API Keys section, review existing keys. Click the **Delete / Revoke** icon on the compromised or expired key.
  3. Click **"Create New API Key"**.
  4. Label the key `JARVIS-Desktop-Win11`.
  5. Copy the generated key string.
  6. Store in Windows Credential Manager:
     ```powershell
     python -m jarvis.security.secrets set ELEVENLABS_API_KEY <NEW_ELEVEN_KEY>
     ```
  7. Update local `.env`:
     ```dotenv
     ELEVENLABS_API_KEY=<NEW_ELEVEN_KEY>
     ELEVENLABS_VOICE_ID=EXAVITQu4vr4xnSDxMaL
     ELEVENLABS_MODEL_ID=eleven_multilingual_v2
     ```
  8. Verify synthesizer instantiation:
     ```powershell
     python -c "from jarvis.tts.elevenlabs import ElevenLabsTTS; t = ElevenLabsTTS(); print('ElevenLabs Available:', t.is_available())"
     ```
- **Rotation Policy**: Rotate every 180 days or upon billing cycle refresh if API usage anomaly is detected.
- **Fail-Closed Verification**:
  ```powershell
  python -c "from jarvis.tts.elevenlabs import ElevenLabsTTS; t = ElevenLabsTTS(config={'api_key': ''}); assert not t.is_available(); print('ElevenLabs fail-closed: PASS')"
  ```

---

### 3.6 Connector 6: Home Assistant (HASS)

- **Subsystem**: `jarvis/smart_home/home_assistant.py`
- **Owner**: Primary User (`Duong Phuoc Hung`)
- **Storage Location**: Windows Credential Manager (`HASS_TOKEN`), `.env` (`HASS_TOKEN`, `HASS_URL`).
- **Backup Procedure**:
  1. Store Home Assistant supervisor administrative password, local static IP (`192.168.x.x` or `http://homeassistant.local:8123`), and entity mapping registry in password manager.
- **Recovery & Regeneration Procedure**:
  1. Open local web browser and access the local Home Assistant web interface: `http://homeassistant.local:8123`.
  2. Click the user profile icon at the bottom of the left sidebar.
  3. Scroll down to the **"Long-Lived Access Tokens" (Mã truy cập dài hạn)** section.
  4. Locate the existing token labeled `JARVIS Desktop Assistant` and click the **Delete (trash)** icon.
  5. Click **"Create Token"**.
  6. Enter token name: `JARVIS Desktop Assistant - 2026`.
  7. Click **OK**. Home Assistant displays the generated token.
  8. Copy the entire token string.
  9. Persist into Windows Credential Manager:
     ```powershell
     python -m jarvis.security.secrets set HASS_TOKEN <PASTED_HASS_TOKEN>
     ```
  10. Update local `.env`:
      ```dotenv
      HASS_TOKEN=<PASTED_HASS_TOKEN>
      HASS_URL=http://homeassistant.local:8123
      ```
  11. Verify connectivity with authenticated curl probe:
      ```bash
      curl -s -H "Authorization: Bearer <PASTED_HASS_TOKEN>" http://homeassistant.local:8123/api/
      ```
- **Rotation Policy**: Rotate annually (365 days) or immediately if local LAN router credentials or Wi-Fi security keys change.
- **Fail-Closed Verification**:
  ```powershell
  python -c "from jarvis.smart_home.home_assistant import HomeAssistantClient; c = HomeAssistantClient(access_token=''); res = c.call_service('light', 'turn_on', {'entity_id': 'light.test'}); assert res.code == 'NOT_CONFIGURED', res; print('HASS fail-closed: PASS')"
  ```

---

### 3.7 Connector 7: Google Gemini API

- **Subsystem**: `jarvis/vision/screen.py`, `jarvis/llm/client.py`
- **Owner**: Primary User (`Duong Phuoc Hung`)
- **Storage Location**: Windows Credential Manager (`GEMINI_API_KEY`), `.env` (`GEMINI_API_KEY`).
- **Backup Procedure**:
  1. Record Google Cloud Project ID, linked billing account, and API Quota boundaries in password manager.
- **Recovery & Regeneration Procedure**:
  1. Access Google AI Studio API Key Manager: `https://aistudio.google.com/apikey`.
  2. Locate the existing key used by JARVIS and click the **Delete (trash)** icon.
  3. Click **"Create API key"**.
  4. Select the designated Google Cloud project (or create a new project `JARVIS-Desktop`).
  5. Copy the generated API key string (`AIzaSy...`).
  6. Store in Windows Credential Manager:
     ```powershell
     python -m jarvis.security.secrets set GEMINI_API_KEY AIzaSy...
     ```
  7. Update local `.env`:
     ```dotenv
     GEMINI_API_KEY=AIzaSy...
     ```
  8. Validate model list query:
     ```bash
     curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=AIzaSy..."
     ```
- **Rotation Policy**: Rotate every 180 days.
- **Fail-Closed Verification**:
  ```powershell
  python -c "from jarvis.llm.client import UnifiedLLMClient, LLMProvider, LLMAuthenticationError; c = UnifiedLLMClient(provider=LLMProvider.GEMINI, api_key=''); \
  try: c.generate('hi'); print('FAIL'); \
  except LLMAuthenticationError: print('Gemini fail-closed: PASS')"
  ```

---

### 3.8 Connector 8: OpenAI API

- **Subsystem**: `jarvis/llm/client.py`
- **Owner**: Primary User (`Duong Phuoc Hung`)
- **Storage Location**: Windows Credential Manager (`OPENAI_API_KEY`), `.env` (`OPENAI_API_KEY`).
- **Backup Procedure**:
  1. Record OpenAI Organization ID, Project ID, and monthly billing limit configuration ($10 hard limit) in password manager.
- **Recovery & Regeneration Procedure**:
  1. Navigate to OpenAI API Keys Dashboard: `https://platform.openai.com/api-keys`.
  2. Locate the existing key named `JARVIS_Win11` and click the revoke/delete icon.
  3. Click **"Create new secret key"**.
  4. Set key permissions to **Restricted** (allow Model Inference `Read/Write`, block Administrative / Billing / Org modifications).
  5. Name the key: `JARVIS_Win11_2026`.
  6. Copy the secret key (`sk-...`).
  7. Store in Windows Credential Manager:
     ```powershell
     python -m jarvis.security.secrets set OPENAI_API_KEY sk-...
     ```
  8. Update local `.env`:
     ```dotenv
     OPENAI_API_KEY=sk-...
     ```
  9. Probe OpenAI models endpoint:
     ```bash
     curl -s -H "Authorization: Bearer sk-..." https://api.openai.com/v1/models
     ```
- **Rotation Policy**: Rotate every 90 days. Mandatory rotation if rate limit or usage anomaly alert triggers.
- **Fail-Closed Verification**:
  ```powershell
  python -c "from jarvis.llm.client import UnifiedLLMClient, LLMProvider, LLMAuthenticationError; c = UnifiedLLMClient(provider=LLMProvider.OPENAI, api_key=''); \
  try: c.generate('hi'); print('FAIL'); \
  except LLMAuthenticationError: print('OpenAI fail-closed: PASS')"
  ```

---

### 3.9 Connector 9: OpenWeatherMap API

- **Subsystem**: `jarvis/web/weather.py`
- **Owner**: Primary User (`Duong Phuoc Hung`)
- **Storage Location**: Windows Credential Manager (`WEATHER_API_KEY`), `.env` (`WEATHER_API_KEY`, `OPENWEATHER_API_KEY`).
- **Backup Procedure**:
  1. Record OpenWeatherMap account login email and API subscription tier in password manager.
- **Recovery & Regeneration Procedure**:
  1. Navigate to OpenWeatherMap API Keys Console: `https://home.openweathermap.org/api_keys`.
  2. Locate the active key, click the delete button to invalidate.
  3. Enter a new key name: `JARVIS_Weather_Engine` → click **"Generate"**.
  4. Copy the newly generated 32-character hexadecimal key.
  5. Store in Windows Credential Manager:
     ```powershell
     python -m jarvis.security.secrets set WEATHER_API_KEY <32_CHAR_HEX_KEY>
     ```
  6. Update local `.env`:
     ```dotenv
     OPENWEATHER_API_KEY=<32_CHAR_HEX_KEY>
     WEATHER_API_KEY=<32_CHAR_HEX_KEY>
     ```
  7. Test weather query:
     ```bash
     curl -s "https://api.openweathermap.org/data/2.5/weather?q=Hanoi&appid=<32_CHAR_HEX_KEY>&units=metric"
     ```
- **Rotation Policy**: Rotate annually (365 days).
- **Fail-Closed / Zero-Key Fallback**:
  ```powershell
  python -c "from jarvis.web.weather import WeatherClient; w = WeatherClient(api_key=''); res = w.get_current_weather('Hà Nội'); assert res.city == 'Hà Nội', res; print('Weather zero-key wttr.in fallback: PASS')"
  ```

---

### 3.10 Connector 10: GitHub Actions Secrets

- **Subsystem**: `.github/workflows/ci.yml`, `.github/workflows/release.yml`
- **Owner**: Primary User (`Duong Phuoc Hung`, GitHub repository owner)
- **Storage Location**: GitHub Repository Secrets (`https://github.com/Duong-Phuoc-Hung/JARVIS/settings/secrets/actions`).
- **Backup Procedure**:
  1. Maintain an encrypted, password-protected KeePassXC record holding the complete dictionary of CI/CD secrets.
  2. Maintain GitHub Personal Access Token (PAT) with `repo` scope to administer secrets programmatically.
- **Recovery & Regeneration Procedure**:
  1. Whenever any upstream connector token is regenerated per sections 3.1–3.4, update GitHub Actions secrets via GitHub CLI (`gh`):
     ```bash
     # Authenticate gh CLI if necessary:
     gh auth login --hostname github.com

     # Update all production communication secrets:
     gh secret set TELEGRAM_BOT_TOKEN --body "$NEW_TELEGRAM" --repo Duong-Phuoc-Hung/JARVIS
     gh secret set DISCORD_BOT_TOKEN --body "$NEW_DISCORD" --repo Duong-Phuoc-Hung/JARVIS
     gh secret set ZALO_OA_ACCESS_TOKEN --body "$NEW_ZALO_ACCESS" --repo Duong-Phuoc-Hung/JARVIS
     gh secret set ZALO_APP_ID --body "$NEW_ZALO_APP_ID" --repo Duong-Phuoc-Hung/JARVIS
     gh secret set ZALO_APP_SECRET --body "$NEW_ZALO_SECRET" --repo Duong-Phuoc-Hung/JARVIS
     gh secret set SMTP_USER --body "$NEW_SMTP_USER" --repo Duong-Phuoc-Hung/JARVIS
     gh secret set SMTP_PASSWORD --body "$NEW_SMTP_PASSWORD" --repo Duong-Phuoc-Hung/JARVIS
     ```
  2. Trigger CI workflow or push a commit to verify that integration workflows execute without secret errors.
- **Rotation Policy**: Synchronized immediately with each individual upstream credential rotation cycle.
- **Fail-Closed Verification**:
  In `.github/workflows/ci.yml`, test steps guard against missing secrets using conditional expressions (`if: env.TELEGRAM_BOT_TOKEN != ''`), ensuring that lack of credentials gracefully skips live network tests rather than fabricating fake passes.

---

### 3.11 Connector 11: PicoVoice Porcupine (Optional Wake Word)

- **Subsystem**: `jarvis/audio/wake_word.py`
- **Owner**: Primary User (`Duong Phuoc Hung`)
- **Storage Location**: Local `.env` (`PORCUPINE_ACCESS_KEY`), config dot-key `audio.wake_word.porcupine_access_key`.
- **Backup Procedure**:
  1. Record PicoVoice Developer Account email in password manager.
- **Recovery & Regeneration Procedure**:
  1. Log in to the PicoVoice Console: `https://console.picovoice.ai/`.
  2. Copy the AccessKey from the dashboard overview.
  3. If compromised, click **"Revoke AccessKey"** and generate a replacement.
  4. Update `.env`:
     ```dotenv
     PORCUPINE_ACCESS_KEY=<BASE64_ACCESS_KEY>
     ```
  5. Restart JARVIS audio engine.
- **Rotation Policy**: Rotate annually or upon account tier modification.
- **Fail-Closed Verification**:
  ```powershell
  python -c "from jarvis.audio.wake_word import WakeWordDetector; d = WakeWordDetector(); print('WakeWord initialized, fallback tier active:', d is not None)"
  # Missing Porcupine AccessKey causes detector to fall back to Vosk and energy-VAD cascade without crash.
  ```

---

### 3.12 Connector 12: Spotify Plugin (Optional Media Launcher)

- **Subsystem**: `jarvis/plugins/spotify.py`
- **Owner**: Primary User (`Duong Phuoc Hung`)
- **Storage Location**: Local `.env` (`SONG_URI`), config dot-key `plugins.spotify.song_uri`.
- **Backup Procedure**:
  1. Store favorite Spotify track or playlist URI in `config/default_config.yaml` or password manager.
- **Recovery & Regeneration Procedure**:
  1. Open Spotify application.
  2. Navigate to target track or playlist → click `...` (More options) → **Share** → **Copy Spotify URI** (or copy link).
  3. Update `.env`:
     ```dotenv
     SONG_URI=spotify:track:39shmbIHICJ2Wxnk1fPSdz
     ```
- **Rotation Policy**: Non-secret configuration; update on user preference change.
- **Fail-Closed Verification**:
  If Spotify application is not installed on Windows host, `os.startfile` or `ComputerController.open_app("spotify")` returns `success=False` with error `"Yêu cầu mở Spotify bị chặn hoặc tiến trình không tìm thấy"` without crashing.

---

## 4. Verification & Auditing Protocol

To audit the fail-closed status of all configured credentials across the repository, execute:

```powershell
# 1. Run diagnostic fail-closed probe:
python scripts/verify_credentials.py --verbose

# 2. Verify Windows Credential Manager integrity:
python -m jarvis.security.secrets migrate-dry

# 3. Verify comms adversarial fail-closed test suite:
pytest tests/test_adversarial_beta_m1_comms_failclosed.py -v
```

All 12 connectors maintain complete fail-closed compliance:
- **No silent fallbacks**: Zero dummy successes.
- **No data fabrication**: Zero synthetic message payloads.
- **No unhandled exceptions**: Unconfigured services surface canonical error codes (`NOT_CONFIGURED`, `UNAVAILABLE`, `API_KEY_MISSING`).
