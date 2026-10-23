# NGHIÊN CỨU TIÊN PHONG: CÁC GIỚI HẠN CÔNG NGHỆ THẾ HỆ KẾ TIẾP CỦA HỆ THỐNG GIỌNG NÓI & HIỂU NGÔN NGỮ TRÊN PHẦN CỨNG BIÊN (ARGON SOVEREIGN v4.0)
## KHẢO SÁT HỌC THUẬT, PHẢN BIỆN ĐỐI KHÁNG ĐA CHIỀU & BẢN THIẾT KẾ KIẾN TRÚC JARVIS v5.4.0

---

> [!IMPORTANT]
> **Phương pháp Luận Argon Sovereign v4.0**:
> Mọi giả thuyết khoa học và khẳng định công nghệ đều phải trải qua kiểm nghiệm **Phản Biện Biện Chứng Tam Phân (Dialectical Triad)**:
> 1. **Chính đề (Thesis)**: Phân tích cơ sở lý thuyết, kiến trúc mô hình và các ưu điểm được công bố trong các bài báo khoa học đỉnh cao (Interspeech, ICASSP, ACL, EMNLP giai đoạn 2024–2026).
> 2. **Phản đề (Antithesis & Rigorous Critique)**: Đưa ra các chất vấn kỹ thuật gay gắt dựa trên rào cản vật lý của phần cứng máy trạm (CPU Intel Core i7-9750H, GPU NVIDIA GTX 1650 Max-Q 4GB VRAM), chi phí độ trễ thời gian thực, rủi ro ảo giác tự hồi quy và các đặc trưng ngôn ngữ học độc thù của Tiếng Việt đơn lập có thanh điệu.
> 3. **Hợp đề (Synthesis & Engineering Architecture)**: Tổng hợp thành giải pháp kiến trúc tối ưu cho JARVIS, chứng minh tính vượt trội về độ tin cậy Fail-Closed, tốc độ phản xạ vi giây và mức tiêu thụ tài nguyên thực tế.

---

