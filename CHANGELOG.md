# MeetTranscribe 開發紀錄

**專案**：MeetTranscribe — 免費 AI 會議轉錄與分析工具
**部署**：https://meet-transcribe.streamlit.app
**操作手冊**：https://claude.ai/code/artifact/39221198-5e11-4d5f-a739-d30b1cac141f — 圖解操作流程（申請 Groq API Key → 音檔轉逐字稿 → AI 整理成會議紀錄）
**技術棧**：Streamlit · Groq Whisper · Groq Llama 3.3 70B · Python

---

## v1.11 — 2026-11-11

### 新功能
- **名詞對照表持續保存**：整張對照表（手動、匯入、AI 學到的，含啟用狀態）自動存在瀏覽器，下次開啟直接沿用，AI 會在既有基礎上繼續學
- **歷史記錄保存更可靠**：上傳音檔的轉錄、錄音轉錄、AI 分析、即時口譯都持續保存；儲存位置由 localStorage（約 5 MB 上限，紀錄一多會靜默存不進去）改為 IndexedDB，舊資料第一次開啟時自動接手
- **整包備份／還原**：歷史記錄分頁新增「備份全部紀錄 (.json)」，包含所有紀錄與名詞對照表；在別台電腦或別的瀏覽器上傳即可還原（同一筆不重複加入）
- 瀏覽器無法儲存時（無痕模式、空間已滿）會在歷史記錄分頁顯示警告

### 修正
- 歷史記錄分頁上傳 JSON 後，同一個檔案不再被重複載入

### 技術細節
- 新增自訂元件 `local_store/index.html` 負責讀寫 IndexedDB，取代 `streamlit-javascript`（讀）與 `st.components.v1.html`（寫，Streamlit 已宣告移除）；`requirements.txt` 移除 `streamlit-javascript`
- 內容以 MD5 比對，沒有變動就不重送，避免即時口譯時每段都重傳整份歷史

### 已知限制
- 原始音檔不保存（太大），只在當次連線可播放與下載
- 資料存在「這台電腦的這個瀏覽器」；換裝置請用備份檔

---

## v1.10 — 2026-11-11

### 新功能
- **講者語言自動偵測**（預設）：每講完一小段就把錄音送 Groq Whisper 辨識，任何語言、中英夾雜都可以；簡報與對照表裡的名詞會當作提示傳給 Whisper，專有名詞比較不會聽錯。字幕約慢 5–10 秒；指定語言時仍用瀏覽器語音辨識（字會邊講邊出現）
- **中英互譯**：「翻譯成」新增「自動（中文↔英文互譯）」，講中文翻成英文、講英文或其他語言翻成中文；也可固定翻成 English
- **專有名詞對照表改為可編輯表格**（啟用／原文／譯名／來源）
  - 可匯入 Excel（.xlsx）或 CSV，並提供「下載範例 Excel」
  - **AI 邊聽邊學**：每 6 段從原文與譯文挑出專有名詞加進表格（來源標示「AI 學習」）
  - 學到的內容可直接修改譯名、取消勾選停用、刪除，或一鍵「清掉 AI 學到的」
  - 「下載對照表」存成 Excel，下次直接匯入沿用
- **口譯內容存入歷史記錄**：每場口譯自動存成一筆（標示「口譯」），在「歷史記錄」分頁可查看原文／譯文對照並下載 Word／CSV／純文字；「開始新的一場」會另開一筆

### 技術細節
- `live_mic/index.html` 新增錄音模式：以音量偵測停頓切段（2.5–12 秒），沒有人聲的片段不送出；錄音以 base64 送回 Python
- `_live_whisper`：`whisper-large-v3-turbo`，失敗時改用 `whisper-large-v3`；略過 `no_speech_prob > 0.6` 的片段
- 對照表超過 60 組時，每句只帶入該句出現的名詞與前 60 組，避免超過 Groq 免費方案的 token 上限
- `requirements.txt` 新增 `openpyxl`

### 已知限制
- 自動偵測模式會使用 Groq 的音訊額度（免費方案每小時 7,200 秒）
- 歷史記錄存在瀏覽器 localStorage，換瀏覽器或清除網站資料就會消失，重要內容請下載

---

## v1.9 — 2026-11-11

### 新功能
- **即時口譯**（「即時錄音／口譯」分頁 → 模式選「即時口譯」）：按「開始聆聽」後，講者每說完一句就翻譯一句，最新譯文以大字顯示，下方為原文／譯文對照表
  - 講者語言可選（英、中、粵、日、韓、德、法、西）；直接輸入或貼上文字時自動偵測語言
  - 可翻成繁體中文、English、日本語、한국어、简体中文
