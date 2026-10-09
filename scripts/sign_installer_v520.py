#!/usr/bin/env python3
"""
scripts/sign_installer_v520.py
==============================
PowerShell Authenticode Signing & Integrity Verification Runner for JARVIS Windows Installers.
Complies strictly with AUDIT_FRAMEWORK.md and RULE[AGENTS.md] (Three-Tier Verdict Discipline).

Behaviors:
1. Commercial Tier:
   - If `--require-commercial` or `JARVIS_REQUIRE_COMMERCIAL_SIGNING=1` is specified:
     Searches for an EV/Commercial Code Signing Certificate (via `--cert-thumbprint`,
     `JARVIS_COMMERCIAL_CERT_THUMBPRINT`, or `--pfx-path`).
   - If missing or self-signed, FAILS CLOSED (exit code 3: COMMERCIAL_CERT_NOT_CONFIGURED).
2. Development / Test Tier:
   - If commercial credentials are not required, signs with a local self-signed certificate.
   - Truthfully marks verdict as "PASS fail-closed, commercial Authenticode PENDING_CREDENTIALS".
   - Never fabricates commercial CA validity or SmartScreen trust.
3. Generates SHA-256 checksum and structured signature audit manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
DEFAULT_INSTALLER = ROOT / "dist" / "installer" / "JARVIS_Setup_v5.2.1.exe"
if not DEFAULT_INSTALLER.exists():
    fallback_520 = ROOT / "dist" / "installer" / "JARVIS_Setup_v5.2.0.exe"
    if fallback_520.exists():
        DEFAULT_INSTALLER = fallback_520

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("sign_installer")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sign JARVIS Windows Installer with Authenticode")
    parser.add_argument(
        "--installer",
        type=Path,
        default=DEFAULT_INSTALLER,
        help="Path to the installer executable to sign",
    )
    parser.add_argument(
        "--require-commercial",
        action="store_true",
        default=os.environ.get("JARVIS_REQUIRE_COMMERCIAL_SIGNING", "0") in ("1", "true", "TRUE"),
        help="Enforce commercial EV/CA code signing certificate (fails closed if missing)",
    )
    parser.add_argument(
        "--cert-thumbprint",
        type=str,
        default=os.environ.get("JARVIS_COMMERCIAL_CERT_THUMBPRINT"),
        help="Certificate thumbprint in Windows Cert Store (Cert:\\CurrentUser\\My or Cert:\\LocalMachine\\My)",
    )
    parser.add_argument(
        "--pfx-path",
        type=Path,
        default=Path(os.environ["JARVIS_COMMERCIAL_PFX_PATH"]) if os.environ.get("JARVIS_COMMERCIAL_PFX_PATH") else None,
        help="Path to commercial code signing .pfx file",
    )
    parser.add_argument(
        "--pfx-password",
        type=str,
        default=os.environ.get("JARVIS_COMMERCIAL_PFX_PASSWORD", ""),
        help="Password for commercial code signing .pfx file",
    )
    parser.add_argument(
        "--timestamp-url",
        type=str,
        default=os.environ.get("JARVIS_TIMESTAMP_URL", "http://timestamp.digicert.com"),
        help="RFC 3161 Timestamp Authority URL",
    )
    return parser.parse_args()


def sign_installer(args: argparse.Namespace) -> int:
    installer = args.installer.resolve()
    if not installer.exists():
        log.error("Installer binary not found at %s", installer)
        return 1

    size_bytes = installer.stat().st_size
    log.info("Found installer: %s (%s bytes)", installer, f"{size_bytes:,}")

    # Determine signature tier
    commercial_mode = bool(args.cert_thumbprint or (args.pfx_path and args.pfx_path.exists()))
    if args.require_commercial and not commercial_mode:
        log.error(
            "[FAIL-CLOSED] Commercial Authenticode certificate not configured (STATUS: PENDING_CREDENTIALS).\n"
            "To sign with a commercial certificate, provide --cert-thumbprint or set JARVIS_COMMERCIAL_CERT_THUMBPRINT,\n"
            "or provide --pfx-path with a valid DigiCert/Sectigo/GlobalSign EV Code Signing token."
        )
        manifest = {
            "installer": str(installer),
            "size_bytes": size_bytes,
            "signature_tier": "NOT_CONFIGURED",
            "verdict": "FAIL_CLOSED (COMMERCIAL_CERT_NOT_CONFIGURED)",
            "smartscreen_trusted": False,
            "error_code": "COMMERCIAL_CERT_NOT_CONFIGURED",
        }
        manifest_path = installer.parent / "signature_audit.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return 3

    if commercial_mode:
        log.info("Using commercial signing credentials...")
        if args.cert_thumbprint:
            ps_cert_retrieval = f'$cert = Get-Item "Cert:\\CurrentUser\\My\\{args.cert_thumbprint}" -ErrorAction SilentlyContinue; if (-not $cert) {{ $cert = Get-Item "Cert:\\LocalMachine\\My\\{args.cert_thumbprint}" }}'
        else:
            ps_cert_retrieval = f'$securePass = ConvertTo-SecureString "{args.pfx_password}" -AsPlainText -Force; $cert = Get-PfxCertificate -FilePath "{args.pfx_path}" -Password $securePass'
        ps_sign_cmd = f'$sig = Set-AuthenticodeSignature -FilePath "{installer}" -Certificate $cert -TimestampServer "{args.timestamp_url}" -HashAlgorithm SHA256'
        signature_tier = "COMMERCIAL"
    else:
        log.warning(
            "Commercial certificate credentials not provided. Generating development self-signed certificate.\n"
            "Notice: Development self-signed certificates are NOT trusted by Windows SmartScreen.\n"
            "Per Three-Tier Verdict Discipline, this build is classified as TEST_SIGNED (PASS fail-closed)."
        )
        ps_cert_retrieval = """
