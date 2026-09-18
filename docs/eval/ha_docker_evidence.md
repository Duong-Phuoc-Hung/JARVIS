# Real Runtime Evidence Report: Home Assistant via Docker (R16 / R23)

**Standard**: `AGENTS.md §2` (Anti-Fabrication Principle) & `docs/AUDIT_FRAMEWORK.md`  
**Date of Initial Audit (R16)**: 2026-09-17 (UTC: 2026-09-17T20:51:11.215946+00:00)  
**Date of Retry Audit (R23)**: 2026-09-18 (UTC: 2026-09-18T11:01:00Z)  
**Subsystem**: `jarvis.smart_home.home_assistant.HomeAssistantClient` & Local Docker Daemon  
**Host Target**: Windows 11 x64  
**Auditors**: Worker 1 (`teamwork_preview_worker_m1_infra`) & Worker R23 (`worker_r23`)  
**Gate Status**: `HARDWARE_BLOCKED (DOCKER_NOT_RUNNING)`  

---

## 1. Executive Summary

Requirement **R16** evaluates the feasibility of executing a local Home Assistant container via Docker (`homeassistant/home-assistant:stable`) on port `8123` to test the authoritative smart home write path.

### Key Findings
1. **Docker Desktop & CLI Presence**:
   - `Docker Desktop.exe` is **present** on disk at `C:\Program Files\Docker\Docker\Docker Desktop.exe`.
   - `docker.exe` CLI is **present** on disk at `C:\Program Files\Docker\Docker\resources\bin\docker.EXE`.
   - CLI version output: `Docker version 29.5.3, build d1c06ef` (Exit code: `0`).
2. **Docker Daemon Operational State**:
   - Probing `docker info` exited with code `1`.
   - Probing `docker ps` exited with code `1`.
   - Output emitted by docker CLI:
     ```text
     Client:
 Version:    29.5.3
 Context:    desktop-linux
 Debug Mode: false
 Plugins:
  agent: Docker AI Agent Runner (Docker Inc.)
    Version:  v1.70.0
    Path:     C:\Program Files\Docker\cli-plugins\docker-agent.exe
  ai: Docker AI Agent - Ask Gordon (Docker Inc.)
    Version:  v1.24.0
    Path:     C:\Program Files\Docker\cli-plugins\docker-ai.exe
  buildx: Docker Buildx (Docker Inc.)
    Version:  v0.34.1-desktop.1
    Path:     C:\Program Files\Docker\cli-plugins\docker-buildx.exe
  compose: Docker Compose (Docker Inc.)
    Version:  v5.1.4
    Path:     C:\Program Files\Docker\cli-plugins\docker-compose.exe
  debug: Get a shell into any image or container (Docker Inc.)
    Version:  0.0.47
    Path:     C:\Program Files\Docker\cli-plugins\docker-debug.exe
  desktop: Docker Desktop commands (Docker Inc.)
    Version:  v0.3.0
    Path:     C:\Program Files\Docker\cli-plugins\docker-desktop.exe
  dhi: CLI for managing Docker Hardened Images (Docker Inc.)
    Version:  v0.0.4
    Path:     C:\Program Files\Docker\cli-plugins\docker-dhi.exe
  extension: Manages Docker extensions (Docker Inc.)
    Version:  v0.2.31
    Path:     C:\Program Files\Docker\cli-plugins\docker-extension.exe
  init: Creates Docker-related starter files for your project (Docker Inc.)
    Version:  v1.4.0
    Path:     C:\Program Files\Docker\cli-plugins\docker-init.exe
  mcp: Docker MCP Plugin (Docker Inc.)
    Version:  v0.42.2
    Path:     C:\Program Files\Docker\cli-plugins\docker-mcp.exe
  model: Docker Model Runner (Docker Inc.)
    Version:  v1.2.1
    Path:     C:\Program Files\Docker\cli-plugins\docker-model.exe
  offload: Docker Offload (Docker Inc.)
    Version:  v0.6.3
    Path:     C:\Program Files\Docker\cli-plugins\docker-offload.exe
  pass: Docker Pass Secrets Manager Plugin (beta) (Docker Inc.)
    Version:  v0.1.3
    Path:     C:\Program Files\Docker\cli-plugins\docker-pass.exe
  sandbox: Docker Sandbox (Docker Inc.)
    Version:  v0.12.0
    Path:     C:\Program Files\Docker\cli-plugins\docker-sandbox.exe
  scout: Docker Scout (Docker Inc.)
    Version:  v1.21.0
    Path:     C:\Program Files\Docker\cli-plugins\docker-scout.exe

Server:
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine; check if the path is correct and if the daemon is running: open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
     ```
   - Conclusion: The Docker Desktop engine / daemon is **NOT running** (service stopped or WSL2 integration inactive).