- **上傳簡報提高精準度**：上傳講者的 `.pptx` 或 `.pdf`，自動整理出主題與專有名詞（含備忘稿、表格文字），用來修正語音辨識聽錯的名詞並統一譯法；整理結果可直接修改
- **場景判斷**：可自行填寫場景，也會每 6 段依內容自動判斷場合與領域；另可貼上專有名詞對照表
- **對照檔下載**：Word 對照表（.docx）、CSV（Excel 可開，另含原始辨識文字）、純文字，皆同時包含原文與譯文

### 技術細節
- 語音辨識使用瀏覽器 Web Speech API（自訂元件 `live_mic/index.html`，不經伺服器、不佔 Groq 音訊額度）；辨識完成的段落帶遞增 id 送回 Python，Python 以 `acked` 回報已處理的 id，避免重複或漏譯
- 翻譯使用 Groq `llama-3.3-70b-versatile`，JSON 模式一次回傳「修正後原文」與「譯文」；遇到 429 時自動改用 `llama-3.1-8b-instant` 並讓主力模型休息 90 秒
- `requirements.txt` 新增 `python-docx`、`python-pptx`、`pypdf`

### 已知限制
- 即時口譯需使用電腦版 Chrome 或 Edge
- 瀏覽器語音辨識一次只能聽一種語言，且無法事先餵入字彙；簡報名詞是在翻譯步驟用來修正辨識結果
- 口譯內容只存在當次連線，重新整理頁面會清空，請先下載

---

## v1.8 — 2026-11-10

### 修正
- **繁體中文輸出**：Whisper 轉錄結果改以 opencc s2twp 自動轉換為繁體中文（台灣慣用詞：軟體、網路、檔案、歐盟⋯），解決原本輸出簡體字的問題
- **標點符號補全**：在 Whisper API 呼叫加入 `prompt="請使用繁體中文輸出，並加上正確的標點符號。"`，引導模型輸出帶標點的文字，不再輸出無標點連續文字串
- **AI 修正逐字稿繁體化**：Llama 分析 prompt 明確要求 `corrected_transcript` 欄位使用繁體中文並加標點

### 技術細節
- 新增 opencc 初始化區塊（頂部）：使用 `opencc-python-reimplemented` 載入 `s2twp` 轉換器；import 失敗時 fallback 為原文，不影響運行
- `_call_whisper`：依語言參數（`zh` 或 `None`）決定是否傳入 prompt；每段 segment 文字以 `_to_traditional()` 轉換後才存入結果
- `requirements.txt` 新增 `opencc-python-reimplemented>=0.1.7`

---

## v1.7 — 2026-11-02

### 新功能
- **逐字稿時間軸標示**：所有下載格式均於每行前綴 `[HH:MM:SS]` 時間軸
  - 會議紀錄 `.txt`（「下載會議記錄」）
  - 純逐字稿 `.txt`（「下載逐字稿」）
  - 歷史記錄 `.txt`（歷史分頁「下載逐字稿」）
  - 輸出格式：`[HH:MM:SS] 發言者: 內容`
- **新增 README.md**：功能總覽、快速開始（Streamlit Cloud / 本機）、Groq 免費方案限制

### 技術細節
- 新增 `_fmt_entry(e)` helper，統一管理時間軸前綴邏輯，避免三處下載位置各自維護
- `displayTime` 欄位存在時輸出 `[HH:MM:SS] 發言者: 內容`，不存在時退回原有格式，向下相容

---

## v1.6 — 2026-07-31

### 修正
- **修復大檔案轉錄出現 `400 could not process file` 的問題**
  - 根本原因：`_split_audio` 切片時，若音訊總長剛好落在 8 分鐘倍數之後一點（例如 3840.02 秒），
    會多切出一段約 0.02 秒的 mp3。ffmpeg 對這種長度產出沒有音訊框的空檔，
    而舊碼只用 `Path(out).exists()` 判斷成功——檔案存在但內容是空的，仍被送給 Whisper
  - 解法：捨棄長度 < 1 秒的尾段；改為同時檢查 ffmpeg `returncode` 與輸出檔大小（≥ 2048 bytes）
- **切片失敗不再靜默**：ffmpeg 失敗時 raise 並附上 stderr 尾三行，指出是第幾段、returncode 多少
- **送出前防呆**：`_call_whisper` 擋掉小於 2048 bytes 的空檔，不再讓 Groq 回英文原文錯誤
- 修復 `_ffmpeg_ok()` 未檢查 returncode，ffmpeg 裝壞仍回報可用
- 修復 `_audio_duration` 在 webm / ogg 等缺少 stream duration 的容器上回傳 0，
  導致誤報「找不到 ffmpeg」：改為退回 `format.duration`
- 暫存切片改用 `try/finally` 清理，轉錄中途失敗不再殘留檔案

