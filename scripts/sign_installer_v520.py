#!/usr/bin/env python3
"""
scripts/sign_installer_v520.py
==============================
Signs dist/installer/JARVIS_Setup_v5.2.0.exe with PowerShell Authenticode
and computes SHA-256 checksum file.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
INSTALLER = ROOT / "dist" / "installer" / "JARVIS_Setup_v5.2.0.exe"
SHA256_FILE = ROOT / "dist" / "installer" / "JARVIS_Setup_v5.2.0.exe.sha256"

def main() -> int:
    if not INSTALLER.exists():
        print(f"ERROR: Installer binary not found at {INSTALLER}", file=sys.stderr)
        return 1

    size_bytes = INSTALLER.stat().st_size
    print(f"Found installer: {INSTALLER} ({size_bytes:,} bytes)")

    ps_script = f"""
$ErrorActionPreference = 'Stop'
Write-Host "=== 1. Creating Self-Signed Code Signing Certificate ==="
$cert = New-SelfSignedCertificate `
    -Type CodeSigningCert `
    -Subject "CN=JARVIS Release v5.2.0" `
    -CertStoreLocation "Cert:\\CurrentUser\\My" `
    -KeyLength 2048 `
    -HashAlgorithm SHA256 `
    -NotAfter (Get-Date).AddYears(5)
Write-Host "Thumbprint: $($cert.Thumbprint)"
Write-Host "Subject:    $($cert.Subject)"

Write-Host "`n=== 2. Signing Installer Binary with Set-AuthenticodeSignature ==="
$sig = Set-AuthenticodeSignature -FilePath "{INSTALLER}" -Certificate $cert -HashAlgorithm SHA256
Write-Host "Set-AuthenticodeSignature Status: $($sig.Status)"
Write-Host "Set-AuthenticodeSignature StatusMessage: $($sig.StatusMessage)"

Write-Host "`n=== 3. Verifying Authenticode Signature ==="
$verify = Get-AuthenticodeSignature -FilePath "{INSTALLER}"
Write-Host "Verification Status:        $($verify.Status)"
Write-Host "Verification StatusMessage: $($verify.StatusMessage)"
Write-Host "Signer Subject:             $($verify.SignerCertificate.Subject)"
Write-Host "Signer Thumbprint:          $($verify.SignerCertificate.Thumbprint)"

if ($verify.Status -eq 'NotSigned') {{
    Write-Error "Signature verification failed: Status is NotSigned"
    exit 2
}}
exit 0
"""

    print("\nExecuting PowerShell Authenticode signing...")
    _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
        capture_output=True,
        text=True,
        creationflags=_cflags,
    )
    print("--- PowerShell Output ---")
    print(proc.stdout)
    if proc.stderr:
        print("--- PowerShell Stderr ---")
        print(proc.stderr)

    if proc.returncode != 0:
        print(f"ERROR: PowerShell signing failed with exit code {proc.returncode}", file=sys.stderr)
        return proc.returncode

    # Verify post-sign file size
    signed_size = INSTALLER.stat().st_size
    print(f"\nSigned installer size: {signed_size:,} bytes (delta: +{signed_size - size_bytes} bytes)")

    # Compute SHA-256
    print("\nComputing SHA-256 checksum...")
    sha256 = hashlib.sha256()
    with open(INSTALLER, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    digest = sha256.hexdigest().lower()
    print(f"SHA-256: {digest}")

    # Write .sha256 file
    # Standard format: "<hash> *<filename>" or "<hash>  <filename>"
    content = f"{digest}  JARVIS_Setup_v5.2.0.exe\n"
    SHA256_FILE.write_text(content, encoding="utf-8")
    print(f"Wrote checksum to: {SHA256_FILE}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
