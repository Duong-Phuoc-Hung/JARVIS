# Manual Signing Guide for JARVIS.exe (Option A)

This operational guide describes the manual Authenticode code signing procedure for `JARVIS.exe` using the existing **SignPath Foundation** account. This workflow provides an interim, zero-subscription path to produce an authentic, CA-backed Authenticode signature via interactive web upload.

---

## 1. Context & Operational Parameters

- **Organization**: `14be0b5a-511d-4104-8b35-c23386fd2ba0`
- **Project**: `Jarvis`
- **Artifact Configuration**: `initial` (PE Authenticode signing for `JARVIS.exe`)
- **Signing Policy**: `Jarvis_Test_Signing`
- **Web Console URL**: `https://app.signpath.io`
- **Estimated Duration**: **5–10 minutes** (guaranteed **≤ 15 minutes** per release)
- **Applicability**: Release engineers or repository maintainers with authorized SignPath web access

---

## 2. Prerequisites

Before starting the manual signing process, verify the following prerequisites:

1. **SignPath Account Access**: You have active login credentials at `https://app.signpath.io` with submitter permissions in organization `14be0b5a-511d-4104-8b35-c23386fd2ba0`.
2. **Completed GitHub Actions Run**: A tagged release build workflow on GitHub Actions has completed successfully and produced the `jarvis-unsigned-exe` artifact.
3. **Local PowerShell Environment**: Windows PowerShell 5.1+ or PowerShell 7+ is available locally for signature verification.
4. **Archiving Utility**: A standard zip archiving tool (such as PowerShell's `Compress-Archive` or 7-Zip) is installed.

---

## 3. Step-by-Step Procedure

Follow these 6 sequential steps to manually sign the release binary:

1. **Download the Unsigned Artifact**: Navigate to the GitHub Actions tab in the repository and select the release workflow run for the target tag. Under the Run summary section, download the `jarvis-unsigned-exe` artifact archive to your workstation. Extract `JARVIS.exe` from the downloaded archive into a clean local staging directory.

2. **Access the SignPath Web Console**: Log in to your SignPath account at `https://app.signpath.io` using your authorized project credentials. Select Organization `14be0b5a-511d-4104-8b35-c23386fd2ba0` and open the `Jarvis` project dashboard. Navigate to the Signing Requests tab and click the New signing request button.

3. **Submit the Executable for Signing**: Select the artifact configuration `initial` and choose signing policy `Jarvis_Test_Signing` from the options. Upload the extracted `JARVIS.exe` binary, ensuring that the filename remains unaltered. Click the Submit request button to send the binary for signing.

4. **Wait for Processing and Download Signed Executable**: Monitor the signing request queue until the status transitions from Processing to Completed. Click the download button on the request details page to save the signed executable package. Extract the signed `JARVIS.exe` from the returned package to your local staging directory.

5. **Validate Signature in PowerShell**: Open PowerShell in your staging folder and run the command `Get-AuthenticodeSignature .\JARVIS.exe`. Verify that the output displays Status as Valid and shows the certificate details. Confirm that the signing timestamp and certificate subject correspond to your SignPath configuration.

6. **Repack Archive and Attach to GitHub Release**: Compress the signed `JARVIS.exe` into `JARVIS_v<version>_windows_x64.zip` using your preferred archive tool. Navigate to the GitHub Releases page for the release tag and enter the release editor. Upload and replace the existing archive with your signed zip and attach the signed `JARVIS.exe` directly.

---

## 4. Verification & Validation Reference

### PowerShell Command

To confirm that the binary carries a valid Authenticode signature, execute:

```powershell
Get-AuthenticodeSignature .\JARVIS.exe | Format-List Status, StatusMessage, SignerCertificate, TimeStamperCertificate
```

### Expected Output

```text
Status                : Valid
StatusMessage         : Signature verified.
SignerCertificate     : [Subject]
                          CN=...
                        [Issuer]
                          CN=...
TimeStamperCertificate: [Subject]
                          CN=...
```

---

## 5. Troubleshooting & Operational Notes

| Issue | Cause | Resolution |
|---|---|---|
| **Artifact Name Mismatch** | Uploaded file was renamed (e.g., `JARVIS_v5.2.0.exe`). | The `initial` artifact configuration strictly expects `JARVIS.exe`. Rename file to `JARVIS.exe` before uploading. |
| **Pending Multi-Person Approval** | Signing policy requires peer approval before execution. | Notify an authorized approver on the team to approve the request in the SignPath web console. |
| **GitHub Release Asset Conflict** | An asset with the same name already exists on GitHub Releases. | Delete the older unsigned asset or click "Replace existing asset" when saving the release edit. |
| **PowerShell `Status: NotSigned`** | Extracted the original unsigned file instead of the signed package. | Re-download the output package from SignPath and ensure the signed executable is extracted. |