### 改善
- 切片改用 input seeking（`-ss` 移到 `-i` 之前），長音訊不必每段從頭解碼，大幅加快分割
- 切片檔名不再產生 `tmpXXX.m4a_c0.mp3` 這種雙副檔名
- `_friendly_error` 新增 400 的中文說明，並列出 Groq 實際支援的格式
  （flac / mp3 / mp4 / mpeg / mpga / m4a / ogg / opus / wav / webm，**不含 raw .aac**）
- **修復 `.aac` 上傳被拒**：Groq 不支援 raw ADTS，過去 24 MB 以下的 .aac 會直接回 400，
  超過 24 MB 反而因為被 ffmpeg 轉成 mp3 而成功。現在改為：副檔名不在 Groq 支援清單內時，
  一律先用 ffmpeg 轉成 mp3（mono / 16 kHz / 48 kbps）再送，行為一致

---

## v1.5 — 2026-05-05

### 新功能
- **儲存原始錄音**：轉錄後自動將音訊檔存入歷史記錄，可在歷史分頁直接重播或下載原始錄音檔
- **大檔案支援**：新增 `packages.txt` 讓 Streamlit Cloud 安裝 ffmpeg，修復 >25 MB 音訊無法自動分割的問題

### 修正
- 修復上傳 >25 MB 檔案時顯示「找不到 ffmpeg」的錯誤（根本原因：Streamlit Cloud 未預裝 ffmpeg，需 `packages.txt` 明確宣告）

---

## v1.4 — 2026-05-05

### 新功能
- **刪除歷史記錄**：每筆記錄新增「🗑」刪除按鈕，刪除後自動更新索引並同步至 localStorage
- **友善錯誤訊息**：將 Groq API 原始錯誤轉換為中文提示
  - 429 音訊秒數超限 → 顯示剩餘等待時間（例：「請等待 12m54s 後再試」）
  - 429 TPM 超限 → 顯示限制說明
  - 413 Token 過長 → 說明原因

---

## v1.3 — 2026-05-05

### 新功能
- **歷史記錄持久化**：使用 `streamlit-javascript` 將歷史記錄存入瀏覽器 localStorage，關閉 app 後重開仍保留

### 修正
- 修復第一次 render 時 `st_javascript` 回傳 `0`（JS 未執行完），導致空陣列覆蓋 localStorage 舊資料的問題
  - 解法：加入 `_history_loaded` 旗標，確認 JS 執行完成後才允許寫入
- 修復 `StreamlitDuplicateElementId`：`render_results` 同頁被呼叫兩次（歷史 + 本次分析）造成 download_button ID 重複
  - 解法：加入 `key_prefix` 參數區分兩個實例

---

## v1.2 — 2026-05-05

### 新功能
- **上傳後自動填入會議標題**：偵測到新檔案時，以檔名（去副檔名）自動填入標題欄，可手動覆蓋
- **轉錄後自動儲存**：不需點「AI 分析」，轉錄完成即存入歷史記錄；AI 分析完成後更新同一筆，不重複新增
- **歷史記錄支援純逐字稿**：未分析的記錄以「（逐字稿）」標註，可單獨查看與下載

### 修正
- 修復 `StreamlitAPIException`：sidebar widget 渲染後無法再修改同名 session state key
  - 解法：用 `_pending_title` 中繼 key，在 sidebar 渲染前套用，再觸發 rerun

---

## v1.1 — 2026-05-05

### 新功能
- **Groq 413 Token 超限保護**：逐字稿超過 12,000 字元時自動截取首尾（前 67% + 後 33%），並在 UI 顯示警告
- `max_tokens` 從 4096 降至 2048，給輸入 Token 更多空間

---

## v1.0 — 初始版本

### 核心功能
- 上傳音訊（mp3 / wav / m4a / aac / ogg / flac / webm），最大 100 MB
- 即時錄音（需 Streamlit ≥ 1.31）
- Groq Whisper Large v3 語音轉錄，支援自動偵測 / 中文 / 英文
- 大檔案自動分割（ffmpeg，每段 8 分鐘）
- 指定發言者（最多 6 人），可編輯逐字稿
- Groq Llama 3.3 70B AI 分析：摘要、主題標籤、Action Items、修正逐字稿
- 歷史記錄（session 內）：查看過去分析結果、下載 .txt / .json
- 全部免費，一個 Groq API Key 搞定轉錄與分析

### 技術架構
| 元件 | 服務 |
|---|---|
| 語音轉錄 | Groq Whisper Large v3 |
| AI 分析 | Groq Llama 3.3 70B Versatile |
| 前端 / 部署 | Streamlit Community Cloud |
| 持久化 | 瀏覽器 localStorage（文字）+ session state（音訊） |
| 原始碼 | GitHub carolkao-fin/meet-transcribe |

### Groq 免費方案限制
| 項目 | 上限 |
|---|---|
| 音訊轉錄（每小時） | 7,200 秒 |
| 分析 Token（每分鐘） | 12,000 TPM |
| 單檔大小 | 25 MB（超過自動分割） |
