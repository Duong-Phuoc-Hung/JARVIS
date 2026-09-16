# Production Code Signing Upgrade Roadmap (Option B)

## 1. Executive Summary & Context

This document outlines the technical architecture, financial investment, and CI/CD integration steps required to upgrade **JARVIS** from interim code signing approaches to automated, globally trusted production code signing in GitHub Actions.

Currently, the release pipeline (`.github/workflows/release.yml`) builds `JARVIS.exe` using PyInstaller on `windows-latest`. However, due to architectural restrictions in free-tier cloud signing programs, automated CI-based production signing has been blocked. This document details the root cause of the SignPath Foundation limitation, assesses the cost of upgrading SignPath, evaluates three industry-standard commercial alternatives (Microsoft Azure Trusted Signing, DigiCert KeyLocker, and Sectigo / SSL.com eSigner), provides a side-by-side comparison matrix, and specifies the exact changes required in `.github/workflows/release.yml`.

---

## 2. Root Cause Analysis: SignPath Foundation Blocker

JARVIS previously configured an open-source SignPath Foundation account:
- **Organization ID**: `14be0b5a-511d-4104-8b35-c23386fd2ba0`
- **Project Slug**: `Jarvis`
- **Signing Policy**: `Jarvis_Test_Signing`
- **Artifact Configuration**: `initial`

During CI integration trials (`v5.2.0-beta.1` through `v5.2.0-beta.3`), automated CI signing failed due to the following structural limitations:

1. **Connector Endpoint Restriction**: The SignPath GitHub Actions connector (`githubactions.connectors.signpath.io`) enforces strict validation against policy-defined Trusted Build Systems. On the SignPath Foundation tier, configuring custom GitHub Actions Trusted Build Systems via `pipelinePolicies` is restricted.
2. **REST API Endpoint Disabled (HTTP 404)**: Attempting to invoke the SignPath REST API directly (`POST https://app.signpath.io/api/v1/{organization_id}/signing-requests`) using a CI User API token returns `HTTP 404 Not Found`. SignPath confirmed that programmatic submission via REST API is deliberately unavailable on Foundation accounts to enforce interactive human review and prevent automated abuse.
3. **CA/Browser Forum Hardware Mandate**: As of June 1, 2023, the CA/Browser Forum mandates that private keys for all code signing certificates (both Standard OV and Extended Validation EV) must be stored on FIPS 140-2 Level 2 or Common Criteria EAL 4+ hardware cryptographic modules. Traditional exportable PFX files cannot be purchased from commercial CAs for CI use, necessitating a Cloud HSM or cloud-native signing service.

Consequently, unattended CI signing cannot function on the SignPath Foundation free tier. Automated signing requires either upgrading to a commercial SignPath tier or adopting a cloud signing platform.

---

## 3. Commercial Upgrade Option: SignPath Paid Tier

SignPath provides dedicated enterprise tiers that support unattended CI/CD automation.

### Specifications & Pricing
- **Required Tier**: **SignPath Team** or **SignPath Business**
- **Estimated Cost**: **~€150–€250/month (~€1,800–€3,000/year)**, billed annually based on project count and signing volume.
- **Certificate Model**: Bring-Your-Own-Certificate (BYOC) from a commercial CA (e.g., DigiCert or Sectigo stored in an Azure Key Vault or AWS CloudHSM), or a managed SignPath certificate.

### Setup & Implementation Steps
1. **Commercial Contract**: Upgrade the existing organization `14be0b5a-511d-4104-8b35-c23386fd2ba0` from Foundation to Team/Business tier.
2. **Configure Trusted Build Systems**: In the SignPath web portal, navigate to the `Jarvis` project signing policy and bind the GitHub Actions repository (`Duong-Phuoc-Hung/JARVIS`) with required branch filters (`refs/heads/main`, `refs/tags/v*`).
3. **Connect Pipeline**: Re-enable the GitHub Actions connector `SignPath/github-action-submit-signing-request@v1` in `release.yml` using the organization CI user token (`SIGNPATH_API_TOKEN`).

---

## 4. Industry-Standard Commercial Alternatives

### Alternative 1: Microsoft Azure Trusted Signing (Recommended)

Microsoft **Azure Trusted Signing** (formerly known as Azure Code Signing / ACS) is a cloud-native service built directly into Azure. It provides FIPS 140-2 Level 2 Cloud HSM certificate generation and signing without requiring hardware tokens or separate CA contracts. Certificates issued under Trusted Signing chain up to Microsoft's root CA and are natively trusted by Windows Defender SmartScreen.

