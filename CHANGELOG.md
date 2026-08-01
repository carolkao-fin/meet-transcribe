# MeetTranscribe 開發紀錄

**專案**：MeetTranscribe — 免費 AI 會議轉錄與分析工具
**部署**：https://meet-transcribe.streamlit.app
**技術棧**：Streamlit · Groq Whisper · Groq Llama 3.3 70B · Python

---

## v1.8 — 2026-08-01

以既有的人工整理成果（`訪談/必佳訪視_會議紀錄.docx`）為基準，對齊版面與內容結構。

### 改善
- **版面完全對齊參考檔**（逐項回讀比對，7 種段落型態全數相符）
  - 字級：標題 22pt、H1 18pt、H2 14pt、meta 11pt、正文 12pt
  - **修正中文字型**：eastAsia 由 Arial 改為 Microsoft JhengHei。
    Arial 沒有中文字符，原本中文會退回 Word 預設（新細明體）
  - 標題與 H1 加底線分隔；間距對齊（H1 前 18pt/後 8pt、H2 前 12pt/後 4pt、逐字稿段落後 6pt）
  - **自動編號**：H1 為「1. Meeting Summary」，H2 為「一、」「二、」（每個 H1 內重新編號）；
    標題若已自帶編號不會重複加
  - 標題列改為「{會議主題} 會議紀錄」，並加上 meta 行（會議日期／時間／地點／主席／來源檔案）
- **AI prompt 對齊參考檔的內容結構**：Meeting Summary 先總述再分節、Topics 用頓號、
  Action Items 無期限時寫「（期限：未於逐字稿中提及）」、
  Notes 依六類分節（發言者標記／專有名詞統一／錯字修正彙整／待確認項目／數字與代碼／雜訊說明）

### 新功能
- **AI 整理逐字稿**（選填，預設關閉）：補標點、修正明顯辨識錯字並標記【原文：…】、
  依語意標註發言者角色（如「speaker_1（訪視方）」）
  - 先偵測整份逐字稿的角色名稱，再固定帶入每一批，避免各批叫法不一致
  - 分批送出並自動控速（Groq 免費方案 12,000 TPM），過程顯示進度
  - **逐字稿零損失保證**：整理後長度不足原文 60% 視為模型在摘要，該段一律改用原文；
    回應被截斷、單批失敗、中途撞到速率限制，都只保留原文並提示，不會少內容

### 已知限制
- 參考檔中「逐字稿逐行校對、Notes 附行號引用、錯字統一對照表」的深度，
  超出 Groq 免費方案（單次 2,048 output tokens／12,000 TPM）能達到的範圍，
  本工具產出的是同樣結構但較精簡的版本

---

## v1.7.2 — 2026-08-01

### 修正
- **修復「AI 回傳的格式不符預期（缺少 sections）」**
  - 根本原因：舊碼只認 `{"sections": [...]}` 一種形狀，但 Llama 常改用自己的鍵名
    （例如 `{"meeting_minutes": {...}}`）、直接回陣列、或回 `{段落標題: 內容}` 對應表，
    這些其實都是可用的內容，卻被當成失敗
  - 改以 Groq **JSON 模式**（`response_format={"type":"json_object"}`）呼叫，
    模型不支援時自動退回一般模式
  - 新增回傳形狀正規化：接受頂層陣列、其他鍵名包裝、單鍵巢狀、`{標題: 內容}` 對應表；
    blocks 可以是字串、字串陣列（視為條列）、或 `{assignee, task, due}` 物件
    （組成「【負責人】任務（期限：）」）；`title` / `date` 等 metadata 鍵會被略過
  - JSON 擷取改用括號配對掃描，正確處理 code fence、前後贅字，
    以及字串內含 `}`、跳脫引號的情況
  - 仍然失敗時**自動重試一次**（把模型自己的輸出貼回去要求改正）；
    兩次都失敗才報錯，並附上模型實際回傳的開頭 400 字，不再只說「格式不符預期」
- 新增回應被截斷（`finish_reason == "length"`）的專屬提示，不再讓它以 JSON 解析錯誤呈現

---

## v1.7.1 — 2026-08-01

### 改善
- **短句逐字稿自動合併成段落**：本專案「下載逐字稿」輸出的是 Whisper 的 segment 切法，
  一句一行、每行都帶發言者前綴（實測一場 40 分鐘訪談 = 991 行）。直接轉 Word 會變成
  991 個各掛一次「speaker_1：」的單句段落
  - 合併連續同一發言者的句子，長度以 250 字元為目標，**只在原始行邊界斷段**
    （那是 Whisper 的語音停頓點，從那裡斷不會切在句子中間）
  - 不靠句末標點切段：Whisper 中文輸出常整份沒有標點，實測 991 行只有零星逗號
  - 續段不重複印發言者名稱
  - 實測 991 行 → 45 段，段落長度 57–251 字元，內容零遺失
- **語音停頓以空白標示**：合併時片段之間留一個半形空白，不自行補逗號句號——
  斷句會改變語意，那是發言者的話，不應由工具代為決定
- **大幅降低 AI 字元用量**：移除重複的發言者前綴後，同一份逐字稿從 21,082 字元降到
  10,168 字元（前綴本身佔了 11,891 字元），**從超過 12,000 上限變成完全不需截斷**
- 單一發言者時提示 Whisper 不做語者分離，需自行在 .txt 改名
- 字元數統計改以實際送給 AI 的內容計算，不再用原始檔案大小

---

## v1.7 — 2026-08-01

### 新功能
- **逐字稿轉 Word**：新增「📄 逐字稿轉 Word」分頁，可直接上傳已轉好的 `.txt` 逐字稿，
  產出正式會議紀錄 `.docx`，不需再跑一次語音轉錄
  - 逐字稿解析：支援「發言者：內容」與行首時間戳（`[00:01:23]`），
    連續斷行併入同段、空行分段；空行後未標記發言者的內容自成一段（不沿用上一位發言者，避免誤植）
  - 編碼容錯：依序嘗試 UTF-8 / UTF-8-BOM / CP950（Windows 記事本另存的 Big5）
  - **預設格式**：未上傳模板時採用「會議行動轉譯官」skill 的五段結構
    （Meeting Summary / Topics / Action Items / Notes / Transcript）
  - **自訂格式**：可上傳 `.txt` / `.md` / `.docx` 範本，依範本欄位與順序填寫；
    模板有欄位但逐字稿無對應資訊時填「——」，不捏造
  - **忠實還原**：AI prompt 明訂只呈現逐字稿實際出現的資訊，禁止推斷補充、禁止更改立場
  - **Transcript 不經 LLM**：完整逐字稿由程式直接寫入 docx，
    長逐字稿只有摘要段落受 12,000 字元上限影響，Transcript 一律完整
  - 可取消「AI 整理」只做格式轉檔，此時**不需要 Groq API Key**
- **.docx 樣式**（對應 SeaSalt.AI 規範）：A4、四邊 1 inch 邊距、Arial（含 eastAsia 字型設定）、
  主色 Teal `#00897B`、H1 粗體加底線分隔、H2 粗體、正文 `#212121` 12pt、
  發言者名稱 Teal 粗體、條列使用 Word numbering（`List Bullet`）而非手動符號
- 檔名格式：`{會議主題}_{YYYYMMDD}_會議紀錄.docx`（路徑非法字元自動置換）

### 技術
- 新增依賴 `python-docx>=1.1.0`
- 上傳檔一律以 `getvalue()` 讀取：`UploadedFile` 跨 rerun 是同一個物件，
  用 `read()` 會在第二次 rerun 讀到空內容

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
