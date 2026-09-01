param(
    [string]$RepoPath = (Get-Location).Path,
    [switch]$RunTests
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$reportDir = Join-Path $RepoPath "reports"
$reportFile = Join-Path $reportDir "system_diagnostic_$timestamp.txt"

New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

function Write-Report {
    param([string]$Text = "")
    Write-Host $Text
    Add-Content -Path $reportFile -Value $Text -Encoding UTF8
}

function Section {
    param([string]$Title)
    Write-Report ""
    Write-Report ("=" * 70)
    Write-Report $Title
    Write-Report ("=" * 70)
}

function Run-Check {
    param(
        [string]$Name,
        [scriptblock]$Command
    )

    Write-Report ""
    Write-Report "[$Name]"

    try {
        # Out-String ensures Format-List objects are serialized properly
        $output = (& $Command 2>&1) | Out-String

        if ([string]::IsNullOrWhiteSpace($output)) {
            Write-Report "OK - no output"
        }
        else {
            foreach ($line in ($output -split "`r?`n")) {
                Write-Report $line
            }
        }
    }
    catch {
        Write-Report "ERROR: $($_.Exception.Message)"
    }
}

# Python helper: write code to temp .py file then run (avoids here-string SyntaxError)
function Run-Python {
    param([string]$Code)
    $tmp = [System.IO.Path]::GetTempFileName() + ".py"
    [System.IO.File]::WriteAllText($tmp, $Code, [System.Text.Encoding]::UTF8)
    try {
        python $tmp 2>&1
    } finally {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
}

Set-Location $RepoPath

Section "JARVIS SYSTEM DIAGNOSTIC"
Write-Report "Time       : $(Get-Date)"
Write-Report "Repo       : $RepoPath"
Write-Report "Computer   : $env:COMPUTERNAME"
Write-Report "User       : $env:USERNAME"

# ------------------------------------------------------------------
# 1. Windows / Hardware
# ------------------------------------------------------------------

Section "1. WINDOWS / HARDWARE"

Run-Check "Windows" {
    Get-CimInstance Win32_OperatingSystem |
        Select-Object Caption, Version, BuildNumber, OSArchitecture |
        Format-List |
        Out-String
}

Run-Check "CPU" {
    Get-CimInstance Win32_Processor |
        Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed |
        Format-List |
        Out-String
}

Run-Check "RAM" {
    $os = Get-CimInstance Win32_OperatingSystem
    $total = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
    $free  = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
    $used  = [math]::Round($total - $free, 2)
    "Total RAM : $total GB"
    "Used RAM  : $used GB"
    "Free RAM  : $free GB"
}

Run-Check "Disk" {
    Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" |
        ForEach-Object {
            $size = [math]::Round($_.Size / 1GB, 2)
            $free = [math]::Round($_.FreeSpace / 1GB, 2)
            "$($_.DeviceID) Total=$size GB Free=$free GB"
        }
}

# ------------------------------------------------------------------
# 2. GPU / CUDA
# ------------------------------------------------------------------

Section "2. GPU / CUDA"

Run-Check "NVIDIA SMI" {
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        nvidia-smi
    } else {
        "NOT FOUND: nvidia-smi"
    }
}

Run-Check "CTranslate2 CUDA" {
    Run-Python "
try:
    import ctranslate2
    print('ctranslate2 version:', ctranslate2.__version__)
    print('CUDA devices:', ctranslate2.get_cuda_device_count())
except Exception as e:
    print(type(e).__name__ + ':', e)
"
}

# ------------------------------------------------------------------
# 3. Python
# ------------------------------------------------------------------

Section "3. PYTHON"

Run-Check "Python executable" {
    python -c "import sys; print(sys.executable)"
}

Run-Check "Python version + architecture" {
    python -c "import sys,platform; print('Version:', sys.version); print('Arch:', platform.architecture())"
}

Run-Check "pip" {
    python -m pip --version
}

Run-Check "Important Python packages" {
    Run-Python "
import importlib
packages = [
    'numpy', 'pytest', 'requests', 'faster_whisper', 'ctranslate2',
    'sounddevice', 'soundfile', 'psutil', 'keyring', 'pytest_env', 'pytest_asyncio',
]
for name in packages:
    try:
        m = importlib.import_module(name)
        version = getattr(m, '__version__', 'unknown')
        print(f'OK      {name:<25} {version}')
    except Exception as e:
        print(f'MISSING {name:<25} {type(e).__name__}: {e}')
"
}

# ------------------------------------------------------------------
# 4. JARVIS
# ------------------------------------------------------------------

Section "4. JARVIS IMPORT CHECK"

Run-Check "Import jarvis" {
    python -c "import jarvis; print('jarvis.__version__ =', jarvis.__version__)"
}

Run-Check "Import STT engine" {
    Run-Python "
from jarvis.stt.engine import FasterWhisperSTT, FASTER_WHISPER_AVAILABLE
print('FasterWhisperSTT import: OK')
print('FASTER_WHISPER_AVAILABLE:', FASTER_WHISPER_AVAILABLE)
"
}

Run-Check "SecretsManager (presence only - no values printed)" {
    Run-Python "
from jarvis.security.secrets import get_secret, _keyring_available
print('keyring available:', _keyring_available())
for key in ['OPENAI_API_KEY', 'GEMINI_API_KEY', 'TELEGRAM_BOT_TOKEN', 'WEATHER_API_KEY']:
    val = get_secret(key)
    status = 'SET' if val else 'NOT SET'
    print(f'  {key}: {status}')
"
}

Run-Check "Compile production modules" {
    python -m py_compile `
        jarvis/stt/engine.py `
        jarvis/llm/router.py `
        jarvis/core/app.py `
        jarvis/audio/wake_word.py `
        jarvis/utils/subprocess_utils.py `
        jarvis/__init__.py
}

# ------------------------------------------------------------------
# 5. Git
# ------------------------------------------------------------------

Section "5. GIT STATE"

Run-Check "Git version" { git --version }
Run-Check "Current branch" { git branch --show-current }
Run-Check "Git status" { git status --short }
Run-Check "Latest commits" { git log -5 --oneline --decorate }
Run-Check "Remote" { git remote -v }

# ------------------------------------------------------------------
# 6. Environment Variables (presence check only)
# ------------------------------------------------------------------

Section "6. ENVIRONMENT VARIABLES (presence check - values never printed)"

$secretVars = @(
    "OPENAI_API_KEY",
    "JARVIS_OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "DISCORD_BOT_TOKEN",
    "OPENWEATHER_API_KEY",
    "TELEGRAM_CHAT_ID"
)

foreach ($name in $secretVars) {
    # Check Process, then User, then Machine scope
    $val = [Environment]::GetEnvironmentVariable($name, "Process")
    if ([string]::IsNullOrWhiteSpace($val)) {
        $val = [Environment]::GetEnvironmentVariable($name, "User")
    }
    if ([string]::IsNullOrWhiteSpace($val)) {
        $val = [Environment]::GetEnvironmentVariable($name, "Machine")
    }

    if ([string]::IsNullOrWhiteSpace($val)) {
        Write-Report "$name : NOT SET (checked Process + User + Machine)"
    } else {
        Write-Report "$name : SET"
    }
}

# ------------------------------------------------------------------
# 7. Error Log Scan
# ------------------------------------------------------------------

Section "7. ERROR LOG SCAN"

$errorPattern = "ERROR|CRITICAL|Traceback|Exception|Fatal"
$noisePattern = "\[INTERACTION\].*STATUS: failed"

$logFolder = Join-Path $RepoPath "logs"
Write-Report ""
Write-Report "Scanning: $logFolder"

if (-not (Test-Path $logFolder)) {
    Write-Report "Directory not found."
} else {
    $files = Get-ChildItem $logFolder -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in ".log", ".txt", ".out", ".err" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 10

    foreach ($file in $files) {
        $errorLines = Select-String `
            -Path $file.FullName `
            -Pattern $errorPattern `
            -CaseSensitive:$false `
            -ErrorAction SilentlyContinue |
            Where-Object { $_.Line -notmatch $noisePattern } |
            Select-Object -Last 15

        if ($errorLines) {
            Write-Report ""
            Write-Report "ERRORS in: $($file.Name)"
            foreach ($m in $errorLines) {
                Write-Report "  L$($m.LineNumber): $($m.Line.Trim())"
            }
        } else {
            Write-Report "  $($file.Name) -- no real errors found"
        }
    }

    # Summarize INTERACTION failures separately (informational)
    $logFile = Join-Path $logFolder "jarvis.log"
    if (Test-Path $logFile) {
        Write-Report ""
        $failCount = (Select-String -Path $logFile -Pattern "STATUS: failed" -ErrorAction SilentlyContinue | Measure-Object).Count
        Write-Report "INTERACTION STATUS:failed total: $failCount lines in jarvis.log"
        Write-Report "(These are user commands JARVIS could not route. See CHANGELOG for known fixes.)"

        $recentFails = Select-String -Path $logFile -Pattern "STATUS: failed" -ErrorAction SilentlyContinue |
            Select-Object -Last 100 |
            ForEach-Object {
                if ($_.Line -match "INPUT: ([^|]+)") { $Matches[1].Trim() }
            } |
            Sort-Object -Unique |
            Select-Object -First 10

        Write-Report "Recent unique failed commands:"
        foreach ($cmd in $recentFails) {
            Write-Report "  - $cmd"
        }
    }
}

# ------------------------------------------------------------------
# 8. Optional Tests
# ------------------------------------------------------------------

if ($RunTests) {
    Section "8. OPTIONAL TESTS"

    Run-Check "STT unit tests" {
        python -m pytest tests/unit/test_stt_engine.py -q --tb=short
    }

    Run-Check "Adversarial M1 router tests" {
        python -m pytest tests/test_adversarial_m1_intent_router.py -q --tb=short
    }

    Run-Check "STT eval helper tests" {
        if (Test-Path "tests/unit/test_stt_eval_failure_decomposition.py") {
            python -m pytest tests/unit/test_stt_eval_failure_decomposition.py -q --tb=short
        } else {
            "Test file not present on this branch."
        }
    }
}

# ------------------------------------------------------------------
# 9. Quick Diagnosis
# ------------------------------------------------------------------

Section "9. QUICK DIAGNOSIS"

$issues = @()

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    $issues += "Python not found in PATH."
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    $issues += "Git not found in PATH."
}

if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    $issues += "nvidia-smi not found. NVIDIA driver/CUDA GPU unavailable or not in PATH."
}

# venv check
if (-not $env:VIRTUAL_ENV) {
    $issues += "Not running inside a virtual environment (.venv). Activate before running tests."
}

# RAM check
$osInfo = Get-CimInstance Win32_OperatingSystem
$freeGb = [math]::Round($osInfo.FreePhysicalMemory / 1MB, 2)
if ($freeGb -lt 2.0) {
    $issues += "Low RAM: only $freeGb GB free. Whisper large-v3 requires ~3-4 GB."
}

if ($issues.Count -eq 0) {
    Write-Report "No obvious system-level problem detected."
    Write-Report "Check sections above for Python/import/log-specific errors."
} else {
    foreach ($issue in $issues) {
        Write-Report "WARNING: $issue"
    }
}

Section "DONE"
Write-Report "Report saved to: $reportFile"

Write-Host ""
Write-Host "============================================"
Write-Host "Diagnostic complete"
Write-Host "Report: $reportFile"
Write-Host "============================================"