3. **Home Assistant Local Port 8123 Probe**:
   - Probe target: `http://localhost:8123/api/` (Timeout: 2.0s).
   - Observed result: `UNREACHABLE` (<urlopen error timed out>).
   - Port 8123 is closed; no Home Assistant container is active.
4. **Authoritative Subsystem State**:
   - Per `AGENTS.md §2` and `AUDIT_FRAMEWORK.md`, zero synthetic container states or mock API responses are fabricated.
   - Subsystem accurately reports `StatusLevel.UNAVAILABLE`.

---

## 2. Verbatim Command Outputs

### 2.1 `docker --version`
- **Command**: `docker --version`
- **Exit Code**: `0`
- **Output**:
```text
Docker version 29.5.3, build d1c06ef
```

### 2.2 `docker info`
- **Command**: `docker info`
- **Exit Code**: `1`
- **Output**:
```text
Client:
 Version:    29.5.3
 Context:    desktop-linux
 Debug Mode: false
 Plugins:
  agent: Docker AI Agent Runner (Docker Inc.)
    Version:  v1.70.0
    Path:     C:\Program Files\Docker\cli-plugins\docker-agent.exe
  ai: Docker AI Agent - Ask Gordon (Docker Inc.)
    Version:  v1.24.0
    Path:     C:\Program Files\Docker\cli-plugins\docker-ai.exe
  buildx: Docker Buildx (Docker Inc.)
    Version:  v0.34.1-desktop.1
    Path:     C:\Program Files\Docker\cli-plugins\docker-buildx.exe
  compose: Docker Compose (Docker Inc.)
    Version:  v5.1.4
    Path:     C:\Program Files\Docker\cli-plugins\docker-compose.exe
  debug: Get a shell into any image or container (Docker Inc.)
    Version:  0.0.47
    Path:     C:\Program Files\Docker\cli-plugins\docker-debug.exe
  desktop: Docker Desktop commands (Docker Inc.)
    Version:  v0.3.0
    Path:     C:\Program Files\Docker\cli-plugins\docker-desktop.exe
  dhi: CLI for managing Docker Hardened Images (Docker Inc.)
    Version:  v0.0.4
    Path:     C:\Program Files\Docker\cli-plugins\docker-dhi.exe
  extension: Manages Docker extensions (Docker Inc.)
    Version:  v0.2.31
    Path:     C:\Program Files\Docker\cli-plugins\docker-extension.exe
  init: Creates Docker-related starter files for your project (Docker Inc.)
    Version:  v1.4.0
    Path:     C:\Program Files\Docker\cli-plugins\docker-init.exe
  mcp: Docker MCP Plugin (Docker Inc.)
    Version:  v0.42.2
    Path:     C:\Program Files\Docker\cli-plugins\docker-mcp.exe
  model: Docker Model Runner (Docker Inc.)
    Version:  v1.2.1
    Path:     C:\Program Files\Docker\cli-plugins\docker-model.exe
  offload: Docker Offload (Docker Inc.)
    Version:  v0.6.3
    Path:     C:\Program Files\Docker\cli-plugins\docker-offload.exe
  pass: Docker Pass Secrets Manager Plugin (beta) (Docker Inc.)
    Version:  v0.1.3
    Path:     C:\Program Files\Docker\cli-plugins\docker-pass.exe
  sandbox: Docker Sandbox (Docker Inc.)
    Version:  v0.12.0
    Path:     C:\Program Files\Docker\cli-plugins\docker-sandbox.exe
  scout: Docker Scout (Docker Inc.)
    Version:  v1.21.0
    Path:     C:\Program Files\Docker\cli-plugins\docker-scout.exe

Server:
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine; check if the path is correct and if the daemon is running: open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

### 2.3 `docker ps`
- **Command**: `docker ps`
- **Exit Code**: `1`
- **Output**:
```text
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine; check if the path is correct and if the daemon is running: open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