- **Estimated Cost**: **$9.99/month (~$120/year)** for the Basic tier. Over 90% cheaper than traditional commercial CAs.
- **Trust Level**: Full Windows Authenticode and SmartScreen reputation building.
- **Key Storage**: Cloud HSM managed by Microsoft (compliant with CA/B Forum regulations).

#### Prerequisites & Setup
1. **Azure Subscription & Entra ID**: An active Azure subscription linked to an Entra ID (Azure AD) tenant.
2. **Identity Validation**: Navigate to the Azure Portal and search for **Trusted Signing Accounts**. Submit organizational identity validation (business registration, D-U-N-S number, and domain ownership). Approval typically completes within 1–3 business days.
3. **Certificate Profile**: Create a **Certificate Profile** under the Trusted Signing Account (e.g., `Jarvis_Production_Profile`) selecting `Public Trust`.
4. **App Registration (OIDC)**: Register an application in Entra ID, configure Federated Credentials for GitHub Actions (`repo:Duong-Phuoc-Hung/JARVIS:ref:refs/tags/*`), and assign the role `Trusted Signing Certificate Profile Signer` to the service principal.

#### GitHub Actions Workflow Snippet

```yaml
    - name: Azure Login via OIDC
      uses: azure/login@v3
      with:
        client-id: ${{ secrets.AZURE_CLIENT_ID }}
        tenant-id: ${{ secrets.AZURE_TENANT_ID }}
        subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

    - name: Sign Executable via Azure Trusted Signing
      uses: azure/artifact-signing-action@v2
      with:
        endpoint: 'https://eus.codesigning.azure.net/'
        signing-account-name: ${{ secrets.AZURE_SIGNING_ACCOUNT_NAME }}
        certificate-profile-name: ${{ secrets.AZURE_CERTIFICATE_PROFILE_NAME }}
        files-folder: 'dist'
        files-folder-filter: 'exe'

    - name: Verify Authenticode Signature
      shell: pwsh
      run: |
        $sig = Get-AuthenticodeSignature .\dist\JARVIS.exe
        Write-Host "Signature Status: $($sig.Status)"
        Write-Host "Signer Subject: $($sig.SignerCertificate.Subject)"
        if ($sig.Status -ne "Valid") {
          Write-Error "Binary signature verification failed!"
          exit 1
        }
```

---

### Alternative 2: DigiCert KeyLocker / Software Trust Manager

DigiCert is the enterprise market leader in digital trust. **DigiCert KeyLocker** (part of DigiCert ONE Software Trust Manager) provides cloud-hosted key storage for Extended Validation (EV) and Organization Validation (OV) code signing certificates.

- **Estimated Cost**: **~$1,000+/year (~$83/month)** per certificate.
- **Trust Level**: Immediate SmartScreen reputation with EV certificates; industry standard for enterprise software distribution.
- **Key Storage**: FIPS 140-2 Level 3 Cloud HSM managed by DigiCert.

#### Prerequisites & Setup
1. **CertCentral / DigiCert ONE Account**: Purchase a DigiCert Code Signing certificate with KeyLocker storage.
2. **Identity Verification**: Complete DigiCert organization validation and EV vetting (phone verification, business registry verification).
3. **Client Configuration**: Generate an API token in Software Trust Manager and register a client authentication certificate.
4. **Tooling**: Install the DigiCert `smctl` (Software Trust Manager CLI) on the runner or use the official GitHub Action.

#### GitHub Actions Workflow Snippet

```yaml
    - name: Setup DigiCert Software Trust Manager
      uses: digicert/ssm-code-signing@v1
      with:
        certificate: ${{ secrets.SM_CLIENT_CERT_BASE64 }}
        certificate-password: ${{ secrets.SM_CLIENT_CERT_PASSWORD }}
        api-key: ${{ secrets.SM_API_KEY }}

    - name: Sign JARVIS.exe with DigiCert smctl
      shell: pwsh
      run: |
        smctl sign --keypair-alias "${{ secrets.SM_KEYPAIR_ALIAS }}" `
                   --input "dist/JARVIS.exe" `
                   --digest-algorithm SHA256
```

---

### Alternative 3: Sectigo / SSL.com eSigner with Cloud HSM

Sectigo and SSL.com offer competitive commercial certificates paired with cloud signing services (such as SSL.com eSigner or Azure Key Vault HSM).

- **Estimated Cost**: **~$250–$500/year** for the certificate + **~$20/month (~$240/year)** for cloud signing tier = **~$490–$740/year total**.
- **Trust Level**: Full Windows Authenticode trust; builds SmartScreen reputation over time.
- **Key Storage**: Cloud HSM or eSigner remote signing service.