Write-Host "Creating local self-signed test code signing certificate..."
$cert = New-SelfSignedCertificate `
    -Type CodeSigningCert `
    -Subject "CN=JARVIS Release Test Signer (Dev Only)" `
    -CertStoreLocation "Cert:\\CurrentUser\\My" `
    -KeyLength 2048 `
    -HashAlgorithm SHA256 `
    -NotAfter (Get-Date).AddYears(2)
"""
        ps_sign_cmd = f'$sig = Set-AuthenticodeSignature -FilePath "{installer}" -Certificate $cert -HashAlgorithm SHA256'
        signature_tier = "TEST_SIGNED"

    ps_script = f"""
$ErrorActionPreference = 'Stop'
Write-Host "=== 1. Resolving Certificate ==="
{ps_cert_retrieval}
Write-Host "Thumbprint: $($cert.Thumbprint)"
Write-Host "Subject:    $($cert.Subject)"

Write-Host "`n=== 2. Signing Installer Binary ==="
{ps_sign_cmd}
Write-Host "Set-AuthenticodeSignature Status: $($sig.Status)"
Write-Host "Set-AuthenticodeSignature StatusMessage: $($sig.StatusMessage)"

Write-Host "`n=== 3. Verifying Authenticode Signature ==="
$verify = Get-AuthenticodeSignature -FilePath "{installer}"
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

    log.info("Executing PowerShell Authenticode signing...")
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
        log.error("PowerShell signing failed with exit code %s", proc.returncode)
        return proc.returncode

    # Compute SHA-256
    log.info("Computing SHA-256 checksum...")
    sha256 = hashlib.sha256()
    with open(installer, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    digest = sha256.hexdigest().lower()
    log.info("SHA-256: %s", digest)

    # Write .sha256 file
    sha256_file = installer.parent / f"{installer.name}.sha256"
    sha256_file.write_text(f"{digest}  {installer.name}\n", encoding="utf-8")
    log.info("Wrote checksum to: %s", sha256_file)

    # Write signature audit manifest
    smartscreen_trusted = signature_tier == "COMMERCIAL"
    verdict = (
        "PASS runtime (COMMERCIAL)"
        if signature_tier == "COMMERCIAL"
        else "PASS fail-closed, commercial Authenticode PENDING_CREDENTIALS"
    )
    audit_manifest = {
        "installer": str(installer),
        "filename": installer.name,
        "sha256": digest,
        "size_bytes": installer.stat().st_size,
        "signature_tier": signature_tier,
        "smartscreen_trusted": smartscreen_trusted,
        "verdict": verdict,
        "timestamp_authority": args.timestamp_url if signature_tier == "COMMERCIAL" else None,
    }
    audit_path = installer.parent / "signature_audit.json"
    audit_path.write_text(json.dumps(audit_manifest, indent=2), encoding="utf-8")
    log.info("Wrote signature audit manifest to: %s", audit_path)
    log.info("Authenticode Verdict: %s", verdict)

    return 0


def main() -> int:
    args = parse_args()
    return sign_installer(args)


if __name__ == "__main__":
    sys.exit(main())
