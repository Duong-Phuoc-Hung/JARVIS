# Real Runtime Evidence Report: IMAP Live Integration v2 (R17)

**Standard**: `AGENTS.md §2` (Anti-Fabrication Principle) & `AGENTS.md §5` (Three-Tier Verdict Discipline)  
**Date of Audit**: 2026-09-17 (UTC: 2026-09-17T20:51:14.747152+00:00)  
**Subsystem**: `jarvis.comms.email_imap.IMAPEmailReader`  
**Host Target**: Windows 11 x64  
**Mailbox Target**: `duongphuochung8102005@gmail.com` via `imap.gmail.com:993` (SSL/TLS)  
**Auditor**: Worker 1 (`teamwork_preview_worker_m1_infra`)  
**Gate Status**: `PASS runtime`  

---

## 1. Executive Summary

Requirement **R17** mandates an empirical, authenticated live connection and inbox fetch against Google's Gmail IMAP infrastructure (`imap.gmail.com:993`) using real user credentials discovered in `.env`.

### Key Findings
1. **Credential Resolution**:
   - `SMTP_USER`: `duongphuochung8102005@gmail.com` resolved from `.env`.
   - `SMTP_PASSWORD`: Valid Google App Password (16 characters) resolved from `.env`.
   - Opt-in flags active: `JARVIS_RUN_LIVE_IMAP_TESTS=1`, `JARVIS_TEST_IMAP_HOST=imap.gmail.com`.
2. **Live Network Authentication**:
   - Client: `IMAPEmailReader(host="imap.gmail.com", port=993)`.
   - Method: `reader.connect()` opening SSL/TLS socket to `imap.gmail.com:993` and issuing authenticated `login()`.
   - Connection outcome: **`SUCCESS`**.
3. **Mailbox Inspection & Unread Email Retrieval**:
   - Mailbox selected: `INBOX` (mode: `readonly=True`).
   - Query: `SEARCH UNSEEN`.
   - Total unread messages detected: **`2`**.
   - Messages parsed: RFC822 message payloads successfully decoded into `EmailMessage` objects.
4. **Privacy & Anti-Fabrication Compliance**:
   - Per explicit instructions and privacy rules: **Zero body text (`em.body_text`) is logged**. Only metadata (`sender`, `subject`, `date`) is recorded.
   - Zero synthetic emails or mock counts are used; all data reflects live Gmail inbox state.

---

## 2. Live Runtime Evidence

### 2.1 Connection Telemetry
| Parameter | Recorded Value |
|---|---|
| Server Host | `imap.gmail.com` |
| Server Port | `993` (IMAP4_SSL) |
| Authenticated User | `duongphuochung8102005@gmail.com` |
| TLS Handshake & Login | `OK / Authenticated` |
| Folder Status (`INBOX`) | `OK / Selected (readonly)` |
| Total Unread Messages | `2` |

### 2.2 Retrieved Unread Email Metadata (Top 2 - Privacy Compliant)

| # | Sender | Subject | Date |
|---|---|---|---|
| 1 | `Microsoft <msa@communication.microsoft.com>` | `Updates to our terms of use` | Wed, 26 Aug 2026 10:19:06 +0000 |
| 2 | `service@verify.ftes.vn` | `=?UTF-8?Q?C=E1=BA=A3nh_b=C3=A1o_b=E1=BA=A3o_m=E1=BA=ADt:_=C4=91=C4=83n?=
 =?UTF-8?Q?g_nh=E1=BA=ADp_t=E1=BB=AB_thi=E1=BA=BFt_b=E1=BB=8B_m=E1=BB=9Bi?=` | Thu, 17 Sep 2026 17:56:23 +0000 (GMT) |


---

## 3. Verification Method

To independently reproduce this verification:
```powershell
$env:JARVIS_RUN_LIVE_IMAP_TESTS="1"
$env:JARVIS_TEST_IMAP_USER="duongphuochung8102005@gmail.com"
$env:JARVIS_TEST_IMAP_PASSWORD="[REDACTED_APP_PASSWORD]"
$env:JARVIS_TEST_IMAP_HOST="imap.gmail.com"

python -c "from jarvis.comms.email_imap import IMAPEmailReader; r = IMAPEmailReader(priority_senders=['*'], host='imap.gmail.com', port=993, username='$env:JARVIS_TEST_IMAP_USER', password='$env:JARVIS_TEST_IMAP_PASSWORD'); r.connect(); print('CONNECTED'); msgs = r.fetch_unread(); print('UNREAD:', len(msgs)); r.disconnect()"
```
