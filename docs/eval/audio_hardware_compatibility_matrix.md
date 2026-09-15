# Ma Tran Tuong Thich Phan Cung Thiet Bi Am Thanh (Audio Hardware Compatibility Matrix)
**Du An**: JARVIS Voice Assistant - Beta v1
**Trang Thai**: PARTIAL - 3/10 TIER 1 PASS (tin hieu that)
**Lan do**: 2026-09-16 00:08 ICT | Raw JSON: docs/eval/audio_hardware_compatibility_matrix_results_r2.json

## Bang Danh Gia 10 Cau Hinh

| STT | Cau Hinh | Ket Noi | Trang Thai | Peak | Sample Rate | Ghi Chu |
|:---:|:---|:---|:---:|:---:|:---:|:---|
| 1 | Built-in Mic Array (Realtek) | Internal | TIER1_PASS | 5697 | 16kHz | Device[1] R1 - tin hieu that |
| 2 | USB Microphone (USB Audio) | USB | TIER1_PASS | 4619 | 16kHz | Device[1] R2 - USB mic NEW |
| 3 | Realtek Array (beamforming) | Internal | TIER1_PASS | 332 | 16kHz | Device[3] R2 - confirmed |
| 4 | Virtual Audio Cable (VB-Audio) | Virtual | TIER1_PASS_SILENT | 1 | 16kHz | Device[2] - loopback OK |
| 5 | iPhone Virtual Mic (Camo) | USB Virtual | TIER1_PASS_SILENT | 1 | 16kHz | Device[4] - stream OK, signal not confirmed |
| 6 | Bluetooth HFP (LY-Z5202) | BT HFP | TIER1_FAIL | - | 8kHz | PaErrorCode -9999 exclusive mode |
| 7 | Bluetooth HFP (AirPods Pro) | BT HFP | TIER1_FAIL | - | 8kHz | PaErrorCode -9999 exclusive mode |
| 8 | USB Audio Interface 8ch | USB | TIER1_FAIL | - | - | blocked |
| 9 | Webcam Integrated Mic | USB | CHUA KET NOI | - | - | chua co |
| 10 | USB Condenser Mic | USB-C | CHUA KET NOI | - | - | chua co |

## Ket Luan

- Tier 1 PASS (tin hieu that): 3/10 - Realtek built-in, USB Mic, Realtek Array
- Tier 1 PASS_SILENT: 2/10 - VB-Audio, Camo
- Tier 1 FAIL: 3/10 - Bluetooth HFP, 8ch
- Chua ket noi: 2/10
- H-10 Status: PARTIAL
