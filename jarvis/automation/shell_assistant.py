"""
Natural Language Shell Assistant for JARVIS.
Translates conversational developer intents into shell commands, parses and summarizes
complex CLI outputs (git, docker, netstat, package managers) into natural Vietnamese for TTS,
and protects system integrity with an adversarial destructive command safety gate.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Any

from jarvis.automation.safety_gate import SafetyGate


class ShellAssistant:
    """
    Intelligent Developer & OS Shell Assistant.
    Provides NL-to-CLI translation, execution, safety filtering, and TTS summarization.
    """

    DANGEROUS_PATTERNS: list[re.Pattern] = [
        re.compile(r"\brm\s+-[rf]{1,2}\b", re.IGNORECASE),
        re.compile(r"\brmdir\s+/[sq]\b", re.IGNORECASE),
        re.compile(r"\bdel\s+/[sqf]\b", re.IGNORECASE),
        re.compile(r"\berase\s+/[sqf]\b", re.IGNORECASE),
        re.compile(r"\berase\b", re.IGNORECASE),
        re.compile(r"\bformat\s+[a-zA-Z]:", re.IGNORECASE),
        re.compile(r"\bdrop\s+(database|table)\b", re.IGNORECASE),
        re.compile(r"\bdelete\s+from\b", re.IGNORECASE),
        re.compile(r"\btruncate\s+table\b", re.IGNORECASE),
        re.compile(r"\btaskkill\s+/[fF]\s+/im\s+(explorer|csrss|lsass|svchost)\.exe", re.IGNORECASE),
        re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE),
        re.compile(r"\bgit\s+clean\s+-[fF]", re.IGNORECASE),
        re.compile(r"\bdd\s+if=", re.IGNORECASE),
        re.compile(r"\bmkfs\b", re.IGNORECASE),
        re.compile(r"\bdiskpart\b", re.IGNORECASE),
        re.compile(r"\bRemove-Item\b.*-Recurse", re.IGNORECASE),
        re.compile(r"\bshutil\.rmtree\b", re.IGNORECASE),
    ]

    def __init__(
        self,
        default_cwd: str | None = None,
        safety_gate: SafetyGate | None = None,
        dispatcher: Any | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.default_cwd = os.path.abspath(default_cwd or os.getcwd())
        self.safety_gate = safety_gate or SafetyGate()
        self.dispatcher = dispatcher
        self.config = config or {}

    @property
    def _safety_gate(self) -> SafetyGate:
        return self.safety_gate

    # -----------------------------------------------------------------------
    # Destructive Command Safety Filter
    # -----------------------------------------------------------------------
    def is_destructive(self, command: str) -> bool:
        """
        Determines whether a command matches destructive or high-risk patterns.
        """
        if not command:
            return False
        cmd_clean = command.strip()
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.search(cmd_clean):
                return True
        return False

    # -----------------------------------------------------------------------
    # Dev Server Command Resolver
    # -----------------------------------------------------------------------
    def resolve_dev_server_command(self, cwd: str | None = None) -> str | None:
        """
        Analyzes project files in target directory and infers development server command.
        Supports Node.js, Django, FastAPI/Uvicorn, Flask, Rust, Go, Docker Compose.
        """
        target_dir = os.path.abspath(cwd or self.default_cwd)
        if not os.path.isdir(target_dir):
            return None

        # 1. Check package.json (Node.js / React / Vue / Next / Vite)
        pkg_json = os.path.join(target_dir, "package.json")
        if os.path.isfile(pkg_json):
            try:
                with open(pkg_json, encoding="utf-8") as f:
                    data = json.load(f)
                    scripts = data.get("scripts", {})
                    if "dev" in scripts:
                        return "npm run dev"
                    elif "start" in scripts:
                        return "npm start"
                    elif "serve" in scripts:
                        return "npm run serve"
                    return "npm start"
            except Exception:
                return "npm start"

        # 2. Check manage.py (Django)
        if os.path.isfile(os.path.join(target_dir, "manage.py")):
            return "python manage.py runserver"

        # 3. Check FastAPI / Uvicorn in main.py, app.py, api.py
        for entry_name in ["main.py", "app.py", "api.py", "server.py"]:
            entry_path = os.path.join(target_dir, entry_name)
            if os.path.isfile(entry_path):
                try:
                    with open(entry_path, encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        if "FastAPI" in content or "uvicorn" in content:
                            module_name = os.path.splitext(entry_name)[0]
                            return f"uvicorn {module_name}:app --reload"
                        elif "Flask" in content:
                            return f"python {entry_name}"
                except Exception:
                    pass

        # 4. Check Cargo.toml (Rust)
        if os.path.isfile(os.path.join(target_dir, "Cargo.toml")):
            return "cargo run"

        # 5. Check go.mod (Go)
        if os.path.isfile(os.path.join(target_dir, "go.mod")):
            return "go run ."

        # 6. Check Docker Compose
        if os.path.isfile(os.path.join(target_dir, "docker-compose.yml")) or os.path.isfile(
            os.path.join(target_dir, "compose.yaml")
        ):
            return "docker-compose up"

        # 7. Generic Python fallback
        if os.path.isfile(os.path.join(target_dir, "main.py")):
            return "python main.py"
        if os.path.isfile(os.path.join(target_dir, "app.py")):
            return "python app.py"

        return None

    # -----------------------------------------------------------------------
    # Natural Language Command Translator
    # -----------------------------------------------------------------------
    def translate_nl_command(self, query: str, cwd: str | None = None) -> tuple[str, str]:
        """
        Translates a natural language query (Vietnamese/English) into an inferred shell command.
        Returns (command_str, category_name).
        """
        q = query.strip()
        q_lower = q.lower()
        target_dir = cwd or self.default_cwd

        # 1. Dev Server Triggers
        dev_server_keywords = [
            "chạy server", "start server", "start dev server", "bật server",
            "run server", "khởi động server", "chay server", "bat server", "khoi dong server"
        ]
        if any(kw in q_lower for kw in dev_server_keywords):
            inferred = self.resolve_dev_server_command(target_dir) or "npm start"
            return inferred, "dev_server"

        # 2. Git Status Triggers
        if any(kw in q_lower for kw in ["git status", "kiểm tra git", "kiem tra git", "trạng thái git", "trang thai git"]):
            return "git status", "git_status"

        # 3. Package Installation Triggers
        install_match = re.search(
            r"(?:cài đặt|cai dat|cài|cai|install)\s+(?:package|gói|goi|thư viện|thu vien)?\s*([a-zA-Z0-9_\-\.\@\/]+)",
            q,
            re.IGNORECASE,
        )
        if install_match:
            pkg_name = install_match.group(1).strip()
            # If in a node project, use npm install, otherwise pip
            pkg_json = os.path.join(target_dir, "package.json")
            if os.path.isfile(pkg_json):
                return f"npm install {pkg_name}", "package_install"
            return f"pip install {pkg_name}", "package_install"

        # 4. Docker Triggers
        if any(kw in q_lower for kw in ["restart docker", "khởi động lại docker", "khoi dong lai docker"]):
            return "docker restart $(docker ps -q)", "docker_restart"
        if any(kw in q_lower for kw in ["docker status", "trạng thái docker", "trang thai docker", "kiểm tra docker", "docker ps"]):
            return "docker ps -a", "docker_status"

        # 5. Port Inspection Triggers
        port_match = re.search(
            r"(?:port|cổng|cong)\s+(\d+)",
            q,
            re.IGNORECASE,
        )
        if port_match:
            port_num = port_match.group(1)
            return f"netstat -ano | findstr :{port_num}", "port_check"
        if any(kw in q_lower for kw in ["kiểm tra port", "kiem tra port", "check port", "các port đang chạy"]):
            return "netstat -ano", "port_check"

        # 6. Network IP Triggers
        if any(kw in q_lower for kw in ["xem ip", "địa chỉ ip", "dia chi ip", "ip máy tính", "ipconfig"]):
            return "ipconfig", "network_ip"

        # 7. Delete Directory Triggers (Destructive)
        del_dir_match = re.search(
            r"(?:xóa\s+sạch\s+thư\s+mục|xoa\s+sach\s+thu\s+muc|xóa\s+thư\s+mục|xoa\s+thu\s+muc|xóa\s+folder|xoa\s+folder|delete\s+folder|delete\s+directory)\s+(.+)",
            q,
            re.IGNORECASE,
        )
        if del_dir_match:
            path_arg = del_dir_match.group(1).strip()
            return f"rmdir /s /q {path_arg}", "destructive_delete"

        # 8. Clear Temp Triggers
        if any(kw in q_lower for kw in ["dọn dẹp temp", "don dep temp", "clear temp", "xóa file tạm", "xoa file tam"]):
            return "Remove-Item -Path $env:TEMP\\* -Recurse -Force", "clear_temp"

        # Fallback to literal command
        return q, "custom"

    # -----------------------------------------------------------------------
    # Git Status Runner & Summarizer
    # -----------------------------------------------------------------------
    def parse_git_status_output(self, output: str) -> str:
        """
        Parses raw `git status` output into clean, concise Vietnamese text for TTS.
        """
        if not output or not output.strip():
            return "Working tree sạch, không có thay đổi nào chưa commit, thưa Ngài."

        lines = [line.strip() for line in output.splitlines() if line.strip()]

        # Detect Branch
        branch = "main"
        branch_match = re.search(r"(?:On branch|##)\s+([^\s\.]+)", output, re.IGNORECASE)
        if branch_match:
            branch = branch_match.group(1)

        modified_count = 0
        untracked_count = 0
        staged_count = 0
        deleted_count = 0

        # Parse short or long git format
        in_staged_section = False
        in_unstaged_section = False
        in_untracked_section = False

        for line in lines:
            if "Changes to be committed:" in line:
                in_staged_section = True
                in_unstaged_section = False
                in_untracked_section = False
                continue
            elif "Changes not staged for commit:" in line:
                in_staged_section = False
                in_unstaged_section = True
                in_untracked_section = False
                continue
            elif "Untracked files:" in line:
                in_staged_section = False
                in_unstaged_section = False
                in_untracked_section = True
                continue

            # Short format checks (e.g. "M  file.py", " M file.py", "?? file.py", "A  file.py")
            if line.startswith("??"):
                untracked_count += 1
            elif line.startswith("M ") or line.startswith(" M") or line.startswith("MM"):
                modified_count += 1
            elif line.startswith("A ") or line.startswith("AM"):
                staged_count += 1
            elif line.startswith("D ") or line.startswith(" D"):
                deleted_count += 1
            # Long format checks
            elif in_staged_section:
                if "new file:" in line or "modified:" in line:
                    staged_count += 1
                elif "deleted:" in line:
                    deleted_count += 1
            elif in_unstaged_section:
                if "modified:" in line:
                    modified_count += 1
                elif "deleted:" in line:
                    deleted_count += 1
            elif in_untracked_section:
                if not line.startswith("(") and not line.startswith("nothing added"):
                    untracked_count += 1

        total_changes = modified_count + untracked_count + staged_count + deleted_count
        if total_changes == 0 or "working tree clean" in output.lower():
            return f"Nhánh {branch}: Working tree sạch, không có thay đổi nào chưa commit, thưa Ngài."

        parts: list[str] = []
        if staged_count > 0:
            parts.append(f"{staged_count} tệp đã sẵn sàng commit")
        if modified_count > 0:
            parts.append(f"{modified_count} tệp đã chỉnh sửa")
        if untracked_count > 0:
            parts.append(f"{untracked_count} tệp chưa theo dõi")
        if deleted_count > 0:
            parts.append(f"{deleted_count} tệp đã xóa")

        summary_details = ", ".join(parts)
        return f"Nhánh {branch}: Đang có {summary_details}, thưa Ngài."

    def git_status(self, repo_dir: str | None = None) -> str:
        """Runs git status and returns Vietnamese TTS summary."""
        target_dir = os.path.abspath(repo_dir or self.default_cwd)
        try:
            res = subprocess.run(
                ["git", "status", "-s", "-b"],
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if res.returncode != 0:
                res = subprocess.run(
                    ["git", "status"],
                    cwd=target_dir,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            output = res.stdout if res.returncode == 0 else res.stderr
            return self.parse_git_status_output(output)
        except Exception as e:
            return f"Không thể kiểm tra trạng thái Git: {e}"

    # -----------------------------------------------------------------------
    # Port Inspector
    # -----------------------------------------------------------------------
    def check_port(self, port: int) -> str:
        """Inspects network port binding and identifies holding process."""
        port_num = int(port)
        cmd = "netstat -ano"
        try:
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            lines = res.stdout.splitlines() if res.stdout else []
            matching_lines = [
                line for line in lines
                if f":{port_num} " in line or f":{port_num}\t" in line or line.rstrip().endswith(f":{port_num}")
            ]

            if not matching_lines:
                return f"Port {port_num} hiện đang rảnh, không có tiến trình nào chiếm dụng, thưa Ngài."

            # Parse state and PID from first match
            first_match = matching_lines[0].split()
            state = "LISTENING"
            pid = "N/A"
            if len(first_match) >= 4:
                # Format: TCP [Local Address] [Foreign Address] [State] [PID]
                if first_match[0].upper() == "TCP":
                    if len(first_match) >= 5:
                        state = first_match[3]
                        pid = first_match[4]
                    else:
                        pid = first_match[-1]
                else:
                    # UDP has no state
                    state = "UDP_BOUND"
                    pid = first_match[-1]

            proc_name = f"PID {pid}"
            # Attempt to find process name
            if pid.isdigit() and int(pid) > 0:
                try:
                    task_res = subprocess.run(
                        f"tasklist /fi \"PID eq {pid}\" /fo csv /nh",
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if task_res.stdout and '"' in task_res.stdout:
                        proc_name = task_res.stdout.split(",")[0].replace('"', "").strip()
                except Exception:
                    pass

            return f"Port {port_num} đang mở ở trạng thái {state}, được sử dụng bởi tiến trình {proc_name} (PID {pid}), thưa Ngài."
        except Exception as e:
            return f"Không thể kiểm tra port {port_num}: {e}"

    # -----------------------------------------------------------------------
    # Package Installer
    # -----------------------------------------------------------------------
    def install_package(
        self, package_name: str, manager: str = "auto", cwd: str | None = None
    ) -> tuple[bool, str]:
        """Installs a package via pip or npm and returns Vietnamese summary."""
        pkg = package_name.strip()
        target_dir = os.path.abspath(cwd or self.default_cwd)

        if manager == "auto":
            if os.path.isfile(os.path.join(target_dir, "package.json")):
                cmd = ["npm", "install", pkg]
            else:
                cmd = [sys.executable, "-m", "pip", "install", pkg]
        elif manager == "npm":
            cmd = ["npm", "install", pkg]
        else:
            cmd = [sys.executable, "-m", "pip", "install", pkg]

        try:
            res = subprocess.run(cmd, cwd=target_dir, capture_output=True, text=True, timeout=120)
            if res.returncode == 0:
                return True, f"Đã cài đặt thành công gói '{pkg}', thưa Ngài."
            else:
                err_line = (res.stderr or res.stdout).strip().splitlines()[-1] if (res.stderr or res.stdout) else "Lỗi không xác định"
                return False, f"Cài đặt gói '{pkg}' thất bại: {err_line}"
        except Exception as e:
            return False, f"Lỗi khi thực thi trình cài đặt gói: {e}"

    # -----------------------------------------------------------------------
    # Docker Status / Restart Runner
    # -----------------------------------------------------------------------
    def docker_status(self) -> str:
        """Queries Docker containers and returns Vietnamese summary."""
        try:
            res = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.Names}}: {{.Status}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if res.returncode != 0:
                return "Docker daemon hiện không hoạt động hoặc chưa được cài đặt trên máy tính, thưa Ngài."

            lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            if not lines:
                return "Docker daemon đang hoạt động nhưng hiện không có container nào, thưa Ngài."

            running = [l for l in lines if "Up " in l]
            total = len(lines)
            running_cnt = len(running)
            return f"Docker hiện có {running_cnt}/{total} container đang chạy, thưa Ngài."
        except Exception as e:
            return f"Không thể kiểm tra trạng thái Docker: {e}"

    def docker_restart(self) -> str:
        """Restarts Docker containers."""
        try:
            res = subprocess.run(
                "docker restart $(docker ps -q)",
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if res.returncode == 0:
                return "Đã khởi động lại toàn bộ các container Docker đang chạy, thưa Ngài."
            return "Không thể khởi động lại Docker containers hoặc không có container nào đang chạy."
        except Exception as e:
            return f"Lỗi khi khởi động lại Docker: {e}"

    # -----------------------------------------------------------------------
    # Stdout Summarization Engine (> 10 lines)
    # -----------------------------------------------------------------------
    def summarize_output(self, command: str, stdout: str, exit_code: int = 0) -> str:
        """
        Summarizes command stdout into clean, concise Vietnamese text suitable for TTS.
        If <= 10 lines, returns formatted text.
        If > 10 lines, uses specialized domain parsers or structured head/tail summary.
        """
        if not stdout:
            if exit_code == 0:
                return "Lệnh đã thực thi thành công, không có dữ liệu trả về."
            return f"Lệnh đã thực thi với mã lỗi {exit_code}."

        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        line_count = len(lines)

        # Handle short output (<= 10 lines)
        if line_count <= 10:
            return "\n".join(lines)

        cmd_lower = command.lower()

        # Domain Summarizer: Git Status
        if "git status" in cmd_lower:
            return self.parse_git_status_output(stdout)

        # Domain Summarizer: Pip / NPM Install
        if "pip install" in cmd_lower or "npm install" in cmd_lower or "npm i" in cmd_lower:
            if exit_code == 0:
                success_match = [l for l in lines if "Successfully installed" in l or "added" in l or "up to date" in l]
                if success_match:
                    return f"Cài đặt gói thành công: {success_match[-1]}, thưa Ngài."
                return f"Đã hoàn tất cài đặt gói thành công với {line_count} dòng log, thưa Ngài."
            else:
                return f"Cài đặt gói thất bại: {lines[-1]}"

        # Domain Summarizer: Pytest / Unit Test Runner
        if "pytest" in cmd_lower or "python -m unittest" in cmd_lower:
            summary_line = [l for l in lines if "passed" in l or "failed" in l or "error" in l]
            if summary_line:
                return f"Kết quả kiểm thử: {summary_line[-1]}, thưa Ngài."
            return f"Hoàn tất kiểm thử ({line_count} dòng log), thưa Ngài."

        # Domain Summarizer: Netstat
        if "netstat" in cmd_lower:
            return f"Tìm thấy {line_count} kết nối mạng đang hoạt động trên hệ thống, thưa Ngài."

        # Generic Fallback Summarizer for > 10 lines
        head_preview = lines[0] if lines else ""
        tail_preview = lines[-1] if lines else ""
        status_text = "thành công" if exit_code == 0 else f"với mã lỗi {exit_code}"
        return (
            f"Lệnh đã thực thi {status_text} với {line_count} dòng kết quả. "
            f"Bắt đầu: '{head_preview}'. Kết thúc: '{tail_preview}', thưa Ngài."
        )

    # -----------------------------------------------------------------------
    # Main Execution Engine
    # -----------------------------------------------------------------------
    def execute_natural_command(self, query: str, cwd: str | None = None) -> dict[str, Any]:
        """
        Translates NL query, performs destructive safety checks, executes command,
        and returns structured result with Vietnamese summary.
        """
        cmd, category = self.translate_nl_command(query, cwd)
        target_dir = os.path.abspath(cwd or self.default_cwd)

        # Destructive Command Gate
        if self.is_destructive(cmd):
            token = self.safety_gate.request_confirmation(
                action_desc=f"Thực thi lệnh shell: {cmd}",
                payload={"command": cmd, "cwd": target_dir},
            )
            return {
                "success": False,
                "requires_confirmation": True,
                "gated": True,
                "token": token,
                "confirmation_token": token,
                "risk_level": "high",
                "command": cmd,
                "category": category,
                "message": (
                    f"Cảnh báo: Lệnh '{cmd}' chứa thao tác nguy hiểm có thể xóa hoặc thay đổi dữ liệu hệ thống. "
                    f"Vui lòng xác nhận để thực thi. (Mã xác nhận: {token})"
                ),
            }

        # Safe Execution
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=target_dir,
            )
            raw_out = proc.stdout if proc.returncode == 0 else (proc.stderr or proc.stdout)
            summary = self.summarize_output(cmd, raw_out, proc.returncode)

            return {
                "success": proc.returncode == 0,
                "requires_confirmation": False,
                "command": cmd,
                "category": category,
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "summary": summary,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "requires_confirmation": False,
                "command": cmd,
                "category": category,
                "exit_code": -1,
                "stdout": "",
                "stderr": "Lệnh thực thi quá thời gian cho phép (timeout 60s).",
                "summary": "Lệnh đã bị dừng do vượt quá thời gian chờ (60 giây), thưa Ngài.",
            }
        except Exception as e:
            return {
                "success": False,
                "requires_confirmation": False,
                "command": cmd,
                "category": category,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "summary": f"Không thể thực thi lệnh: {e}",
            }
