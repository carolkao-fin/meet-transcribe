# MeetTranscribe 開發紀錄

**專案**：MeetTranscribe — 免費 AI 會議轉錄與分析工具
**部署**：https://meet-transcribe.streamlit.app
**技術棧**：Streamlit · Groq Whisper · Groq Llama 3.3 70B · Python

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