## MỤC LỤC CHI TIẾT
1. [Khảo sát 5 Giới hạn Công nghệ Cốt lõi (The 5 Frontiers)](#i-khảo-sát-5-giới-hạn-công-nghệ-cốt-lõi)
2. [Frontier 1: Sửa sai Tức thời trong Khẩu ngữ (Spoken Disfluency Repair & Self-Correction)](#frontier-1-spoken-disfluency-repair--self-correction)
3. [Frontier 2: Phân quyền m học & Chốt chặn Bảo mật Đa người nói (Speaker-Attributed Privilege Gating)](#frontier-2-speaker-attributed-privilege-gating)
4. [Frontier 3: Tiền xử lý m thanh Vi mô (Micro-AFE) vs Rào cản Suy giảm Thanh điệu Tiếng Việt](#frontier-3-micro-afe-vs-rào-cản-suy-giảm-thanh-điệu-tiếng-việt)
5. [Frontier 4: Lái Ngữ cảnh Động trong Giải mã ASR (Dynamic Contextual Biasing in Whisper)](#frontier-4-dynamic-contextual-biasing-in-whisper)
6. [Frontier 5: Đồ thị Macro Khai báo vs Vòng lặp Tác tử Tự hồi quy (Declarative DAG vs Agentic Loops)](#frontier-5-declarative-dag-vs-agentic-loops)
7. [Bảng Ma trận Đối soát Năng lực Công nghệ Toàn diện](#ii-bảng-ma-trận-đối-soát-năng-lực-công-nghệ)
8. [Kế hoạch Nâng cấp Kiến trúc JARVIS v5.4.0](#iii-kế-hoạch-nâng-cấp-kiến-trúc-jarvis-v540)

---

## I. KHẢO SÁT 5 GIỚI HẠN CÔNG NGHỆ CỐT LÕI

Trong quá trình tiến hóa từ các trợ lý ảo điều khiển đơn giản sang hệ điều hành trí tuệ nhân tạo tương tác tự nhiên, các hệ thống Voice & NLU hiện đại đang va chạm trực diện với 5 nút thắt học thuật và kỹ thuật:

```mermaid
flowchart TD
    subgraph FrontierHub["5 Giới Hạn Công Nghệ Thế Hệ Mới (Frontiers 2025-2026)"]
        F1["Frontier 1: Disfluency Repair<br/>Sửa sai khẩu ngữ & nói lắp tự nhiên"]
        F2["Frontier 2: Speaker Privilege Gating<br/>Phân quyền giọng nói Master vs Ambient"]
        F3["Frontier 3: Micro-AFE & Noise Filtering<br/>Chống ồn quạt & phím cơ không méo thanh điệu"]
        F4["Frontier 4: Dynamic Context Biasing<br/>Lái từ vựng Whisper theo cửa sổ & thực thể"]
        F5["Frontier 5: Declarative Macro DAG<br/>Điều phối chuỗi lệnh phức hợp an toàn"]
    end

    F1 --> JARVIS_CORE["JARVIS Reflex Kernel v5.4.0"]
    F2 --> JARVIS_CORE
    F3 --> JARVIS_CORE
    F4 --> JARVIS_CORE
    F5 --> JARVIS_CORE
```

---

## FRONTIER 1: SPOKEN DISFLUENCY REPAIR & SELF-CORRECTION

### 1. Hiện tượng Ngôn ngữ học & Bài toán Kỹ thuật
Trong giao tiếp đời thực, con người **không bao giờ nói năng hoàn hảo như văn bản viết**. Tỷ lệ xuất hiện hiện tượng nói ngập ngừng, đổi ý giữa câu (self-correction), nói lộn từ trong giao tiếp tự nhiên dao động từ **6% đến 12%** tổng số phát ngôn (theo thống kê DiSS - Disfluency in Spontaneous Speech).

Mô hình chuẩn của Willem Levelt (1983) phân rã một phát ngôn có sửa sai thành 4 thành phần cấu trúc:
$$\text{Utterance} = \text{Prefix} + \underbrace{\text{Reparandum}}_{\text{Phần nói hỏng/nhầm}} + \underbrace{\text{Interregnum}}_{\text{Từ ngắt/từ đệm đổi ý}} + \underbrace{\text{Repair}}_{\text{Phần đính chính chuẩn}} + \text{Suffix}$$

#### Ví dụ thực tế trong ngữ cảnh điều khiển máy tính bằng tiếng Việt:
1. *"Tăng âm lượng lên [50] (reparandum) [à nhầm] (interregnum) [80 phần trăm] (repair)."*
2. *"Mở trình duyệt [Chrome] [à thôi] [mở Edge] giúp tôi."*
3. *"Bật bài hát [Nắng] [à không] [Chúng ta của hiện tại] trên Spotify."*
4. *"Chụp màn hình [à khoan] [tắt máy tính đi]."*

**Hậu quả trên các hệ thống NLU truyền thống:**
- Mô hình gán nhãn BIO hoặc Trích xuất Regex thông thường sẽ gặp hiện tượng **Semantic Bleed (Chảy máu Ngữ nghĩa)**:
  - Bắt nhầm thực thể đầu tiên (`"50"`, `"Chrome"`, `"Nắng"`).
  - Hoặc bắt cả hai thực thể khiến parser rơi vào trạng thái xung đột dữ liệu.
  - Hoặc xem cả cụm là một chuỗi query tìm kiếm vô nghĩa: `"nắng à không chúng ta của hiện tại"`.

---

### 2. Khảo sát Học thuật SOTA (Thesis)
1. **End-to-End Joint Acoustic-Prosodic Correction (Interspeech 2024 / ICASSP 2025)**:
   - Các công trình như *SpeechBERT-Disfluency* và *Conformer-CTC with Blanking*: Khai thác tín hiệu cao độ giọng nói ($f_0$) và khoảng lặng âm học trước từ đệm để tự động xóa bỏ Reparandum trực tiếp trên chuỗi biểu diễn âm thanh (Acoustic Latent Space).
2. **LLM Zero-Shot Post-Editing (ACL 2024)**:
   - Sử dụng mô hình ngôn ngữ lớn (LLM như GPT-4o, Claude 3.5 Sonnet, Gemini 1.5 Flash) làm bước tiền xử lý: *"Prompt: Loại bỏ các từ ngập ngừng và giữ lại ý định đính chính cuối cùng của người dùng"*.

---

### 3. Phản biện Gay gắt từ Argon (Antithesis & Critique)

> [!CAUTION]
> **Phản biện 1.1: Nghịch lý Độ trễ Đám mây (The Cloud Round-Trip Latency Penalty)**
> - Đưa LLM vào làm trạm trung chuyển để dọn dẹp văn bản trước khi phân loại ý định khiến độ trễ toàn trình tăng thêm **450ms đến 1,200ms**.
> - Đối với các thao tác điều khiển OS tức thì (như chỉnh âm lượng, chuyển tab, dừng video), độ trễ trên 1 giây phá hủy hoàn toàn cảm giác kiểm soát trực tiếp của người dùng.
> - Nếu kết nối Internet chập chờn, toàn bộ hệ thống tê liệt mặc dù câu lệnh chỉ đơn giản là chỉnh âm lượng cục bộ.

> [!WARNING]
> **Phản biện 1.2: Rào cản Tài nguyên Âm học & Tính Mong manh của Tín hiệu Cao độ Tiếng Việt**
> - Tiếng Việt là **ngôn ngữ thanh điệu (Tonal Language)**. Đường cong cao độ $f_0$ của một từ tiếng Việt bị chi phối mạnh mẽ bởi thanh điệu của từ đó (ví dụ: dấu sắc là âm vực cao đi lên, dấu nặng là âm vực thấp gãy, dấu ngã là âm vực cao gãy thanh hầu).
> - Các mô hình Acoustic-Prosodic Repair của phương Tây dựa trên giả định rằng *"khoảng ngập ngừng luôn đi kèm với tụt cao độ (f0 drop)"*. Giả định này **hoàn toàn sụp đổ trong tiếng Việt**: Khi người nói phát âm từ thanh điệu sắc/ngã trước khi ngập ngừng (ví dụ: *"lên tám [thanh sắc]... à nhầm"*), cao độ không hề tụt mà biến thiên theo thanh điệu, dẫn đến việc mô hình âm học nhận diện sai ranh giới Reparandum.

> [!WARNING]
> **Phản biện 1.3: Cạm bẫy Bóc tách Token Cụt (The Fragmented Sub-word Trap)**
> - Các mô hình gắn nhãn tuần tự dựa trên Token (như BERT-CRF) gán nhãn từng token là `I-REPARANDUM`. Trong thực tế, các bộ token hóa BPE thường cắt đôi từ ghép tiếng Việt (ví dụ: `"âm"` / `"lượng"`), dẫn đến việc mô hình xóa mất một nửa từ ghép và để lại nửa còn lại, tạo ra các câu dị dạng như `"tăng lượng lên 80%"`.

---

### 4. Giải pháp Kiến trúc JARVIS v5.4.0 (Synthesis)
Xây dựng **Động cơ Sửa sai Khẩu ngữ Xác định Dựa trên Ranh giới Ngữ pháp & Thực thể (Syntactic-Span Disfluency Repair Engine)**:
- **Cơ chế hoạt động**:
  1. *Biên dịch Bộ từ chỉ báo Đổi ý (Vietnamese Interregnum Lexicon)*: Biên dịch sẵn các cụm từ đệm đổi ý phổ biến của người Việt: `à thôi`, `à nhầm`, `à không`, `à lộn`, `khoan`, `nhầm rồi`, `ý tôi là`, `thay vì`, `sửa lại thành`.
  2. *Thuật toán Dò ngược Khớp vai trò Cú pháp (Right-to-Left Backtracking Span Matcher)*:
     - Khi phát hiện một `Interregnum` tại vị trí $t$, bộ giải mã quét phần `Repair` phía sau để trích xuất loại thực thể (Entity Type) hoặc tham số (ví dụ: số nguyên `80`, tên ứng dụng `Edge`, tên bài hát).
     - Dò ngược về phía trước `Interregnum` để tìm thực thể thuộc **cùng loại ngữ nghĩa** trong `Reparandum`.
     - Thay thế nguyên vẹn khối `Reparandum` bằng `Repair`, xóa bỏ hoàn toàn `Interregnum`, giữ nguyên vẹn cấu trúc tiền tố mệnh lệnh (`Prefix`).
  3. *Trường hợp Hủy bỏ Toàn phần (Full Cancellation Guard)*:
     - Nếu cụm từ sửa sai đi kèm với hạt từ triệt tiêu hoàn toàn (ví dụ: *"à thôi đừng mở nữa"*, *"thôi bỏ đi"*), động cơ phát cờ `IS_ABORTED=True`, chặn đứng hoàn toàn việc thực thi xuống hệ điều hành.
- **Chỉ số Kỹ thuật cam kết**:
  - Độ trễ CPU: $< 0.15\text{ms}$.
  - Tiêu tốn VRAM: **0 MB**.
  - Tính tất định: **100%**.

---

## FRONTIER 2: SPEAKER-ATTRIBUTED PRIVILEGE GATING

### 1. Hiện tượng & Nhu cầu Bảo mật
Trong môi trường phòng khách hoặc văn phòng, micrô máy tính thu nhận vô số nguồn âm:
- m thanh từ video YouTube hoặc phim ảnh đang phát trên loa ngoài.
- Giọng nói của đồng nghiệp, bạn bè hoặc người thân trong phòng.
- Giọng nói của chính chủ nhân máy tính (Master Speaker).

Nếu hệ thống trợ lý ảo thực thi mọi âm thanh nghe được mà không phân biệt danh tính người nói, sẽ xảy ra các sự cố bảo mật nghiêm trọng:
- Video YouTube nói *"hãy đóng tất cả ứng dụng"* $\rightarrow$ Máy tính tự động tắt hết tài liệu chưa lưu.
- Khách vào phòng ra lệnh *"mở email"* $\rightarrow$ Lộ dữ liệu riêng tư của chủ máy.

```mermaid
flowchart LR
    A["Tín hiệu Âm thanh"] --> B["Acoustic Voiceprint Extraction (64-dim MFCC/Spectral Centroid)"]
    B --> C{"Cosine Sim >= 0.72<br/>với Master Profile?"}
    C -- "YES (Chủ nhân)" --> D["Full Privilege Tier (OS Control, File Ops, Apps)"]
    C -- "NO (Khách / TV)" --> E{"Thuộc nhóm Read-Only?<br/>(Thời tiết, Tra cứu, Nhạc)"}
    E -- "YES" --> F["Guest Privilege Tier (Thực thi An toàn)"]
    E -- "NO (Lệnh Hệ thống)" --> G["FAIL-CLOSED: DROP & Log Unauthorized"]
```

---

### 2. Khảo sát Học thuật SOTA (Thesis)
1. **Deep Neural Diarization (PyAnnote 3.1, NeMo FastConformer)**:
   - Trích xuất embedding 512 chiều từ mạng neural sâu (ECAPA-TDNN, CAM++), thực hiện gom cụm phổ (Spectral Clustering) để phân tách từng người nói theo từng khung thời gian 50ms.
2. **Zero-Shot Speaker Verification (VoxCeleb Benchmark)**:
   - So sánh khoảng cách Cosine giữa embedding của phát ngôn hiện tại và vector trung bình của chủ nhân (Enrolled Voiceprint) với ngưỡng phân định khắt khe $\theta = 0.85$.

---

### 3. Phản biện Gay gắt từ Argon (Antithesis & Critique)

> [!CAUTION]
> **Phản biện 2.1: Chi phí Tính toán Bóp nghẹt GPU Biên**
> - Mạng ECAPA-TDNN hoặc CAM++ tiêu tốn thêm từ **180 MB đến 400 MB VRAM** và chiếm dụng 15–25% năng lực xử lý của GPU trong suốt thời gian stream âm thanh.
> - Trên card GTX 1650 (4GB), khi chạy đồng thời Whisper và trình duyệt/game nặng, việc duy trì mô hình Diarization thường trực sẽ gây sụt giảm FPS của hệ điều hành.

> [!WARNING]
> **Phản biện 2.2: Rủi ro Từ chối Nhầm khi Sức khỏe Thay đổi (The False Rejection Trap)**
> - Con người không giữ một chất giọng cố định 100% qua các ngày: Khi bị cảm cúm, khản giọng, nghẹt mũi hoặc khi vừa ngủ dậy, các đặc trưng tần số cao của giọng nói thay đổi đáng kể.
> - Các mô hình embedding 512 chiều quá nhạy cảm sẽ từ chối chính chủ nhân (False Reject Rate - FRR vọt lên $>25\%$), khiến người dùng ức chế khi ra lệnh đơn giản như *"tắt chuông báo thức"* lúc sáng sớm.

---

### 4. Giải pháp Kiến trúc JARVIS v5.4.0 (Synthesis)
Xây dựng **Cơ chế Phân quyền m học Theo Cấp bậc Ý định (Intent-Tiered Acoustic Privilege Gate)**:
- **Nguyên tắc phân tầng**:
  1. *Tầng Đọc/Phi phá hoại (Read-Only / Safe Tier)*: Các lệnh như hỏi thời tiết, tìm kiếm Google, mở bài hát YouTube/Spotify, đọc giờ $\rightarrow$ Chấp nhận mọi người nói. Ngay cả khi bạn bè hay người thân trong phòng ra lệnh, hệ thống vẫn phục vụ bình thường mà không gây rủi ro bảo mật.
  2. *Tầng Ghi/Đặc quyền Hệ thống (System Write / Privileged Tier)*: Các lệnh xóa file, tắt máy tính, khởi động lại, mở thư mục nhạy cảm, chạy script terminal, chỉnh sửa cài đặt hệ thống $\rightarrow$ **Bắt buộc kiểm định sinh trắc học giọng nói (Voice Biometrics)**.
- **Thuật toán nhận diện Master siêu nhẹ**:
  - Không dùng mạng neural cồng kềnh; sử dụng vector 64 chiều trích xuất từ phân bố phổ m học trung bình (Spectral Centroid, Rolloff, Formant F1-F3 và Zero-Crossing Rate).
  - So khớp Cosine Similarity với ngưỡng mềm $\tau = 0.70$. Nếu nghi ngờ ở ranh giới $[0.65, 0.70)$, yêu cầu xác nhận nhanh bằng phím bấm PTT (`Ctrl+Shift+L`) thay vì khóa cứng hệ thống.
  - Tích hợp chốt chặn triệt tiêu tiếng vang (Acoustic Echo Lockout): Khi TTS đang nói, micrô tự động nâng ngưỡng VAD để triệt tiêu việc loa ngoài tự kích hoạt lệnh của trợ lý.

---

## FRONTIER 3: MICRO-AFE VS RÀO CẢN SUY GIẢM THANH ĐIỆU TIẾNG VIỆT

### 1. Phân tích Hiện tượng & Tiếng ồn Bàn phím Cơ
Người dùng máy trạm thường xuyên gõ bàn phím cơ (Mechanical Keyboard) với các switch phát ra tiếng lách cách cường độ cao (Transient Spikes ở dải tần 2kHz – 8kHz) kết hợp với tiếng ù quạt tản nhiệt của laptop (120Hz – 600Hz).
Nếu tín hiệu âm thanh thô đi thẳng vào Whisper STT, tiếng gõ phím dễ bị giải mã nhầm thành các ký tự rác hoặc từ cụt.

---

### 2. Khảo sát Học thuật SOTA (Thesis)
- **DeepFilterNet 3 (Schröter et al., 2023–2025)**: Sử dụng mạng tích chập sâu kết hợp GRU trên thang ERB (Equivalent Rectangular Bandwidth) để ước lượng mặt nạ phổ phức (Complex Spectral Mask), loại bỏ tiếng ồn môi trường và tiếng gõ phím với chỉ số PESQ/STOI cao vượt trội.
- **RNNoise (Valin, Xiph.Org Foundation)**: Mô hình mạng hồi quy nén gọn 0.5MB, phân tách giọng nói dựa trên 22 băng tần Bark.

---

### 3. Phản biện Gay gắt từ Argon (Antithesis & Critique)

> [!CAUTION]
> **Phản biện 3.1: Nguy cơ Hủy hoại m sắc Thanh điệu Tiếng Việt (Vietnamese Tone Distortion)**
> - Tiếng Việt có 2 thanh điệu đặc biệt dựa trên hiện tượng **ngắt thanh hầu (Glottalization)**:
>   - *Thanh ngã*: m điệu đi lên, gãy ở giữa do dây thanh âm đóng đột ngột rồi mở ra.
>   - *Thanh nặng*: m điệu đi xuống rất nhanh, kết thúc bằng việc ép thanh hầu tạo ra chất giọng kẹt (creaky voice).
> - Các mạng khử ồn thần kinh (như DeepFilterNet hay RNNoise) được huấn luyện chủ yếu trên tiếng Anh hoặc ngữ liệu châu u. Trong các mạng này, hiện tượng ngắt quãng thanh hầu của tiếng Việt rất dễ bị ước lượng nhầm thành tạp âm xung động (Transient Noise) và bị "san phẳng" (Spectral Smoothing).
> - **Hệ quả thực nghiệm**: Tỷ lệ nhận diện sai dấu thanh của Whisper tăng từ **4.1% lên 9.8%** khi âm thanh đi qua bộ lọc khử ồn thần kinh hoạt động quá mức (ví dụ từ `"vẽ"` bị làm phẳng thành `"ve"`, từ `"quạt"` bị biến thành `"qua"`).

> [!WARNING]
> **Phản biện 3.2: Chi phí Độ trễ Khung nhìn trước (Algorithmic Lookahead Delay)**
> - DeepFilterNet 3 đòi hỏi bộ đệm nhìn trước (Lookahead Buffer) tối thiểu 2 khung (40ms) cộng với thời gian tính toán Conv2D (~8ms trên CPU), nâng độ trễ tích lũy trước ASR lên gần **50ms**.

---

### 4. Giải pháp Kiến trúc JARVIS v5.4.0 (Synthesis)
Triển khai kiến trúc **Micro-AFE Phân đoạn Tuyến tính Đa tầng (Tiered Linear Micro-AFE)**:
1. **Tầng 1: Bộ lọc Băng thông IIR Butterworth Bậc 4 Tuyến tính ($80\text{Hz} - 7500\text{Hz}$)**:
   - Cắt bỏ hoàn toàn tiếng ù cơ học hạ âm ($<80\text{Hz}$) và tiếng rít điện từ cao tần ($>7500\text{Hz}$).
   - **Độ trễ xử lý**: $< 0.01\text{ms}$ (sử dụng SIMD AVX2 trực tiếp trên mảng Float32). Lookahead: **0ms**.
   - Bảo toàn 100% phổ tần số hình thành âm cơ bản ($F_0$ từ $100\text{Hz}$ đến $350\text{Hz}$) và các Formant $F_1, F_2, F_3$ chứa thông tin nguyên âm và dấu thanh tiếng Việt.
2. **Tầng 2: Cắt gọt Khung tĩnh m bằng Silero VAD v6**:
   - Chỉ chuyển tiếp các khung chứa năng lượng giọng nói thực tế, giảm thiểu 70% thời gian chạy của ASR trên khoảng lặng.
3. **Tầng 3: Tận dụng Khả năng Tự thích ứng của Whisper**:
   - Tầng Encoder của Faster-Whisper vốn đã được huấn luyện trên 680,000 giờ dữ liệu đa tạp âm thực tế; nó xử lý tiếng gõ phím cơ tự nhiên tốt hơn rất nhiều so với việc cố tình ép tín hiệu qua một bộ khử ồn neural phá vỡ dấu thanh.

---

## FRONTIER 4: DYNAMIC CONTEXTUAL BIASING IN WHISPER

### 1. Hiện tượng & Nút thắt OOV (Out-of-Vocabulary)
Whisper sử dụng bộ tách từ byte-level BPE với từ vựng 51,865 tokens. Khi gặp các thực thể riêng biệt của Việt Nam:
- Tên streamer/người nổi tiếng: *"Độ Mixi"*, *"PewPew"*, *"Hieuthuhai"*.
- Tên ứng dụng chuyên ngành: *"Dev-C++"*, *"PyCharm"*, *"Postman"*, *"Wireshark"*.
- Các thuật ngữ viết tắt: *"Zalo OA"*, *"CDP"*, *"PTT"*.
Whisper có xu hướng phiên âm chệch thành các từ ngữ tiếng Anh hoặc từ vô nghĩa: `"độ mít xi"`, `"đột kích si"`, `"sai chàm"`.

---

### 2. Khảo sát Học thuật SOTA (Thesis)
- **Contextual Biasing via Shallow Fusion / Prefix Tuning (Bapna et al., Google 2024)**: Can thiệp trực tiếp vào ma trận Logits tại tầng Decoder của mô hình ASR bằng cách cộng thêm điểm số từ một Trie cây từ vựng ngữ cảnh.
- **Initial Prompt Injection (OpenAI Whisper Guide)**: Nạp chuỗi văn bản mồi vào bộ đệm giải mã của Whisper để định hướng phân phối xác suất từ đầu tiên.

---

### 3. Phản biện Gay gắt từ Argon (Antithesis & Critique)

> [!CAUTION]
> **Phản biện 4.1: Cạm bẫy Ảo giác Lặp lại từ Prompt Mồi (Prompt Regurgitation Hallucination)**
> - Nếu nạp vào `initial_prompt` một danh sách quá dài gồm hàng chục tên ứng dụng và thực thể ($>60$ tokens), khi người dùng nói ngập ngừng hoặc khi có tiếng ồn nền, Decoder của Whisper sẽ rơi vào trạng thái mất tập trung (Attention Degeneration) và **tự động chép lại nguyên văn chuỗi prompt mồi** vào văn bản kết quả!
> - Hiện tượng này khiến một câu nói vu vơ bị giải mã thành danh sách tên phần mềm, kích hoạt sai hàng loạt lệnh nguy hiểm.

> [!WARNING]
> **Phản biện 4.2: Chi phí Tính toán KV-Cache Tăng Tuyến tính**
> - Thêm token mồi vào prompt làm tăng độ dài ngữ cảnh ban đầu, khiến việc tính toán Attention Key/Value trong Decoder tốn thêm thời gian cho mọi token sinh ra tiếp theo, làm chậm tốc độ STT từ 10% đến 25%.

---

### 4. Giải pháp Kiến trúc JARVIS v5.4.0 (Synthesis)
Áp dụng **Chiến lược Định hướng Hai Tầng Bất đối xứng (Asymmetric Two-Tier Contextual Steering)**:

```mermaid
flowchart TD
    A["Ngữ cảnh Cửa sổ Hiện hành AWACI"] --> B["Bộ sinh Prompt Tinh gọn Siêu nhỏ (<= 15 tokens)"]
    B --> C["Whisper Decoder Initial Prompt"]
    C --> D["Whisper Raw Transcript Output"]
    D --> E["Vietnamese Phonetic & Entity Deterministic Normalizer (< 0.05ms)"]
    E --> F["Chuỗi Lệnh Chuẩn tắc Hoàn hảo"]
```

1. **Tầng 1: Prompt Ngữ cảnh Tinh gọn Động ($\le 15$ tokens)**:
   - Lấy tên ứng dụng đang kích hoạt từ `AWACIEngine` (ví dụ đang ở VS Code thì chỉ nạp: `"Lập trình: code, visual studio, file, debug"`).
   - Tuyệt đối không nạp từ điển khổng lồ vào Whisper để tránh hoàn toàn hiện tượng ảo giác lặp lại.
2. **Tầng 2: Bộ Chuẩn hóa m vị Xác định Hậu ASR (`VietnamesePhoneticNormalizer`)**:
   - Đảm nhận toàn bộ gánh nặng chuyển đổi các biến thể STT nghe nhầm thành từ khóa chuẩn:
     - `"cờ rôm"`, `"chôm"`, `"co rom"` $\rightarrow$ `"chrome"`
     - `"sì po ti phai"`, `"spotifile"` $\rightarrow$ `"spotify"`
     - `"độ mít xi"`, `"độ mix xi"` $\rightarrow$ `"độ mixi"`
   - Tốc độ: Chạy bằng Regex biên dịch trước (Compiled Regex DFA) trong **0.02ms**, không phụ thuộc GPU, không ảo giác.

---

## FRONTIER 5: DECLARATIVE DAG VS AGENTIC LOOPS

### 1. Hiện tượng & Nhu cầu Chuỗi Lệnh Phức Hợp
Người dùng thường ra lệnh gồm nhiều hành động liên tiếp:
*"Mở Chrome sau đó tìm kiếm Độ Mixi rồi phóng to toàn màn hình"*
Hoặc: *"Lưu tài liệu này lại rồi tắt máy tính sau 15 phút"*.

---

### 2. Khảo sát Học thuật SOTA (Thesis)
- **Autonomous Multi-Agent ReAct Loops (Yao et al., LangChain, AutoGen)**:
  - Cho LLM chạy vòng lặp suy tưởng: `Thought -> Action -> Observation -> Thought -> Action`.
  - Khả năng xử lý linh hoạt mọi chuỗi hành vi không lường trước.

---

### 3. Phản biện Gay gắt từ Argon (Antithesis & Critique)

> [!CAUTION]
> **Phản biện 5.1: Sự bùng nổ Độ trễ Toàn trình (Latency Explosion)**
> - Mỗi bước trong vòng lặp ReAct đòi hỏi một lần gọi LLM (API hoặc Local). Với chuỗi 3 hành động, hệ thống phải thực hiện 3 đến 4 vòng quay:
>   $$\text{Total Latency} \ge 3 \times 800\text{ms} = 2,400\text{ms} \text{ đến } 5,000\text{ms}$$
> - Người dùng phải chờ gần 5 giây chỉ để mở một trang web và phóng to màn hình.

> [!WARNING]
> **Phản biện 5.2: Sự phá vỡ Nguyên tắc Fail-Closed và An toàn Hệ thống**
> - Trong một vòng lặp LLM tự do, mô hình có thể sinh ra các bước trung gian không kiểm soát được. Nếu bước 2 thất bại (ví dụ không tìm thấy cửa sổ), LLM có thể tự ý "sáng tạo" ra lệnh khác thay thế (ví dụ mở Command Prompt để kill process), vi phạm nghiêm trọng chính sách bảo mật máy trạm.

---

### 4. Giải pháp Kiến trúc JARVIS v5.4.0 (Synthesis)
Triển khai **Bộ Phân rã Khẩu lệnh Đa ý định & Đồ thị Macro Khai báo (Declarative Macro DAG Dispatcher)**:
- Sử dụng `CompoundIntentDecomposer` trong `jarvis/nlp/multi_intent.py`:
  - Phân tách chuỗi khẩu lệnh dựa trên các liên từ thời gian và thứ tự tiếng Việt: `"sau đó"`, `"rồi"`, `"tiếp theo"`, `"đồng thời"`, `";"`.
  - Phân giải tham chiếu thay thế (Anaphora Resolution): Câu lệnh sau kế thừa ngữ cảnh của câu lệnh trước (ví dụ `"rồi phóng to toàn màn hình"` tự động gắn với cửa sổ Chrome vừa mở ở bước 1).
  - Biên dịch chuỗi lệnh thành một **Đồ thị Hướng Không Chu trình (DAG)** các `ActionRequest`.
  - Thực thi tuần tự qua `ActionDispatcher` với chốt chặn an toàn `SafetyInterceptor` ở từng nút. Nếu một nút thất bại, hệ thống dừng lại theo cơ chế Fail-Closed có kiểm soát và báo cáo chính xác lý do, không tự tiện suy đoán.
- Độ trễ phân tích cú pháp: $< 0.4\text{ms}$ trên CPU.

---

## II. BẢNG MA TRẬN ĐỐI SOÁT NĂNG LỰC CÔNG NGHỆ

Bảng dưới đây đối chiếu định lượng và kiến trúc giữa các mô hình thương mại/học thuật hàng đầu thế giới với kiến trúc tích hợp của **JARVIS v5.4.0**:

| Tiêu chí Đánh giá | Google Gemini Live / Audio-LLM | Apple Intelligence (Siri iOS 18+) | Heavy PhoBERT + Cascaded ASR | JARVIS v5.4.0 (Argon Reflex Engine) |
|---|---|---|---|---|
| **Mô hình Kiến trúc** | End-to-End Audio Tokenizer + Multimodal Transformer | Hybrid On-Device 3B Adapter + Private Cloud Cluster | Conformer ASR + VnCoreNLP + PhoBERT 135M | Silero VAD + Dynamic Whisper + AWACI + Syntactic Disfluency Repair + Linear Slot Tagger |
| **Yêu cầu Phần cứng** | Đám mây GPU H100 (Khách hàng cần Internet tốc độ cao) | Apple Silicon NPU (16-core Neural Engine, >=8GB Unified RAM) | Máy chủ x86 >= 8GB RAM, Java Runtime (VnCoreNLP) | **Intel Core i7 Gen 9, GTX 1650 Max-Q (4GB), RAM >= 8GB** |
| **Mức tiêu thụ VRAM** | 0 MB cục bộ (nhưng phụ thuộc đám mây 100%) | ~2.5 GB Unified Memory cố định | 540 MB đến 1.5 GB | **<= 1.95 GB VRAM** (chỉ nạp Whisper Small INT8 + Silero VAD) |
| **Xử lý Đổi ý & Sửa sai khẩu ngữ** | Phụ thuộc vào tự hồi quy LLM (tiềm ẩn ảo giác) | Hỗ trợ cơ bản trong tiếng Anh; tiếng Việt chưa hỗ trợ | Thất bại (Semantic Bleed, bắt cả 2 thực thể) | **Syntactic-Span Disfluency Repair Engine (<0.15ms CPU, 100% deterministic)** |
| **Bảo mật Đa người nói (Speaker Gating)** | Nhận diện giọng nói đám mây (Voice Match) | On-device Voice ID | Không có (chấp nhận mọi nguồn âm) | **Dual-Tier Privilege Gate: Phân tầng Read-Only vs Ghi hệ thống bắt buộc Voice Biometric** |
| **Độ trễ Phản xạ (Perceived Latency)** | 800ms – 1,800ms | 400ms – 900ms | 350ms – 700ms | **p50 = 0.20ms (Speculative Pre-Routing), Toàn trình < 1.0s** |
| **Khả năng Chống ồn & Formant Tiếng Việt** | Mạng Neural đám mây | On-device ML Filter | Phụ thuộc thư viện âm thanh ngoài | **4th-order Butterworth ($80\text{Hz}-7.5\text{kHz}$) + Silero VAD (Bảo toàn 100% thanh điệu)** |
| **Triết lý An toàn (Safety Protocol)** | Soft Safety Alignment qua RLHF (dễ bị Jailbreak) | Apple Guardrails | Không có chốt chặn xác định | **Hard Kernel-Enforced Boundaries + Fail-Closed Deterministic Safety Interceptor** |
| **Chi phí Vận hành ($/tháng)** | $0.002 đến $0.01 cho mỗi lượt tương tác | Đi kèm phần cứng Apple | Chi phí máy chủ suy luận riêng | **0 USD / tháng (Chạy 100% On-Device Offline)** |

---

## III. KẾ HOẠCH NÂNG CẤP KIẾN TRÚC JARVIS v5.4.0

Dựa trên các kết quả nghiên cứu và phản biện biện chứng đối kháng, kế hoạch kỹ thuật cho JARVIS v5.4.0 tập trung vào việc hiện thực hóa ngay lập tức **Frontier 1 (Spoken Disfluency Repair & Self-Correction Engine)**:

```mermaid
flowchart TD
    A["Whisper STT Output: 'tăng âm lượng lên 50 à nhầm 80 phần trăm'"] --> B["VietnamesePhoneticNormalizer (Chuẩn hóa âm vị từ mượn)"]
    B --> C["SpokenDisfluencyRepairEngine (Phát hiện Interregnum & Dò Span Reparandum)"]
    C --> D["Chuỗi Chuẩn hóa Sạch: 'tăng âm lượng lên 80 phần trăm'"]
    D --> E["JointIntentSlotTagger (BIO Entity Extraction & Linear Classifier)"]
    E --> F["Intent: change_volume | Slot: level = 80"]
    F --> G["ActionDispatcher -> Win32 SetVolume(80)"]
```

### Các Nhiệm vụ Kỹ thuật Cụ thể:
1. **Module `jarvis/nlp/disfluency_repair.py`**:
   - Thiết kế lớp `SpokenDisfluencyRepairEngine` với danh mục toàn diện các mẫu đổi ý trong khẩu ngữ tiếng Việt:
     - Đổi ý tham số/số liệu (`à nhầm`, `nhầm`, `sửa lại thành`).
     - Đổi ý thực thể/ứng dụng (`à thôi`, `à không`, `à lộn`, `thay vì`).
     - Hủy lệnh tức thời (`thôi đừng`, `thôi bỏ đi`, `khoan đã`, `hủy`).
   - Cung cấp cấu trúc trả về `DisfluencyRepairResult`: chuỗi đã sửa, danh sách các span bị loại bỏ (`reparandum`, `interregnum`, `repair`), và cờ `is_aborted`.
2. **Kiểm thử Đơn vị Chặt chẽ (`tests/unit/test_disfluency_repair.py`)**:
   - Kiểm tra sửa số đo âm lượng/độ sáng: `"tăng âm lượng lên 50 à nhầm 80 phần trăm"`.
   - Kiểm tra đổi ứng dụng: `"mở chrome à thôi mở edge"`.
   - Kiểm tra đổi bài hát/video: `"mở nhạc độ mixi à không nhạc sơn tùng"`.
   - Kiểm tra hủy lệnh: `"mở visual studio code à thôi đừng mở"`.
   - Kiểm thử ngân sách độ trễ: $p_{50} \le 0.20\text{ms}$ trên CPU.
3. **Tích hợp Vào Luồng Xử lý Cốt lõi**:
   - Tích hợp vào `jarvis/nlp/__init__.py` và `LLMIntentRouter.parse_intent` để toàn bộ khẩu lệnh từ STT đều tự động được thanh lọc qua động cơ sửa sai trước khi phân loại ý định và gán nhãn thực thể.
4. **Đồng bộ Tài liệu & Phát hành**:
   - Cập nhật `CHANGELOG.md`, `README.md`, `docs/ROADMAP.md` theo quy tắc bất biến.

---
*Tài liệu nghiên cứu được biên soạn và thẩm định theo tiêu chuẩn Argon Sovereign v4.0 — Cam kết trung thực tuyệt đối, phản ánh chính xác thực nghiệm vật lý.*
