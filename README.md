# 🤖 JARVIS — Trợ Lý AI Cá Nhân Tự Trị Cho Windows

<div align="center">

[![CI Status](https://github.com/Duong-Phuoc-Hung/JARVIS/actions/workflows/ci.yml/badge.svg)](https://github.com/Duong-Phuoc-Hung/JARVIS/actions)
[![Tests](https://img.shields.io/badge/tests-passing-00ff88?style=flat-square)](https://github.com/Duong-Phuoc-Hung/JARVIS/actions)
[![Source Version](https://img.shields.io/badge/source%20version-5.1.0-purple?style=flat-square)](https://github.com/Duong-Phuoc-Hung/JARVIS/blob/main/pyproject.toml)
[![Releases](https://img.shields.io/badge/releases-GitHub-blue?style=flat-square)](https://github.com/Duong-Phuoc-Hung/JARVIS/releases)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue?style=flat-square)](https://python.org)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11%2064--bit-0078D4?style=flat-square)](https://github.com/Duong-Phuoc-Hung/JARVIS)
[![License](https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square)](LICENSE)

**JARVIS** là hệ thống trợ lý AI cá nhân tự trị (Autonomous AI Desktop Assistant) chạy nền trên Windows 11/10 64-bit, lấy cảm hứng từ trợ lý JARVIS của Tony Stark trong Iron Man. 
JARVIS có khả năng nhận diện giọng nói offline tiếng Việt & tiếng Anh, tự động phân luồng ý định thông minh, tự động viết mã mở rộng kỹ năng (Self-Coding với Sandbox Dry-Run), ghi nhớ nhật ký và tìm kiếm từ vựng thời gian thực (Lexical / TF-IDF Search Memory), điều khiển toàn diện hệ thống Windows, tự động hóa trình duyệt qua Playwright CDP và kết nối điều khiển từ xa qua Telegram, Zalo OA và Discord.

<sub>**Phiên bản mã nguồn / phát triển (source/runtime, `jarvis.__version__`): 5.1.0** trên `main` — hoàn thiện toàn bộ các nhiệm vụ D-01 đến D-17 của phân hệ Core / Backend / Integrations / Release: GitHub Actions CI xanh 100%, PacketCapture truthfulness với TShark thật, Playwright CDP fail-closed, chống web prompt injection, kiểm soát Home Assistant authoritative write path có allowlist an toàn, Auto-Updater với rollback SHA-256, gói chẩn đoán log redaction và bộ cài đặt Windows Installer một chạm `JARVIS_Setup_v5.1.0.exe`.</sub>


</div>

---

## ðŸ“‹ Má»¥c Lá»¥c

1. [âœ¨ TÃ­nh NÄƒng Ná»•i Báº­t](#-tÃ­nh-nÄƒng-ná»•i-báº­t)
2. [ðŸ’» YÃªu Cáº§u Há»‡ Thá»‘ng (Prerequisites)](#-yÃªu-cáº§u-há»‡-thá»‘ng-prerequisites)
3. [ðŸš€ HÆ°á»›ng Dáº«n CÃ i Äáº·t Tá»«ng BÆ°á»›c (Step-by-Step Installation)](#-hÆ°á»›ng-dáº«n-cÃ i-Ä‘áº·t-tá»«ng-bÆ°á»›c-step-by-step-installation)
4. [⚡ Dành Cho Người Dùng Cuối — Quick Start (Installer & Standalone ZIP)](#-dành-cho-người-dùng-cuối--quick-start-installer--standalone-zip)
5. [ðŸ› ï¸ DÃ nh Cho NhÃ  PhÃ¡t Triá»ƒn (Developer Setup)](#%EF%B8%8F-dÃ nh-cho-nhÃ -phÃ¡t-triá»ƒn-developer-setup)
6. [ðŸ”§ CÃ¡c Lá»—i ThÆ°á»ng Gáº·p & CÃ¡ch Kháº¯c Phá»¥c (Common Errors & Fixes)](#-cÃ¡c-lá»—i-thÆ°á»ng-gáº·p--cÃ¡ch-kháº¯c-phá»¥c-common-errors--fixes)
7. [âš™ï¸ Cáº¥u HÃ¬nh `.env` & Báº£o Máº­t Secrets](#%EF%B8%8F-cáº¥u-hÃ¬nh-env--báº£o-máº­t-secrets)
8. [ðŸ§° Danh SÃ¡ch Ká»¹ NÄƒng Chi Tiáº¿t (18+ Skills)](#-danh-sÃ¡ch-ká»¹-nÄƒng-chi-tiáº¿t-18-skills)
9. [âŒ¨ï¸ PhÃ­m Táº¯t ToÃ n Há»‡ Thá»‘ng](#%EF%B8%8F-phÃ­m-táº¯t-toÃ n-há»‡-thá»‘ng)
10. [ðŸ“± Äiá»u Khiá»ƒn Qua Äiá»‡n Thoáº¡i (Telegram / Zalo / Discord)](#-Ä‘iá»u-khiá»ƒn-qua-Ä‘iá»‡n-thoáº¡i)
11. [ðŸ—ï¸ Kiáº¿n TrÃºc Giá»ng NÃ³i & Tá»± Trá»‹ (Architecture)](#%EF%B8%8F-kiáº¿n-trÃºc-giá»ng-nÃ³i--tá»±-trá»‹-architecture)
12. [ðŸ”’ MÃ´ HÃ¬nh Báº£o Máº­t (Security Model)](#-mÃ´-hÃ¬nh-báº£o-máº­t-security-model)
13. [ðŸ“„ Giáº¥y PhÃ©p & TÃ¡c Giáº£](#-giáº¥y-phÃ©p--tÃ¡c-giáº£)

---

## âœ¨ TÃ­nh NÄƒng Ná»•i Báº­t

### ðŸŽ™ï¸ Nháº­n Diá»‡n Giá»ng NÃ³i Offline & Voice Pipeline (v5.1.0)
- **Wake Word:** Nháº­n diá»‡n tá»« khÃ³a *"Hey JARVIS"* tá»©c thÃ¬ vá»›i Ä‘á»™ trá»… cá»±c tháº¥p.
- **Barge-in (Ngáº¯t lá»i tá»©c thá»i):** Khi JARVIS Ä‘ang nÃ³i, báº¡n cÃ³ thá»ƒ nÃ³i chÃ¨n vÃ o â€” há»‡ thá»‘ng láº­p tá»©c táº¯t Ã¢m thanh TTS vÃ  chuyá»ƒn sang nghe lá»‡nh má»›i.
- **VAD (Voice Activity Detection):** Thuáº­t toÃ¡n phÃ¡t hiá»‡n giá»ng nÃ³i thÃ´ng minh báº±ng nÄƒng lÆ°á»£ng RMS hoáº·c WebRTC VAD â€” xá»­ lÃ½ offline, Ä‘á»™ trá»… <10ms.
- **STT (Speech-to-Text) & Safe Diacritic Normalization:** Faster-Whisper (CTranslate2) cháº¡y offline vá»›i bá»™ chuáº©n hÃ³a bá» dáº¥u Ä‘a Ã¢m an toÃ n (`strip_vietnamese_diacritics`) báº£o vá»‡ nguyÃªn váº¹n tá»« Ä‘Æ¡n, triá»‡t tiÃªu 100% va cháº¡m homophone (`nháº¡c` vs `nháº¯c`, `dá»«ng` vs `dá»¥ng`, `dÃ¡n` vs `dáº«n`, `táº¯t` vs `táº¯c`).
- **KhÃ¡ng Lá»‡ch Ngá»¯ Ã‚m (Phonetic Drift Robustness):** TÃ­ch há»£p 15 alias ngá»¯ Ã¢m chá»n lá»c cho cÃ¡c lá»—i nghe nháº§m Ä‘áº·c thÃ¹ cá»§a Faster-Whisper (`táº¯c mÃ¡y`, `táº­p mÃ¡y tÃ­nh`, `cÃ¡i Ä‘áº·t`, `Ä‘áº·t time`, `táº¯c tÃ­nh`, `táº¯t tÃ­nh`, `ghi chÃº`), nÃ¢ng Ä‘á»™ chÃ­nh xÃ¡c thá»±c táº¿ trÃªn 90 audio test lÃªn 63.3% vÃ  Ä‘áº¡t 100% trÃªn táº­p held-out má»›i.
- **Tiered STT Coordinator (v5.1.0 Phase 5):** Tá»± Ä‘á»™ng Ä‘iá»u phá»‘i phÃ¢n táº§ng nháº­n diá»‡n Ä‘a cáº¥p giá»¯a Faster-Whisper Local (Tier 1), OpenAI Whisper Cloud (Tier 2) vÃ  Windows SAPI (Tier 3) dá»±a trÃªn Æ°á»›c tÃ­nh cháº¥t lÆ°á»£ng tÃ­n hiá»‡u SNR (>10dB) vÃ  thá»i háº¡n deadline; tÃ­ch há»£p VAD silence bypass (<1ms, 0 GPU inference).
- **TTS (Text-to-Speech):** Piper TTS offline mÆ°á»£t mÃ  tá»± nhiÃªn (<80ms) cÃ¹ng tÃ¹y chá»n káº¿t ná»‘i ElevenLabs cháº¥t lÆ°á»£ng studio.

### ðŸ§  Router Ã Äá»‹nh 3 Lá»›p ThÃ´ng Minh (3-Tier Intent Router)
- **Regex & Rule Fast-Path:** Nháº­n diá»‡n ngay láº­p tá»©c hÆ¡n 150+ máº«u cÃ¢u lá»‡nh tiáº¿ng Viá»‡t khÃ´ng cáº§n gá»i LLM (zero-latency, 0 token), tá»± Ä‘á»™ng há»— trá»£ cáº£ cÃ³ dáº¥u, khÃ´ng dáº¥u vÃ  biáº¿n thá»ƒ ngá»¯ Ã¢m.
- **Project & Workspace Assistant:** Quáº£n lÃ½ dá»± Ã¡n, chuáº©n bá»‹ workspace, táº¡o project, liá»‡t kÃª thÆ° má»¥c vÃ  theo dÃµi Git thÃ´ng minh.
- **Fallback Gemini LLM:** PhÃ¢n tÃ­ch Ã½ Ä‘á»‹nh phá»©c táº¡p qua Google Gemini 1.5 Flash / Pro khi khÃ´ng khá»›p rule.
- **Autonomous ReAct Agent:** Tá»± Ä‘á»™ng láº­p káº¿ hoáº¡ch (Plan), thá»±c thi cÃ´ng cá»¥ (Act), quan sÃ¡t (Observe) vÃ  pháº£n há»“i (Reflect).

### ðŸ§¬ Tá»± Sinh Ká»¹ NÄƒng Má»›i (Self-Coding Skills)
- NÃ³i *"JARVIS, táº¡o ká»¹ nÄƒng theo dÃµi giÃ¡ vÃ ng"* â†’ JARVIS tá»± thiáº¿t káº¿ interface, viáº¿t code Python, kiá»ƒm tra cÃº phÃ¡p an toÃ n tÄ©nh (AST Validator), cháº¡y thá»­ nghiá»‡m cÃ´ láº­p trong CodeInterpreterSandbox (Job Object & Low Integrity) vÃ  Ä‘Äƒng kÃ½ trá»±c tiáº¿p vÃ o há»‡ thá»‘ng trong <15 giÃ¢y.

### ðŸ” Bá»™ Nhá»› Tá»« Vá»±ng & TÃ¬m Kiáº¿m TÃ i Liá»‡u (Lexical Search Memory - Tier 1 Hardened)
- Tá»± Ä‘á»™ng lÆ°u trá»¯ nháº­t kÃ½ há»™i thoáº¡i, ghi chÃº vÃ  tÃ i liá»‡u vÃ o SQLite lexical store (TF-IDF BM25 & Cosine Similarity) hoÃ n toÃ n offline.
- **An toÃ n Ä‘a luá»“ng & Ghi Ä‘Ä©a nguyÃªn tá»­ (Phase 6):** Kiá»ƒm thá»­ chá»‹u táº£i 30 luá»“ng Ä‘á»“ng thá»i (30-thread stress test), khÃ³a `RLock` toÃ n diá»‡n, vÃ  cÆ¡ cháº¿ ghi Ä‘Ä©a nguyÃªn tá»­ (Atomic Replace) ngÄƒn cháº·n triá»‡t Ä‘á»ƒ tÃ¬nh tráº¡ng há»ng dá»¯ liá»‡u hoáº·c xung Ä‘á»™t Ä‘á»c/ghi khi nhiá»u tÃ¡c vá»¥ cháº¡y ngáº§m.
- TÃ¬m kiáº¿m tá»« khÃ³a vÃ  ngá»¯ cáº£nh: *"HÃ´m qua tÃ´i nÃ³i gÃ¬ vá» káº¿ hoáº¡ch dá»± Ã¡n?"*

### ðŸŒ Tá»± Äá»™ng HÃ³a TrÃ¬nh Duyá»‡t & Há»‡ Thá»‘ng
- Äiá»u khiá»ƒn Chrome trá»±c tiáº¿p qua giao thá»©c Playwright CDP (Chrome DevTools Protocol).
- PhÃ¢n tÃ­ch ngá»¯ cáº£nh mÃ n hÃ¬nh tá»©c thá»i qua Gemini Vision AI (`Ctrl+Shift+Space`).
- Tá»± Ä‘á»™ng hÃ³a macro chuá»™t/bÃ n phÃ­m, Ä‘iá»u khiá»ƒn Ã¢m lÆ°á»£ng, mÃ n hÃ¬nh, quáº£n lÃ½ file vÃ  á»©ng dá»¥ng Windows.

---

## ðŸ’» YÃªu Cáº§u Há»‡ Thá»‘ng (Prerequisites)

TrÆ°á»›c khi cÃ i Ä‘áº·t, vui lÃ²ng Ä‘áº£m báº£o mÃ¡y tÃ­nh cá»§a báº¡n Ä‘Ã¡p á»©ng cÃ¡c yÃªu cáº§u sau:

| ThÃ nh pháº§n | YÃªu cáº§u tá»‘i thiá»ƒu | Chi tiáº¿t & Link táº£i chÃ­nh thá»©c |
|---|---|---|
| **Há»‡ Ä‘iá»u hÃ nh** | Windows 11 / 10 (64-bit) | Build 19041 trá»Ÿ lÃªn (Há»— trá»£ Win32 API & System Tray) |
| **Python** | **Python 3.13+ (64-bit)** | Táº£i táº¡i: [Python 3.13.2 64-bit](https://www.python.org/downloads/release/python-3132/)<br>âš ï¸ **Báº¯t buá»™c:** TÃ­ch chá»n âœ… **"Add python.exe to PATH"** trong mÃ n hÃ¬nh cÃ i Ä‘áº·t Ä‘áº§u tiÃªn. |
| **Git** | Git for Windows | Táº£i táº¡i: [Git for Windows Official](https://git-scm.com/download/win) |
| **Visual C++ Runtime** | VC++ 2015â€“2022 Redistributable (x64) | Táº£i táº¡i: [vc_redist.x64.exe (Microsoft)](https://aka.ms/vs/17/release/vc_redist.x64.exe)<br>*(Báº¯t buá»™c cho Pillow, sounddevice, CTranslate2, faster-whisper)* |
| **Pháº§n cá»©ng Ã¢m thanh** | Microphone & Loa / Tai nghe | Äáº£m báº£o micro vÃ  loa hoáº¡t Ä‘á»™ng bÃ¬nh thÆ°á»ng trong Windows Settings |
| **API Key** | Google Gemini API Key | Láº¥y miá»…n phÃ­ táº¡i: [Google AI Studio](https://aistudio.google.com/apikey) |

---

## ðŸš€ HÆ°á»›ng Dáº«n CÃ i Äáº·t Tá»«ng BÆ°á»›c (Step-by-Step Installation)

DÃ nh cho ngÆ°á»i dÃ¹ng vÃ  láº­p trÃ¬nh viÃªn muá»‘n cÃ i Ä‘áº·t tá»« mÃ£ nguá»“n (Source Code) trÃªn Windows 11/10.

### BÆ°á»›c 1: Clone kho mÃ£ nguá»“n (Repository)

Má»Ÿ **PowerShell** hoáº·c **Command Prompt (Terminal)** vÃ  cháº¡y:

```powershell
git clone https://github.com/Duong-Phuoc-Hung/JARVIS.git
cd JARVIS
```

### BÆ°á»›c 2: Táº¡o mÃ´i trÆ°á»ng áº£o (Virtual Environment)

Táº¡o mÃ´i trÆ°á»ng áº£o Ä‘á»™c láº­p Ä‘á»ƒ trÃ¡nh xung Ä‘á»™t vá»›i cÃ¡c thÆ° viá»‡n Python khÃ¡c trÃªn há»‡ thá»‘ng:

```powershell
python -m venv .venv
```

### BÆ°á»›c 3: KÃ­ch hoáº¡t Virtual Environment

- **TrÃªn PowerShell:**
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```
  *(ðŸ’¡ Náº¿u gáº·p lá»—i `ExecutionPolicy`: cháº¡y lá»‡nh `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` rá»“i kÃ­ch hoáº¡t láº¡i).*

- **TrÃªn Command Prompt (CMD):**
  ```cmd
  .venv\Scripts\activate.bat
  ```

Sau khi kÃ­ch hoáº¡t, Ä‘áº§u dÃ²ng lá»‡nh sáº½ xuáº¥t hiá»‡n tiá»n tá»‘ `(.venv)`.

### BÆ°á»›c 4: CÃ i Ä‘áº·t cÃ¡c thÆ° viá»‡n phá»¥ thuá»™c (Dependencies)

Cáº­p nháº­t `pip` vÃ  cÃ i Ä‘áº·t danh má»¥c thÆ° viá»‡n:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> â³ QuÃ¡ trÃ¬nh cÃ i Ä‘áº·t máº¥t khoáº£ng 1â€“3 phÃºt tÃ¹y tá»‘c Ä‘á»™ máº¡ng.

### BÆ°á»›c 5: Cáº¥u hÃ¬nh file mÃ´i trÆ°á»ng `.env`

Táº¡o file `.env` táº¡i thÆ° má»¥c gá»‘c cá»§a dá»± Ã¡n `JARVIS\` vÃ  Ä‘iá»n Gemini API Key cá»§a báº¡n:

```powershell
# Táº¡o nhanh file .env báº±ng PowerShell (UTF-8 clean encoding):
Set-Content -Path .env -Value "GEMINI_API_KEY=AIzaSyYourActualAPIKeyHere" -Encoding utf8
```

Hoáº·c má»Ÿ trÃ¬nh soáº¡n tháº£o vÃ  táº¡o file `.env` vá»›i ná»™i dung Ä‘áº§y Ä‘á»§:

```env
# â”€â”€ Cáº¥u hÃ¬nh báº¯t buá»™c â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
GEMINI_API_KEY=AIzaSyYourActualGeminiAPIKeyHere
GOOGLE_API_KEY=AIzaSyYourActualGeminiAPIKeyHere

# â”€â”€ Cáº¥u hÃ¬nh giá»ng nÃ³i & ngÃ´n ngá»¯ (TÃ¹y chá»n) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
JARVIS_LANGUAGE=vi
JARVIS_WHISPER_MODEL=base
JARVIS_VOICE=vi_VN-vivos-medium

# â”€â”€ Äiá»u khiá»ƒn tá»« xa (TÃ¹y chá»n) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
DISCORD_BOT_TOKEN=
DISCORD_GUILD_ID=
ZALO_ACCESS_TOKEN=
ZALO_OA_ID=
```

### BÆ°á»›c 6: Kiá»ƒm tra sá»©c khá»e há»‡ thá»‘ng (Health Check)

Cháº¡y lá»‡nh kiá»ƒm tra cháº©n Ä‘oÃ¡n toÃ n bá»™ 17 há»‡ thá»‘ng con (Audio, Wake Word, Memory Store, UI Tray, Router, v.v.):

```powershell
python -m jarvis health-check
```

Äáº£m báº£o táº¥t cáº£ cÃ¡c má»¥c quan trá»ng Ä‘á»u bÃ¡o `[+] READY`.

### BÆ°á»›c 7: Khá»Ÿi cháº¡y JARVIS láº§n Ä‘áº§u

```powershell
# Khá»Ÿi cháº¡y JARVIS (Máº·c Ä‘á»‹nh cháº¡y ná»n á»Ÿ khay há»‡ thá»‘ng System Tray):
python -m jarvis

# Xem trá»£ giÃºp vÃ  danh sÃ¡ch tÃ¹y chá»n dÃ²ng lá»‡nh:
python -m jarvis --help

# Khá»Ÿi cháº¡y á»Ÿ cháº¿ Ä‘á»™ Headless (khÃ´ng báº­t khay há»‡ thá»‘ng):
python -m jarvis run --headless
```

Sau khi khá»Ÿi cháº¡y:
- Biá»ƒu tÆ°á»£ng JARVIS xuáº¥t hiá»‡n á»Ÿ khay há»‡ thá»‘ng (System Tray cáº¡nh Ä‘á»“ng há»“).
- NÃ³i *"Hey JARVIS"* hoáº·c nháº¥n phÃ­m táº¯t `Ctrl+Shift+J` Ä‘á»ƒ báº¯t Ä‘áº§u trÃ² chuyá»‡n!

### BÆ°á»›c 8: J.A.R.V.I.S. Terminal Control Center (giao diá»‡n Terminal tÆ°Æ¡ng tÃ¡c)

NgoÃ i cháº¿ Ä‘á»™ voice-first máº·c Ä‘á»‹nh, JARVIS cÃ²n cung cáº¥p má»™t giao diá»‡n Terminal/PowerShell
tÆ°Æ¡ng tÃ¡c dáº¡ng menu phÃ¢n cáº¥p â€” má»™t lá»›p trÃ¬nh bÃ y má»ng (thin presentation layer) gá»i trá»±c
tiáº¿p vÃ o cÃ¡c module sáº£n pháº©m hiá»‡n cÃ³, khÃ´ng sao chÃ©p logic nghiá»‡p vá»¥ hay bá» qua báº¥t ká»³ cÆ¡ cháº¿
an toÃ n nÃ o:

```powershell
python -m jarvis menu
# hoáº·c, sau khi cÃ i Ä‘áº·t package:
jarvis menu
```

Äiá»u hÆ°á»›ng báº±ng má»™t phÃ­m sá»‘ duy nháº¥t (há»— trá»£ cáº£ `msvcrt` má»™t-phÃ­m trÃªn Windows Terminal/
PowerShell láº«n cháº¿ Ä‘á»™ nháº­p dÃ²ng khi stdin Ä‘Æ°á»£c redirect). Bá»™ phÃ­m toÃ n cá»¥c nháº¥t quÃ¡n trÃªn má»i
mÃ n hÃ¬nh:

| PhÃ­m | Chá»©c nÄƒng |
|---|---|
| `[1]`â€“`[9]` | Chá»n module (Hardware, InfoSec, Workflow, Data, Smart Home, Biometrics, Gesture, Communications, Self-Healing) |
| `[J]` | Khá»Ÿi cháº¡y JARVIS Voice Core tháº­t (cÃ¹ng má»™t `JarvisApp` dÃ¹ng bá»Ÿi `jarvis run` â€” khÃ´ng cÃ³ lÃµi JARVIS thá»© hai) |
| `[A]` | Cháº¡y táº¥t cáº£ cÃ¡c thao tÃ¡c **an toÃ n cho batch** trÃªn mÃ n hÃ¬nh hiá»‡n táº¡i â€” chá»‰ hiá»ƒn thá»‹ khi cÃ³ **tá»« 2 thao tÃ¡c an toÃ n trá»Ÿ lÃªn** (khÃ´ng bao giá» gá»­i tin nháº¯n, khÃ´ng bao giá» cháº¥m dá»©t tiáº¿n trÃ¬nh, khÃ´ng bao giá» báº­t/táº¯t toÃ n bá»™ thiáº¿t bá»‹) |
| `[R]` | LÃ m má»›i mÃ n hÃ¬nh hiá»‡n táº¡i |
| `[S]` | LÆ°u káº¿t quáº£/phiÃªn lÃ m viá»‡c vÃ o thÆ° má»¥c bÃ¡o cÃ¡o cá»§a JARVIS (`%LOCALAPPDATA%/JARVIS/reports/cli/`) |
| `[B]` | Quay láº¡i má»™t cáº¥p menu |
| `[H]` | Trá»£ giÃºp cho mÃ n hÃ¬nh hiá»‡n táº¡i |
| `[0]` | ThoÃ¡t |

**An toÃ n**: má»i tráº¡ng thÃ¡i hiá»ƒn thá»‹ Ä‘á»u trung thá»±c (khÃ´ng cÃ³ `READY` giáº£ chá»‰ vÃ¬ má»™t class
import thÃ nh cÃ´ng); má»i bÃ¡o cÃ¡o lÆ°u Ä‘á»u Ä‘Æ°á»£c xÃ¡c minh Ä‘Ã£ ghi thÃ nh cÃ´ng trÆ°á»›c khi bÃ¡o "ÄÃ£
lÆ°u"; cÃ¡c thÃ´ng tin nháº¡y cáº£m (token, máº­t kháº©u, embedding sinh tráº¯c há»c) luÃ´n Ä‘Æ°á»£c áº©n
(`<REDACTED>`) trÆ°á»›c khi lÆ°u hoáº·c hiá»ƒn thá»‹. XÃ¡c nháº­n Y/N trÃªn Terminal chá»‰ lÃ  lá»›p UX quyáº¿t
Ä‘á»‹nh cÃ³ thá»­ gá»i hÃ nh Ä‘á»™ng hay khÃ´ng â€” khÃ´ng bao giá» tá»± nÃ³ lÃ  lá»›p xÃ¡c thá»±c. Vá»›i **cháº¥m dá»©t
tiáº¿n trÃ¬nh** (Self-Healing), backend `HealingEngine` tá»± kiá»ƒm tra danh sÃ¡ch tiáº¿n trÃ¬nh Ä‘Æ°á»£c
bảo vệ (`PROTECTED_PROCESS_WHITELIST`) trước khi thực thi, bất kể ai gọi. Với **điều khiển thiết bị Smart Home (v5.1.0)**: Đã có **authoritative write path** thông qua `ActionDispatcher` (`smart_home_turn_on`, `smart_home_turn_off`, `smart_home_set_temp`, `home_assistant_call`). Hệ thống áp dụng danh sách miền an toàn nghiêm ngặt (`ALLOWED_DOMAINS`: light, switch, climate, media_player, fan, sensor) và từ chối dứt điểm (`SECURITY_REFUSAL`) với các thực thể nhạy cảm (`lock.*`, `alarm_control_panel.*`, `camera.*`, `siren.*`, `valve.*`, `vacuum.*`). Thao tác chỉ thực thi khi Home Assistant được cấu hình đầy đủ `HASS_URL` và `HASS_TOKEN` trong Windows Credential Manager. Không bao giờ chạy tự động qua `[A]`.
---

## ⚡ Dành Cho Người Dùng Cuối — Quick Start (Installer & Standalone ZIP)

Để phục vụ thử nghiệm Product Beta v1 cho 10–30 người dùng nội bộ, JARVIS cung cấp cả bộ cài đặt chuẩn Windows một chạm và bản portable ZIP độc lập:

### Cách 1: Bộ Cài Đặt Một Chạm — One-Click Windows Installer (Khuyến nghị cho Beta v1)
1. **Tải Bộ Cài Đặt:**
   - Tải file `JARVIS_Setup_v5.1.0.exe` (71.4 MB) từ [Releases Page](https://github.com/Duong-Phuoc-Hung/JARVIS/releases) hoặc thư mục phát hành `dist/installer/`.
   - **Mã băm kiểm tra toàn vẹn SHA-256**:
     ```text
     E6335E5BF7F704B0FA09E38937BA89CB668939FF9090746B45150ED722031650
     ```
2. **Cài Đặt Dễ Dàng:**
   - Chạy `JARVIS_Setup_v5.1.0.exe` và làm theo hướng dẫn trên màn hình.
   - Trình cài đặt Inno Setup 6 tự động tạo shortcut trên Desktop, Start Menu và tùy chọn khởi động cùng Windows.
3. **Cấu Hình & Khởi Động:**
   - Điền Gemini API Key trong giao diện cấu hình ban đầu hoặc lưu vào Windows Credential Manager.
   - JARVIS sẽ chạy nền tại khay hệ thống (System Tray). Nhấn tổ hợp phím `Ctrl+Shift+L` hoặc nói *"Hey JARVIS"* để ra lệnh.
4. **Gỡ Cài Đặt Sạch Sẽ:**
   - Gỡ bỏ dễ dàng và an toàn thông qua Windows Settings > Apps & Features hoặc chạy `unins000.exe` trong thư mục cài đặt mà không làm mất cấu hình cá nhân của người dùng.

### Cách 2: Bản Standalone Portable (ZIP)
Nếu bạn không muốn cài đặt vào Program Files:
1. Tải file ZIP `JARVIS_v5.1.0_windows_x64.zip` từ trang Releases.
2. Giải nén vào thư mục tùy chọn (ví dụ: `D:\JARVIS\`).
3. Chạy `JARVIS.exe` hoặc `JARVIS.exe --tray`.

---

## ðŸ› ï¸ DÃ nh Cho NhÃ  PhÃ¡t Triá»ƒn (Developer Setup)

DÃ nh cho cÃ¡c láº­p trÃ¬nh viÃªn muá»‘n tÃ¹y biáº¿n mÃ£ nguá»“n, viáº¿t thÃªm ká»¹ nÄƒng hoáº·c Ä‘Ã³ng gÃ³p mÃ£ nguá»“n (Contributing).

### CÃ i Ä‘áº·t mÃ´i trÆ°á»ng phÃ¡t triá»ƒn Ä‘áº§y Ä‘á»§

```powershell
git clone https://github.com/Duong-Phuoc-Hung/JARVIS.git
cd JARVIS
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# CÃ i Ä‘áº·t trá»n gÃ³i bao gá»“m táº¥t cáº£ dev dependencies vÃ  optional extras:
pip install -e ".[all]"
```

### Cháº¡y bá»™ kiá»ƒm thá»­ (Running Test Suites)

JARVIS bao gá»“m hÆ¡n 630+ bÃ i kiá»ƒm thá»­ tá»± Ä‘á»™ng toÃ n diá»‡n:

```powershell
# Cháº¡y toÃ n bá»™ test suites:
pytest tests/

# Cháº¡y kiá»ƒm thá»­ kÃ¨m bÃ¡o cÃ¡o Ä‘á»™ bao phá»§ mÃ£ nguá»“n (Coverage Report):
pytest tests/ --cov=jarvis --cov-report=term-missing

# Cháº¡y kiá»ƒm thá»­ riÃªng cho bá»™ nháº­n diá»‡n Intent Router:
pytest tests/test_router_project_intents.py -v
```

### Kiá»ƒm tra cÃº phÃ¡p, Linting & Type Checking

```powershell
# Kiá»ƒm tra code style vÃ  quy chuáº©n vá»›i Ruff:
ruff check .

# Tá»± Ä‘á»™ng Ä‘á»‹nh dáº¡ng code:
ruff format .

# Kiá»ƒm tra tÄ©nh kiá»ƒu dá»¯ liá»‡u (Static Type Checking) vá»›i Mypy:
mypy jarvis
```

### ÄÃ³ng gÃ³i á»©ng dá»¥ng (Building Executable & Installer)

```powershell
# 1. ÄÃ³ng gÃ³i thÃ nh file cháº¡y trá»±c tiáº¿p dist/JARVIS.exe:
python scripts/build_exe.py

# 2. ÄÃ³ng gÃ³i thÃ nh file cÃ i Ä‘áº·t Windows Installer dist/installer/JARVIS_Setup_v5.0.0.exe
#    (chá»‰ build local qua Inno Setup â€” release workflow chÃ­nh thá»©c trÃªn GitHub Actions
#    KHÃ”NG publish file Setup nÃ y, chá»‰ publish JARVIS_v<version>_windows_x64.zip):
python scripts/build_installer.py
```

---

## ðŸ”§ CÃ¡c Lá»—i ThÆ°á»ng Gáº·p & CÃ¡ch Kháº¯c Phá»¥c (Common Errors & Fixes)

DÆ°á»›i Ä‘Ã¢y lÃ  5 lá»—i phá»• biáº¿n nháº¥t vÃ  giáº£i phÃ¡p xá»­ lÃ½ triá»‡t Ä‘á»ƒ:

### 1. âŒ SQLite database locked / Permission Denied
- **Hiá»‡n tÆ°á»£ng:** Gáº·p lá»—i `sqlite3.OperationalError: database is locked` hoáº·c `PermissionError` khi khá»Ÿi Ä‘á»™ng hoáº·c lÆ°u ghi chÃº.
- **NguyÃªn nhÃ¢n:** CÃ³ tiáº¿n trÃ¬nh JARVIS khÃ¡c Ä‘ang cháº¡y ngáº§m chiáº¿m giá»¯ database, hoáº·c phiÃªn lÃ m viá»‡c trÆ°á»›c bá»‹ táº¯t Ä‘á»™t ngá»™t khiáº¿n file `.wal` / `.shm` bá»‹ khÃ³a.
- **CÃ¡ch kháº¯c phá»¥c:**
  1. ÄÃ³ng toÃ n bá»™ tiáº¿n trÃ¬nh JARVIS Ä‘ang cháº¡y:
     ```powershell
     Stop-Process -Name "JARVIS","python" -Force -ErrorAction SilentlyContinue
     ```
  2. Kiá»ƒm tra thÆ° má»¥c dá»¯ liá»‡u táº¡i `%LOCALAPPDATA%\JARVIS\data` (hoáº·c `~/.jarvis/`).
  3. XÃ³a cÃ¡c file lock táº¡m `.wal` vÃ  `.shm`:
     ```powershell
     Remove-Item "$env:LOCALAPPDATA\JARVIS\data\*.db-wal" -Force -ErrorAction SilentlyContinue
     Remove-Item "$env:LOCALAPPDATA\JARVIS\data\*.db-shm" -Force -ErrorAction SilentlyContinue
     ```
  4. Khá»Ÿi Ä‘á»™ng láº¡i JARVIS.

---

### 2. âŒ PIL / Pillow DLL Load Failed
- **Hiá»‡n tÆ°á»£ng:** `ImportError: DLL load failed while importing _imaging: The specified module could not be found.`
- **NguyÃªn nhÃ¢n:** Há»‡ Ä‘iá»u hÃ nh Windows bá»‹ thiáº¿u thÆ° viá»‡n C runtime cá»§a Microsoft hoáº·c cache cÃ i Ä‘áº·t Pillow bá»‹ lá»—i.
- **CÃ¡ch kháº¯c phá»¥c:**
  1. Táº£i vÃ  cÃ i Ä‘áº·t [Visual C++ 2015â€“2022 Redistributable (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe).
  2. CÃ i Ä‘áº·t láº¡i Pillow khÃ´ng dÃ¹ng cache:
     ```powershell
     pip uninstall -y Pillow
     pip install --no-cache-dir Pillow
     ```

---

### 3. âŒ faster-whisper CTranslate2 model download / CUDA fallback
- **Hiá»‡n tÆ°á»£ng:** Lá»—i khi táº£i mÃ´ hÃ¬nh Whisper tá»« Hugging Face Hub (Connection Timeout / SSL Error) hoáº·c lá»—i crash liÃªn quan Ä‘áº¿n CUDA/GPU.
- **NguyÃªn nhÃ¢n:** MÃ¡y tÃ­nh khÃ´ng cÃ³ card Ä‘á»“ há»a NVIDIA hoáº·c CUDA toolkit khÃ´ng khá»›p; káº¿t ná»‘i tá»›i HuggingFace bá»‹ giÃ¡n Ä‘oáº¡n.
- **CÃ¡ch kháº¯c phá»¥c:**
  1. Cáº¥u hÃ¬nh fallback sang CPU int8 trong file cáº¥u hÃ¬nh `config.yaml` hoáº·c `.env`:
     ```yaml
     whisper:
       device: "cpu"
       compute_type: "int8"
     ```
  2. Náº¿u máº¡ng quá»‘c táº¿ bá»‹ ngháº½n, cáº¥u hÃ¬nh mirror Hugging Face trÃªn PowerShell trÆ°á»›c khi cháº¡y:
     ```powershell
     $env:HF_ENDPOINT = "https://hf-mirror.com"
     ```
  3. Táº£i trÆ°á»›c model Ä‘á»ƒ kiá»ƒm tra:
     ```powershell
     python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"
     ```

---

### 4. âŒ UAC / Administrator Rights & PhÃ­m Táº¯t ToÃ n Cá»¥c (Hotkeys)
- **Hiá»‡n tÆ°á»£ng:** PhÃ­m táº¯t `Ctrl+Shift+J` hoáº·c tÃ­nh nÄƒng gá»­i phÃ­m tá»± Ä‘á»™ng khÃ´ng hoáº¡t Ä‘á»™ng khi Ä‘ang focus vÃ o cÃ¡c cá»­a sá»• cháº¡y quyá»n Admin (nhÆ° Task Manager, CMD Administrator).
- **NguyÃªn nhÃ¢n:** CÆ¡ cháº¿ báº£o máº­t UIPI (User Interface Privilege Isolation) cá»§a Windows ngÄƒn á»©ng dá»¥ng quyá»n chuáº©n tÆ°Æ¡ng tÃ¡c vá»›i cá»­a sá»• quyá»n Elevated Administrator.
- **CÃ¡ch kháº¯c phá»¥c:**
  1. Äá»‘i vá»›i nhu cáº§u hÃ ng ngÃ y, cháº¡y JARVIS dÆ°á»›i quyá»n tÃ i khoáº£n chuáº©n (Standard User).
  2. Náº¿u thÆ°á»ng xuyÃªn lÃ m viá»‡c trÃªn cÃ¡c cá»­a sá»• Administrator vÃ  muá»‘n JARVIS can thiá»‡p: Nháº¥p chuá»™t pháº£i vÃ o `JARVIS.exe` (hoáº·c Terminal) vÃ  chá»n **"Run as administrator"**.

---

### 5. âŒ API Key 401 Unauthorized / Invalid API Key
- **Hiá»‡n tÆ°á»£ng:** Lá»—i `google.api_core.exceptions.InvalidArgument: 401 Unauthorized` hoáº·c `API_KEY_INVALID`.
- **NguyÃªn nhÃ¢n:** File `.env` Ä‘áº·t sai vá»‹ trÃ­, tÃªn biáº¿n khÃ´ng Ä‘Ãºng chuáº©n, hoáº·c API Key bá»‹ dÃ­nh khoáº£ng tráº¯ng, dáº¥u ngoáº·c kÃ©p thá»«a.
- **CÃ¡ch kháº¯c phá»¥c:**
  1. Äáº£m báº£o file `.env` náº±m táº¡i thÆ° má»¥c gá»‘c cá»§a dá»± Ã¡n hoáº·c `%LOCALAPPDATA%\JARVIS\.env`.
  2. Sá»­ dá»¥ng Ä‘á»‹nh dáº¡ng chuáº©n (khÃ´ng dÃ¹ng dáº¥u ngoáº·c kÃ©p, khÃ´ng khoáº£ng tráº¯ng):
     ```env
     GEMINI_API_KEY=AIzaSyD-YourExactKeyHere
     GOOGLE_API_KEY=AIzaSyD-YourExactKeyHere
     ```
  3. Kiá»ƒm tra káº¿t ná»‘i API Key trá»±c tiáº¿p:
     ```powershell
     python -c "import os, dotenv, google.generativeai as genai; dotenv.load_dotenv(); genai.configure(api_key=os.getenv('GEMINI_API_KEY')); print(genai.GenerativeModel('gemini-1.5-flash').generate_content('ping').text)"
     ```

---

## âš™ï¸ Cáº¥u HÃ¬nh `.env`

Báº£ng mÃ´ táº£ cÃ¡c biáº¿n mÃ´i trÆ°á»ng há»— trá»£ trong `.env`:

| TÃªn biáº¿n | Báº¯t buá»™c | Máº·c Ä‘á»‹nh | Ã nghÄ©a |
|---|---|---|---|
| `GEMINI_API_KEY` | **CÃ³** | â€” | API Key láº¥y tá»« [Google AI Studio](https://aistudio.google.com/apikey) |
| `GOOGLE_API_KEY` | TÃ¹y chá»n | â€” | Dá»± phÃ²ng cho `GEMINI_API_KEY` |
| `JARVIS_LANGUAGE` | KhÃ´ng | `vi` | NgÃ´n ngá»¯ giao tiáº¿p chÃ­nh (`vi` hoáº·c `en`) |
| `JARVIS_WHISPER_MODEL` | KhÃ´ng | `base` | Model Whisper: `tiny`, `base`, `small`, `medium` |
| `JARVIS_VOICE` | KhÃ´ng | `vi_VN-vivos-medium` | TÃªn giá»ng Ä‘á»c Piper TTS trong `~/.jarvis/voices/` |
| `JARVIS_HEADLESS` | KhÃ´ng | `0` | `0`: Cháº¿ Ä‘á»™ thÆ°á»ng (Tray UI), `1`: Headless mode (Server) |
| `TELEGRAM_BOT_TOKEN` | KhÃ´ng | â€” | Token Telegram Bot tá»« @BotFather |
| `TELEGRAM_CHAT_ID` | KhÃ´ng | â€” | Chat ID ngÆ°á»i dÃ¹ng nháº­n thÃ´ng bÃ¡o Telegram |
| `DISCORD_BOT_TOKEN` | KhÃ´ng | â€” | Token á»©ng dá»¥ng Discord Bot |
| `ZALO_ACCESS_TOKEN` | KhÃ´ng | â€” | Access token Zalo Official Account |

### ðŸ”’ Báº£o Máº­t: Di Chuyá»ƒn `.env` Sang Windows Credential Manager (`SecretsManager`)

Äá»ƒ báº£o vá»‡ cÃ¡c API Keys khÃ´ng bá»‹ lÆ°u dÆ°á»›i dáº¡ng vÄƒn báº£n thÃ´ (plaintext) trÃªn á»• Ä‘Ä©a, JARVIS há»— trá»£ cÃ´ng cá»¥ di chuyá»ƒn tá»± Ä‘á»™ng sang Windows Credential Manager:

```powershell
# 1. Xem trÆ°á»›c cÃ¡c khÃ³a sáº½ Ä‘Æ°á»£c di chuyá»ƒn an toÃ n (Dry Run - khÃ´ng thay Ä‘á»•i file):
python -m jarvis.cli migrate-secrets --dry-run

# 2. Thá»±c hiá»‡n di chuyá»ƒn vÃ  tá»± Ä‘á»™ng xÃ³a giÃ¡ trá»‹ plaintext khá»i file .env (Purge):
python -m jarvis.cli migrate-secrets --purge
```
Sau khi thá»±c hiá»‡n, há»‡ thá»‘ng `ConfigManager` sáº½ tá»± Ä‘á»™ng truy xuáº¥t API Keys trá»±c tiáº¿p tá»« Windows Credential Manager an toÃ n mÃ  khÃ´ng cáº§n lÆ°u khÃ³a thÃ´ trong `.env`.

---

## ðŸ§° Danh SÃ¡ch Ká»¹ NÄƒng Chi Tiáº¿t (18+ Skills)

JARVIS Ä‘Æ°á»£c tÃ­ch há»£p sáºµn 18+ ká»¹ nÄƒng máº¡nh máº½, tá»± Ä‘á»™ng kÃ­ch hoáº¡t qua giá»ng nÃ³i hoáº·c vÄƒn báº£n:

| # | Ká»¹ nÄƒng | Intent ID | CÃ¢u lá»‡nh máº«u | MÃ´ táº£ chá»©c nÄƒng |
|---|---|---|---|---|
| 1 | ðŸ“° **Briefing SÃ¡ng** | `briefing` | *"JARVIS, bÃ¡o cÃ¡o sÃ¡ng nay"* | Tá»•ng há»£p thá»i tiáº¿t, tin tá»©c ná»•i báº­t vÃ  lá»‹ch trÃ¬nh |
| 2 | ðŸ“ **Ghi ChÃº Nhanh** | `note_taker` | *"Ghi chÃº: há»p dá»± Ã¡n lÃºc 3h chiá»u"* | LÆ°u trá»¯ vÃ  tÃ¬m kiáº¿m ghi chÃº toÃ n vÄƒn vá»›i SQLite FTS5 |
| 3 | â±ï¸ **Bá»™ Äáº¿m Pomodoro** | `pomodoro` | *"Báº¯t Ä‘áº§u táº­p trung 25 phÃºt"* | Äáº¿m ngÆ°á»£c chu ká»³ lÃ m viá»‡c, thÃ´ng bÃ¡o toast khi hoÃ n thÃ nh |
| 4 | ðŸ’» **Äiá»u Khiá»ƒn Há»‡ Thá»‘ng**| `system_control`| *"TÄƒng Ã¢m lÆ°á»£ng 20%", "KhÃ³a mÃ¡y tÃ­nh"* | Äiá»u chá»‰nh Ã¢m thanh, chá»¥p mÃ n hÃ¬nh, khÃ³a mÃ¡y Windows |
| 5 | ðŸ—‚ï¸ **Quáº£n LÃ½ File** | `file_manager` | *"TÃ¬m file bÃ¡o cÃ¡o doanh thu"* | TÃ¬m kiáº¿m vÃ  má»Ÿ táº­p tin, thÆ° má»¥c theo ngÃ´n ngá»¯ tá»± nhiÃªn |
| 6 | ðŸ§® **MÃ¡y TÃ­nh ThÃ´ng Minh**| `calculator` | *"TÃ­nh 15% cá»§a 5 triá»‡u rÆ°á»¡i"* | TÃ­nh toÃ¡n biá»ƒu thá»©c toÃ¡n há»c vÃ  quy Ä‘á»•i tá»· giÃ¡/Ä‘Æ¡n vá»‹ |
| 7 | ðŸ“‹ **Quáº£n LÃ½ Clipboard** | `clipboard` | *"Äá»c clipboard", "Sao chÃ©p: Xin chÃ o"* | Äá»c to ná»™i dung clipboard hoáº·c lÆ°u trá»¯ lá»‹ch sá»­ sao chÃ©p |
| 8 | ðŸš€ **Má»Ÿ á»¨ng Dá»¥ng** | `app_launcher` | *"Má»Ÿ Google Chrome", "Má»Ÿ VS Code"* | Fuzzy search tÃ¬m vÃ  khá»Ÿi cháº¡y pháº§n má»m trÃªn mÃ¡y |
| 9 | ðŸ‘ï¸ **PhÃ¢n TÃ­ch MÃ n HÃ¬nh**| `screen_context`| *"Giáº£i thÃ­ch lá»—i trÃªn mÃ n hÃ¬nh"* (`Ctrl+Shift+Space`) | Chá»¥p áº£nh mÃ n hÃ¬nh vÃ  phÃ¢n tÃ­ch vá»›i Gemini Vision AI |
| 10| âºï¸ **Ghi & PhÃ¡t Macro** | `macro_recorder`| *"Ghi láº¡i macro gá»­i email"* | Tá»± Ä‘á»™ng hÃ³a chuá»—i thao tÃ¡c bÃ n phÃ­m/chuá»™t láº·p láº¡i |
| 11| ðŸ”Š **Sound Board** | `sound_board` | *"PhÃ¡t Ã¢m thanh hoÃ n thÃ nh"* | PhÃ¡t Ã¢m thanh pháº£n há»“i tráº¡ng thÃ¡i vui nhá»™n |
| 12| ðŸ” **TÃ¬m KÃ½ á»¨c / TÃ i Liá»‡u** | `rag_search` | *"Tuáº§n trÆ°á»›c tÃ´i nÃ³i gÃ¬ vá» dá»± Ã¡n X?"* | TÃ¬m kiáº¿m tá»« khÃ³a vÃ  ngá»¯ cáº£nh (TF-IDF & Lexical Search) |
| 13| ðŸ§¬ **Tá»± Viáº¿t Ká»¹ NÄƒng** | `skill_synthesizer`| *"Táº¡o ká»¹ nÄƒng theo dÃµi giÃ¡ vÃ ng"* | Tá»± Ä‘á»™ng viáº¿t code Python vÃ  náº¡p ká»¹ nÄƒng má»›i trong <15s |
| 14| ðŸŒ™ **Night Planner** | `night_planner` | *"Tá»‘i nay phÃ¢n tÃ­ch cÃ¡c file log"* | Thá»±c hiá»‡n tÃ¡c vá»¥ náº·ng ban Ä‘Ãªm vÃ  bÃ¡o cÃ¡o lÃºc sÃ¡ng |
| 15| ðŸ  **NhÃ  ThÃ´ng Minh** | `smart_home_discovery`| *"QuÃ©t thiáº¿t bá»‹ nhÃ  thÃ´ng minh"* | QuÃ©t mDNS vÃ  Ä‘iá»u khiá»ƒn Home Assistant / Tasmota |
| 16| ðŸŒ **Äiá»u Khiá»ƒn Browser**| `browser_control`| *"Má»Ÿ YouTube tÃ¬m bÃ i hÃ¡t Iron Man"* | Äiá»u khiá»ƒn trÃ¬nh duyá»‡t Chrome qua Playwright CDP |
| 17| ðŸ”„ **Tá»± Cáº­p Nháº­t** | `auto_updater` | *"Kiá»ƒm tra báº£n cáº­p nháº­t má»›i"* | Tá»± Ä‘á»™ng kiá»ƒm tra vÃ  nÃ¢ng cáº¥p phiÃªn báº£n qua GitHub |
| 18| ðŸ“‚ **Quáº£n LÃ½ Dá»± Ãn** | `workspace_prepare`| *"Má»Ÿ dá»± Ã¡n JARVIS", "Commit dá»± Ã¡n"* | Quáº£n lÃ½ dá»± Ã¡n láº­p trÃ¬nh, Git assistant vÃ  workspace |

---

## âŒ¨ï¸ PhÃ­m Táº¯t ToÃ n Há»‡ Thá»‘ng

CÃ¡c phÃ­m táº¯t hoáº¡t Ä‘á»™ng toÃ n cáº§u trÃªn Windows (ngay cáº£ khi á»©ng dá»¥ng Ä‘ang cháº¡y áº©n á»Ÿ System Tray):

| PhÃ­m táº¯t | HÃ nh Ä‘á»™ng | Chi tiáº¿t |
|---|---|---|
| `Ctrl + Shift + J` | **Toggle Listening** | Báº­t / Táº¯t cháº¿ Ä‘á»™ láº¯ng nghe giá»ng nÃ³i |
| `Ctrl + Shift + Space` | **PhÃ¢n tÃ­ch mÃ n hÃ¬nh** | Chá»¥p mÃ n hÃ¬nh vÃ  gá»­i Gemini Vision AI phÃ¢n tÃ­ch |
| `Ctrl + Shift + L` | **KhÃ³a mÃ¡y tÃ­nh** | KhÃ³a mÃ n hÃ¬nh Windows (`LockWorkStation`) tá»©c thÃ¬ |
| `Ctrl + Shift + M` | **Mute Microphone** | Táº¯t / Má»Ÿ nhanh microphone cá»§a JARVIS |
| `Ctrl + Shift + B` | **Briefing SÃ¡ng** | Äá»c to báº£n tin tá»•ng há»£p buá»•i sÃ¡ng |
| `Ctrl + Shift + S` | **Chá»¥p mÃ n hÃ¬nh** | LÆ°u áº£nh chá»¥p mÃ n hÃ¬nh cháº¥t lÆ°á»£ng cao ra Desktop |

---

## ðŸ“± Äiá»u Khiá»ƒn Qua Äiá»‡n Thoáº¡i

### Telegram Bot
1. Nháº¯n tin cho `@BotFather` trÃªn Telegram Ä‘á»ƒ táº¡o bot vÃ  láº¥y `TELEGRAM_BOT_TOKEN`.
2. Äiá»n token vÃ  `TELEGRAM_CHAT_ID` vÃ o file `.env`.
3. Gá»­i lá»‡nh `/start`, `/status`, `/briefing`, `/note`, `/screenshot` hoáº·c trÃ² chuyá»‡n báº±ng ngÃ´n ngá»¯ tá»± nhiÃªn tá»« báº¥t ká»³ Ä‘Ã¢u!

### Zalo Official Account & Discord Bot
- Há»— trá»£ webhook 2 chiá»u qua cá»•ng `8765` cho Zalo OA.
- TÃ­ch há»£p Discord Bot qua `DISCORD_BOT_TOKEN` Ä‘á»ƒ Ä‘iá»u khiá»ƒn mÃ¡y tÃ­nh qua channel Discord riÃªng tÆ°.

---

## ðŸ—ï¸ Kiáº¿n TrÃºc Giá»ng NÃ³i & Tá»± Trá»‹ (Architecture)

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                              INPUT LAYER                               â”‚
â”‚  ðŸŽ™ï¸ Voice (VAD RMS/WebRTC)  ðŸ“± Telegram  ðŸ’¬ Discord  ðŸ“ž Zalo OA        â”‚
â”‚  âŒ¨ï¸ Global Win32 Hotkeys   ðŸ‘ï¸ Screen Context Vision                   â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                    â”‚
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                         INTELLIGENCE ROUTER                            â”‚
â”‚  Layer 1: Regex Fast-Path (20+ VN patterns, zero-latency, 0 token)     â”‚
â”‚  Layer 2: Rule Engine Greedy Matcher (Workspace, System, Media, App)   â”‚
â”‚  Layer 3: Gemini 1.5 Flash / Pro LLM Fallback                          â”‚
â”‚  Layer 4: Autonomous ReAct Engine (Think âž” Act âž” Observe âž” Reflect)    â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                    â”‚
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                           CORE SKILLS (18+)                            â”‚
â”‚  briefing Â· note_taker Â· pomodoro Â· system_control Â· file_manager       â”‚
â”‚  calculator Â· clipboard Â· app_launcher Â· screen_context Â· macro_rec    â”‚
â”‚  rag_search Â· skill_synthesizer Â· night_planner Â· smart_home           â”‚
â”‚  browser_control Â· auto_updater Â· project_manager Â· git_assistant      â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                    â”‚
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                       OUTPUT & EXECUTION LAYER                         â”‚
â”‚  ðŸ—£ï¸ Piper TTS / ElevenLabs (<80ms)    ðŸ”” Windows Notification Toast     â”‚
â”‚  ðŸªŸ Silent Subprocess Manager (No-Flash) ðŸ’¾ SQLite FTS5 Memory         â”‚
â”‚  ðŸŒ Playwright CDP Automation          ðŸ“Š Health Diagnostics           â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

---

## ðŸ”’ MÃ´ HÃ¬nh Báº£o Máº­t (Security Model)

- **Cháº¡y Ngáº§m TÄ©nh Láº·ng (No Console Flash):** ToÃ n bá»™ cÃ¡c tiáº¿n trÃ¬nh subprocess/PowerShell/CMD Ä‘Æ°á»£c spawn Ä‘á»u cháº¡y áº©n hoÃ n toÃ n (`CREATE_NO_WINDOW`), khÃ´ng giÃ¡n Ä‘oáº¡n tráº£i nghiá»‡m ngÆ°á»i dÃ¹ng.
- **Báº£o Máº­t Bá»™ Nhá»› Cá»¥c Bá»™:** Dá»¯ liá»‡u ghi chÃº, kÃ½ á»©c vÃ  cáº¥u hÃ¬nh Ä‘Æ°á»£c lÆ°u cá»¥c bá»™ trÃªn mÃ¡y táº¡i `%LOCALAPPDATA%\JARVIS\` vÃ  thÆ° má»¥c ngÆ°á»i dÃ¹ng `~/.jarvis/`.
- **An ToÃ n MÃ£ Nguá»“n:** TÃ­nh nÄƒng tá»± táº¡o ká»¹ nÄƒng (Self-Coding) Ä‘Æ°á»£c kiá»ƒm tra cÃº phÃ¡p vÃ  cháº¡y thá»­ nghiá»‡m trong sandbox an toÃ n trÆ°á»›c khi tÃ­ch há»£p vÃ o há»‡ thá»‘ng.

**Ghi chÃº báº£o trÃ¬ gáº§n Ä‘Ã¢y nháº¥t (sau v4.7.0, khÃ´ng Ä‘á»•i phiÃªn báº£n runtime):**
- Tá»± phá»¥c há»“i há»‡ thá»‘ng (Self-Healing) giá» chá»‰ bÃ¡o thÃ nh cÃ´ng sau khi viá»‡c cháº¥m dá»©t tiáº¿n trÃ¬nh Ä‘Ã£ Ä‘Æ°á»£c **xÃ¡c nháº­n thá»±c sá»± xáº£y ra** â€” khÃ´ng cÃ²n tá»± nháº­n thÃ nh cÃ´ng chá»‰ vÃ¬ lá»‡nh cháº¥m dá»©t Ä‘Æ°á»£c gá»i.
- RAM Ä‘Ã£ giáº£i phÃ³ng khÃ´ng bao giá» bá»‹ bá»‹a Ä‘áº·t â€” chá»‰ bÃ¡o cÃ¡o tá»« phÃ©p Ä‘o trÆ°á»›c/sau thá»±c táº¿, bá» qua khi khÃ´ng Ä‘o Ä‘Æ°á»£c.
- Test wake-word Whisper trÃªn CI Ä‘Ã£ Ä‘Æ°á»£c lÃ m táº¥t Ä‘á»‹nh giá»¯a cÃ¡c mÃ´i trÆ°á»ng cÃ³/khÃ´ng cÃ i `faster-whisper` â€” **khÃ´ng** thay Ä‘á»•i hÃ nh vi wake-word tháº­t khi cháº¡y production.
- Káº¿t quáº£ tháº¥t báº¡i cá»§a má»™t lá»‡nh giá» Ä‘Æ°á»£c lan truyá»n trung thá»±c xuyÃªn suá»‘t há»‡ thá»‘ng â€” tá»« hÃ nh Ä‘á»™ng thá»±c thi, qua bá»™ Ä‘iá»u phá»‘i hÃ nh Ä‘á»™ng, Ä‘áº¿n pháº£n há»“i hiá»ƒn thá»‹ cho ngÆ°á»i dÃ¹ng, nháº­t kÃ½ tÆ°Æ¡ng tÃ¡c vÃ  bá»™ nhá»› â€” khÃ´ng cÃ²n trÆ°á»ng há»£p má»™t lá»‡nh tháº¥t báº¡i bá»‹ bÃ¡o cÃ¡o nháº§m thÃ nh cÃ´ng.

---

## ðŸ“„ Giáº¥y PhÃ©p & TÃ¡c Giáº£

Dá»± Ã¡n Ä‘Æ°á»£c phÃ¡t hÃ nh theo giáº¥y phÃ©p **MIT License**. Xem file [LICENSE](LICENSE) Ä‘á»ƒ biáº¿t thÃªm chi tiáº¿t.

- **TÃ¡c giáº£:** Duong Phuoc Hung
- **GitHub:** [@Duong-Phuoc-Hung](https://github.com/Duong-Phuoc-Hung)
- **Repository:** [https://github.com/Duong-Phuoc-Hung/JARVIS](https://github.com/Duong-Phuoc-Hung/JARVIS)

<div align="center">

*PhÃ¡t triá»ƒn vá»›i táº¥t cáº£ Ä‘am mÃª vÃ  sá»± táº­n tÃ¢m dÃ nh cho cá»™ng Ä‘á»“ng cÃ´ng nghá»‡ Windows & AI Assistant!* ðŸš€

[â­ Star Dá»± Ãn](https://github.com/Duong-Phuoc-Hung/JARVIS) Â· [ðŸ› BÃ¡o Lá»—i / ÄÃ³ng GÃ³p](https://github.com/Duong-Phuoc-Hung/JARVIS/issues) Â· [ðŸ“¦ Táº£i Báº£n PhÃ¡t HÃ nh](https://github.com/Duong-Phuoc-Hung/JARVIS/releases)

</div>