#### Prerequisites & Setup
1. **Order Certificate**: Purchase an OV or EV code signing certificate from Sectigo or SSL.com.
2. **eSigner Enrollment**: Enroll the order into the SSL.com eSigner remote signing service.
3. **Integration**: Utilize the `CodeSignTool` CLI container or GitHub Action (`sslcom/actions-codesigner@v1`) with TOTP / API secret authentication.

---

## 5. Side-by-Side Comparison Matrix

| Criteria | SignPath Commercial | Azure Trusted Signing | DigiCert KeyLocker | Sectigo / SSL.com eSigner |
|---|---|---|---|---|
| **Annual Cost** | ~€1,800–€3,000/yr | **~$120/yr ($9.99/mo)** | ~$1,000+/yr | ~$490–$740/yr |
| **Windows SmartScreen Trust** | High (with commercial cert) | **Instant / High (Microsoft Root)** | Instant (with EV cert) | High (with EV cert) |
| **Key Storage Model** | Cloud HSM (BYOC or managed) | **Microsoft Cloud HSM (FIPS 140-2 L2)** | DigiCert ONE HSM (FIPS 140-2 L3) | eSigner Cloud HSM |
| **GitHub Actions Support** | Native connector action | **Official `azure/artifact-signing-action`** | Official `smctl` / SSM action | Official `CodeSignTool` action |
| **Authentication in CI** | Long-lived API Token | **Passwordless OIDC Federated Credentials** | API Token + Client P12 | Username, Password, TOTP Secret |
| **Identity Vetting Time** | 1–2 days | **1–3 business days (Microsoft)** | 2–5 business days | 2–4 business days |
| **Recommended Verdict** | Good if enterprise budget exists | **Best Value & Highest Integration Quality** | Enterprise Standard / Expensive | Good Alternative |

---

## 6. Implementation Blueprint for `.github/workflows/release.yml`

To transition the release workflow from interim signing to Azure Trusted Signing, the following modifications will be made to `.github/workflows/release.yml`:

### 1. Runner Operating System
Change the `sign` job environment from Ubuntu to Windows to enable native PowerShell validation and Authenticode verification:
```yaml
  sign:
    name: Sign Executables
    needs: [build]
    runs-on: windows-latest
```

### 2. Permissions for OIDC Authentication
Add `id-token: write` permission to the `sign` job to support passwordless federated authentication with Azure:
```yaml
    permissions:
      contents: read
      id-token: write
```

### 3. Replacement of Signing Step
Replace the interim signing step with the authenticated Azure Trusted Signing action:
```yaml
      - name: Azure Login via OIDC
        uses: azure/login@v3
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Sign Executable
        uses: azure/artifact-signing-action@v2
        with:
          endpoint: 'https://eus.codesigning.azure.net/'
          signing-account-name: ${{ secrets.AZURE_SIGNING_ACCOUNT_NAME }}
          certificate-profile-name: ${{ secrets.AZURE_CERTIFICATE_PROFILE_NAME }}
          files-folder: 'dist'
          files-folder-filter: 'exe'
```

### 4. Automated Post-Signing Verification
Enforce a fail-closed verification step using PowerShell's `Get-AuthenticodeSignature`:
```yaml
      - name: Verify Authenticode Signature
        shell: pwsh
        run: |
          $sig = Get-AuthenticodeSignature .\dist\JARVIS.exe
          Write-Host "Authenticode Status: $($sig.Status)"
          Write-Host "Publisher: $($sig.SignerCertificate.Subject)"
          if ($sig.Status -ne "Valid") {
            Write-Error "Authenticode validation failed with status: $($sig.Status)"
            exit 1
          }
```

### 5. Release Notes Update
Update the release generation step (`publish` job) to reflect that releases are signed by a globally trusted Certificate Authority, eliminating the disclaimer that advises users to bypass SmartScreen warnings.

---

## 7. Migration Checklist & Timeline

- [ ] **Phase 1 (Week 1)**: Enroll in Azure Trusted Signing via Azure Portal; submit business verification documents.
- [ ] **Phase 2 (Week 1–2)**: Configure Entra ID App Registration, Federated OIDC credentials, and Certificate Profile (`Jarvis_Production_Profile`).
- [ ] **Phase 3 (Week 2)**: Add repository secrets (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_SIGNING_ACCOUNT_NAME`, `AZURE_CERTIFICATE_PROFILE_NAME`).
- [ ] **Phase 4 (Week 2)**: Update `.github/workflows/release.yml` with the Azure Trusted Signing job and trigger a test release tag.
- [ ] **Phase 5 (Week 3)**: Verify that Windows Defender SmartScreen recognizes the signed binary without unknown publisher warnings.
