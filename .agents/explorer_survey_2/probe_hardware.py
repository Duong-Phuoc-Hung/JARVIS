import sys
import subprocess
import json
import sounddevice as sd
import ctypes
from ctypes import wintypes

print("=== SOUNDDEVICE QUERY DEVICES ===")
try:
    devices = sd.query_devices()
    print(f"Total audio devices: {len(devices)}")
    default_input = sd.default.device[0]
    default_output = sd.default.device[1]
    print(f"Default input index: {default_input}, Default output index: {default_output}")
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] > 0 or dev['max_output_channels'] > 0:
            print(f"  [{i}] {dev['name']} (In: {dev['max_input_channels']}, Out: {dev['max_output_channels']})")
except Exception as e:
    print(f"sounddevice query error: {e}")

print("\n=== HARDWARE DIAGNOSTICS VIA POWERSHELL CIM ===")
ps_script = """
$cpu = Get-CimInstance Win32_Processor | Select-Object -Property Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed, LoadPercentage
$ram = Get-CimInstance Win32_OperatingSystem | Select-Object -Property TotalVisibleMemorySize, FreePhysicalMemory
$disks = Get-CimInstance Win32_LogicalDisk | Select-Object -Property DeviceID, VolumeName, Size, FreeSpace, FileSystem
$battery = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue | Select-Object -Property EstimatedChargeRemaining, BatteryStatus

[PSCustomObject]@{
    CPU = $cpu
    RAM = $ram
    Disks = $disks
    Battery = $battery
} | ConvertTo-Json -Depth 3
"""
try:
    res = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True, text=True, timeout=10
    )
    if res.returncode == 0:
        data = json.loads(res.stdout)
        print("PowerShell CIM Hardware Query: SUCCESS")
        print("CPU Data:", data.get("CPU"))
        print("RAM Data:", data.get("RAM"))
        print("Disks Data:", data.get("Disks"))
    else:
        print("PowerShell CIM failed:", res.stderr)
except Exception as e:
    print("PowerShell CIM error:", e)

print("\n=== POWERSHELL PROCESS LIST (NOT RESPONDING / MEMORY) ===")
ps_proc_script = """
Get-Process | Where-Object { $_.Responding -eq $false -or $_.WorkingSet64 -gt 100MB } | Select-Object -First 10 -Property Id, ProcessName, Responding, WorkingSet64 | ConvertTo-Json
"""
try:
    res = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_proc_script],
        capture_output=True, text=True, timeout=10
    )
    if res.returncode == 0:
        print("Process query SUCCESS (sample):")
        print(res.stdout[:500])
    else:
        print("Process query failed:", res.stderr)
except Exception as e:
    print("Process query error:", e)

print("\n=== CTYPES WINDOWS API CAPABILITIES ===")
# Test user32 LockWorkStation (R12 lock screen)
try:
    user32 = ctypes.windll.user32
    print("LockWorkStation function available in user32:", hasattr(user32, "LockWorkStation"))
    print("EnumWindows available:", hasattr(user32, "EnumWindows"))
    print("GetWindowTextW available:", hasattr(user32, "GetWindowTextW"))
    print("PostMessageW available:", hasattr(user32, "PostMessageW"))
    print("SetWindowPos available:", hasattr(user32, "SetWindowPos"))
except Exception as e:
    print("ctypes test error:", e)

print("\n=== SAPI TTS VIA POWERSHELL SPEED / LATENCY ===")
import time
t0 = time.perf_counter()
try:
    # Test async or non-blocking powershell TTS
    tts_test = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Add-Type -AssemblyName System.Speech; $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; $synth.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }"],
        capture_output=True, text=True, timeout=10
    )
    t1 = time.perf_counter()
    print(f"Installed SAPI Voices (probed in {(t1-t0)*1000:.1f}ms):")
    for line in tts_test.stdout.strip().splitlines():
        print(f"  - {line}")
except Exception as e:
    print("SAPI voices error:", e)