### 2.4 HTTP Endpoint Probe (`http://localhost:8123/api/`)
- **Status**: `UNREACHABLE`
- **Detail**: `<urlopen error timed out>`

---

## 3. Classification & Prerequisites for Gate Closure

- **Three-Tier Verdict**: **`HARDWARE_BLOCKED (DOCKER_NOT_RUNNING)`**.
- **Prerequisites to promote to `PASS runtime`**:
  1. Start Docker Desktop (`"C:\Program Files\Docker\Docker\Docker Desktop.exe"`).
  2. Wait for Docker daemon socket initialization (`docker info` exits 0).
  3. Spin up Home Assistant:
     ```powershell
     docker run -d --name ha-test -p 8123:8123 homeassistant/home-assistant:stable
     ```
  4. Complete local onboarding, generate Long-Lived Access Token, configure `HASS_URL=http://localhost:8123` and `HASS_TOKEN`.
  5. Run authoritative write-path test (`test_home_assistant_authoritative.py`).

---

## 4. R23 Retry Audit: Service Start & Daemon Probing (2026-09-18)

### 4.1 Objective & Methodology
In Phase 4 Session Resume under requirement **R23**, Worker R23 executed the authoritative retry protocol:
1. Re-verify the existence and integrity of the Docker Desktop binary on Windows host storage.
2. Attempt to launch the Docker Desktop daemon service via PowerShell:
   `Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe' -WindowStyle Hidden`
3. Probe daemon status via `docker info`.
4. If daemon becomes healthy, pull `homeassistant/home-assistant:stable`, deploy on port 8123, probe readiness, and execute write-path verification via `ActionDispatcher`.
5. If daemon remains unstarted or blocked, record exact outputs and maintain truthful fail-closed status `HARDWARE_BLOCKED (DOCKER_NOT_RUNNING)`.

### 4.2 Verbatim Probe Observations
1. **Binary Verification**:
   - Location: `C:\Program Files\Docker\Docker\Docker Desktop.exe`
   - Filesystem Check: **`EXISTS`**
   - File Size: `13,208,496` bytes
   - Associated binaries present: `DockerCli.exe` (15,505,328 bytes), `com.docker.service` (36,784 bytes), `Docker Desktop Installer.exe` (7,002,544 bytes).
2. **Daemon Start Attempt**:
   - Command: `Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe' -WindowStyle Hidden`
   - Runtime Result: Execution blocked in headless subagent execution environment. Launching Docker Desktop requires interactive desktop session privileges, WSL2 / Hyper-V backend virtualization initialization, and system UAC approval that cannot be granted in an unattended background process.
3. **Daemon Socket Verification (`docker info`)**:
   - Command: `docker info`
   - Daemon Socket: `npipe:////./pipe/dockerDesktopLinuxEngine`
   - Daemon Status: **UNAVAILABLE** (named pipe not open, service engine stopped).
4. **Local Port 8123 Verification**:
   - Target: `http://localhost:8123`
   - Result: Inactive (port closed, no container running).

### 4.3 Final Gate Status for R23
- **Final Verdict**: **`HARDWARE_BLOCKED (DOCKER_NOT_RUNNING)`**
- **Anti-Fabrication Attestation (`AGENTS.md §2`)**:
  Zero synthetic responses, dummy containers, or mock tokens were generated. The Home Assistant smart home write path remains fail-closed and correctly reports `StatusLevel.UNAVAILABLE` / `HARDWARE_BLOCKED`.

