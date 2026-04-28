"""
MeetTranscribe — Streamlit 版（使用 Groq，完全免費）
上傳音檔（最大 100 MB）→ Groq Whisper 轉錄 → 指定發言者 → Groq Llama 分析
"""

import base64
import json
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from streamlit_javascript import st_javascript

# ── 頁面設定 ───────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MeetTranscribe",
    page_icon="🎙",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.hero {
    background: linear-gradient(135deg, #1BA8A8 0%, #138A8A 100%);
    color: white; border-radius: 14px;
    padding: 1.4rem 2rem; margin-bottom: 1.5rem;
}
.hero h1 { color: white; margin: 0; font-size: 1.9rem; font-weight: 800; }
.hero p  { color: rgba(255,255,255,.85); margin: .3rem 0 0; font-size: .95rem; }
.res-header {
    background: linear-gradient(135deg, #1BA8A8 0%, #138A8A 100%);
    color: white; border-radius: 12px;
    padding: 1.4rem 1.6rem; margin-bottom: 1.2rem;
}
.res-header h2 { color: white; margin: 0 0 .4rem; font-size: 1.4rem; }
.res-header .meta { font-size: .88rem; opacity: .88; }
.pbadge {
    background: rgba(255,255,255,.22);
    padding: .15rem .65rem; border-radius: 20px;
    font-size: .8rem; font-weight: 700;
    display: inline-block; margin: .15rem .2rem 0 0;
}
.sec-title {
    color: #1BA8A8; font-size: .82rem; font-weight: 800;
    text-transform: uppercase; letter-spacing: .6px;
    border-bottom: 2px solid #e0f5f5;
    padding-bottom: .35rem; margin: 1.4rem 0 .7rem;
}
.sum-h   { font-weight: 700; font-size: .97rem; margin: .9rem 0 .25rem; color: #1f2937; }
.sum-ov  { color: #6b7280; font-size: .9rem; margin-bottom: .4rem; line-height: 1.62; }
.bullet  { font-size: .9rem; padding-left: 1.1rem; position: relative; margin: .22rem 0; line-height: 1.56; }
.bullet::before { content:"·"; position:absolute; left:0; color:#1BA8A8; font-weight:700; font-size:1.1rem; }
.ttag {
    background: #e0f5f5; color: #138A8A;
    padding: .22rem .75rem; border-radius: 20px;
    font-size: .85rem; font-weight: 600;
    display: inline-block; margin: .2rem .2rem 0 0;
}
.ai-title { font-weight: 700; font-size: .95rem; margin: .9rem 0 .2rem; }
.ai-desc  { color: #6b7280; font-size: .85rem; margin-bottom: .45rem; }
.ai-item  { font-size: .9rem; padding: .18rem 0 .18rem 1.1rem; position: relative; line-height:1.55; }
.ai-item::before { content:"·"; position:absolute; left:0; color:#1BA8A8; font-weight:700; }
.ai-who   { font-weight: 700; color: #138A8A; }
.tr-row   { display:flex; gap:.75rem; padding:.28rem 0; font-size:.9rem; line-height:1.57; }
.tr-spk   { font-weight:700; min-width:90px; flex-shrink:0; color:#1BA8A8; }
.hist-card {
    border: 1.5px solid #e5e7eb; border-radius: 10px;
    padding: .75rem 1rem; margin-bottom: .5rem; background: white;
}
.hist-card.active { border-color: #1BA8A8; background: #e0f5f5; }
.hist-title { font-weight: 700; font-size: .95rem; color: #1f2937; }
.hist-meta  { font-size: .78rem; color: #9ca3af; margin-top: .2rem; }
</style>
""", unsafe_allow_html=True)

# ── Session state ──────────────────────────────────────────────────────────────
for k, v in {
    "transcript":        [],
    "analysis":          None,
    "meeting_info":      {},
    "history":           [],
    "hist_idx":          None,
    "current_record_id": None,
    "_last_uploaded":    "",
    "_history_loaded":   False,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

if "meeting_title_key" not in st.session_state:
    st.session_state["meeting_title_key"] = f"會議記錄 {datetime.now():%Y-%m-%d}"

# 若上次 rerun 有待套用的檔名，在 sidebar 渲染前先更新 widget key
if st.session_state.get("_pending_title"):
    st.session_state["meeting_title_key"] = st.session_state.pop("_pending_title")

# ── 從 localStorage 載入歷史記錄（每個 session 只做一次）────────────────────────
if not st.session_state["_history_loaded"]:
    _raw = st_javascript('localStorage.getItem("meetTranscribeHistory")')
    if _raw and _raw != 0 and _raw not in ("null", "undefined"):
        try:
            _loaded = json.loads(_raw)
            if isinstance(_loaded, list) and _loaded:
                st.session_state.history = _loaded
        except Exception:
            pass
    if _raw != 0:          # 0 表示 JS 還沒執行完，等下次 rerun 再標記
        st.session_state["_history_loaded"] = True


def _persist_history() -> None:
    """將目前歷史記錄同步至瀏覽器 localStorage（音訊檔案不存入，避免超過大小限制）。"""
    slim = [{k: v for k, v in r.items() if k not in ("audio_bytes",)} for r in st.session_state.history]
    data = json.dumps(slim, ensure_ascii=False)
    components.html(
        f'<script>localStorage.setItem("meetTranscribeHistory",{json.dumps(data)});</script>',
        height=0,
    )

# ── 常數 ───────────────────────────────────────────────────────────────────────
LANG_MAP      = {"自動偵測": None, "中文 (zh)": "zh", "英文 (en)": "en"}
WHISPER_MAX   = 24 * 1_048_576          # 24 MB
WHISPER_MODEL = "whisper-large-v3"
CHAT_MODEL    = "llama-3.3-70b-versatile"

# Groq 免費方案 TPM 上限 ~12,000 tokens；
# prompt 固定部分約 500 tokens，max_tokens=2048，故逐字稿最多保留 ~9,000 tokens。
# 中文約 1.5 chars/token → 安全字元上限取 12,000 chars
MAX_TRANSCRIPT_CHARS = 12_000

# ── Helpers ────────────────────────────────────────────────────────────────────
def secs_hms(s: float) -> str:
    s = int(s)
    return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"


def _friendly_error(e: Exception) -> str:
    """將 Groq API 錯誤轉成友善的中文訊息。"""
    import re
    msg = str(e)
    # 429 rate limit
    if "429" in msg or "rate_limit_exceeded" in msg:
        wait = re.search(r"try again in\s+([\d]+m[\d.]+s|[\d.]+s|[\d]+m)", msg)
        wait_str = f"請等待 **{wait.group(1)}** 後再試。" if wait else "請稍後再試。"
        if "ASPH" in msg or "seconds of audio" in msg:
            return f"⏱ Groq 免費方案每小時音訊轉錄量已達上限（7,200 秒）。{wait_str}"
        if "TPM" in msg or "tokens per minute" in msg:
            return f"⏱ Groq 免費方案每分鐘 Token 用量已達上限。{wait_str}"
        return f"⏱ Groq API 請求次數已達上限。{wait_str}"
    # 413 too large
    if "413" in msg:
        return "📏 逐字稿過長，已超過 Groq 模型的 Token 上限，請縮短錄音後再試。"
    return msg


def _ffmpeg_ok() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


def _audio_duration(path: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path],
            capture_output=True, text=True, timeout=30,
        )
        info = json.loads(r.stdout)
        return next(
            (float(s["duration"]) for s in info.get("streams", []) if "duration" in s), 0.0
        )
    except Exception:
        return 0.0


def _split_audio(src: str, chunk_min: int = 8) -> list | None:
    if not _ffmpeg_ok():
        return None
    dur = _audio_duration(src)
    if not dur:
        return None
    chunks, step, t = [], chunk_min * 60, 0.0
    while t < dur:
        length = min(step, dur - t)
        out = src + f"_c{int(t)}.mp3"
        subprocess.run(
            ["ffmpeg", "-y", "-i", src,
             "-ss", str(t), "-t", str(length),
             "-ac", "1", "-ar", "16000", "-ab", "48k", out],
            capture_output=True, timeout=300,
        )
        if Path(out).exists():
            chunks.append((out, length))
        t += length
    return chunks or None


def _call_whisper(client, path: str, lc: str | None) -> list[dict]:
    with open(path, "rb") as fh:
        r = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=fh,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
            language=lc,
        )
    out = []
    for s in getattr(r, "segments", None) or []:
        start = float(s["start"] if isinstance(s, dict) else s.start)
        text  = (s["text"]  if isinstance(s, dict) else getattr(s, "text", "") or "").strip()
        if text:
            out.append({"start": start, "text": text})
    if not out and getattr(r, "text", None):
        out.append({"start": 0.0, "text": r.text.strip()})
    return out


def transcribe_audio(data: bytes, filename: str, groq_key: str, lc: str | None) -> list[dict]:
    from groq import Groq
    client = Groq(api_key=groq_key)
    suffix = Path(filename).suffix.lower() or ".mp3"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        size = os.path.getsize(tmp_path)
        if size <= WHISPER_MAX:
            return _call_whisper(client, tmp_path, lc)

        chunks = _split_audio(tmp_path)
        if not chunks:
            raise ValueError(
                f"檔案 {size/1_048_576:.1f} MB 超過 25 MB，且找不到 ffmpeg 無法自動分割。\n"
                "請安裝 ffmpeg 或先壓縮音訊後再上傳。"
            )
        segs, offset = [], 0.0
        pbar = st.progress(0, text="分割並轉錄中…")
        for i, (cp, dur) in enumerate(chunks):
            pbar.progress((i + 1) / len(chunks), text=f"轉錄第 {i+1}/{len(chunks)} 段…")
            for s in _call_whisper(client, cp, lc):
                segs.append({"start": s["start"] + offset, "text": s["text"]})
            os.unlink(cp)
            offset += dur
        pbar.empty()
        return segs
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def analyze_with_groq(transcript: list, meeting_info: dict, groq_key: str) -> dict:
    from groq import Groq
    client = Groq(api_key=groq_key)

    txt      = "\n".join(f"{e['speaker']}: {e['text']}" for e in transcript)
    has_zh   = any("\u4e00" <= c <= "\u9fff" for e in transcript for c in e["text"])
    out_lang = "繁體中文" if has_zh else "English"

    # ── 超長逐字稿截斷（保留前 2/3、後 1/3，避免 TPM 超限）──────────────────
    truncated = False
    if len(txt) > MAX_TRANSCRIPT_CHARS:
        keep_head = int(MAX_TRANSCRIPT_CHARS * 0.67)
        keep_tail = MAX_TRANSCRIPT_CHARS - keep_head
        txt = txt[:keep_head] + f"\n\n… [逐字稿過長，中間部分已略去] …\n\n" + txt[-keep_tail:]
        truncated = True

    prompt = f"""你是一個專業的會議記錄分析師。請分析以下會議逐字稿，並以 {out_lang} 輸出結構化的分析結果。{"（注意：逐字稿因過長已截取首尾，請根據現有內容盡力分析。）" if truncated else ""}

會議資訊：
- 標題：{meeting_info.get("title", "未命名會議")}
- 日期：{meeting_info.get("date", "")}
- 參與者：{", ".join(meeting_info.get("participants", []))}

逐字稿：
{txt}

請根據上下文修正專業術語、公司名稱、產品名稱、人名等用詞。

只回傳一個合法的 JSON 物件，不要包含 markdown 或其他文字：

{{
  "summary": [
    {{
      "title": "### 小節標題",
      "overview": "這一小節的概述段落",
      "bullets": ["- speaker_X 說明了...", "- 雙方討論了...", "- 最終確認..."]
    }}
  ],
  "topics": ["主題標籤1", "主題標籤2"],
  "action_items": [
    {{
      "group_title": "### 行動任務群組標題",
      "description": "這組任務的說明",
      "items": [{{"assignee": "負責人", "task": "具體任務"}}]
    }}
  ],
  "corrected_transcript": [{{"speaker": "speaker_1", "text": "修正後文字"}}]
}}

要求：summary 2–4 小節、每節 3–6 要點並標明發言者；action_items 指明負責人；topics 2–4 個標籤。"""

    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2048,
        temperature=0.3,
    )
    text = resp.choices[0].message.content.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif text.startswith("```"):
        text = text.split("```")[1].split("```")[0].strip()
    return json.loads(text)


def save_to_history(transcript, analysis, meeting_info, record_id=None,
                    audio_bytes=None, audio_filename=None) -> str:
    """新增或更新歷史記錄，回傳 record id。"""
    if record_id:
        for r in st.session_state.history:
            if r["id"] == record_id:
                r["transcript"]   = transcript
                r["analysis"]     = analysis
                r["meeting_info"] = meeting_info
                r["participants"] = meeting_info.get("participants", [])
                if audio_bytes is not None:
                    r["audio_bytes"]    = audio_bytes
                    r["audio_filename"] = audio_filename or "recording"
                return record_id

    record = {
        "id":             datetime.now().strftime("%Y%m%d_%H%M%S"),
        "title":          meeting_info.get("title", "未命名會議"),
        "date":           meeting_info.get("date", ""),
        "participants":   meeting_info.get("participants", []),
        "transcript":     transcript,
        "analysis":       analysis,
        "meeting_info":   meeting_info,
        "audio_bytes":    audio_bytes,
        "audio_filename": audio_filename or "recording",
    }
    st.session_state.history.insert(0, record)
    return record["id"]


def plain_text(data: dict, info: dict, transcript: list) -> str:
    lines = [
        info.get("title", "會議記錄"),
        f"日期：{info.get('date', '')}",
        f"參與者：{', '.join(f'[{p}]' for p in info.get('participants', []))}",
        "", "Meeting Summary", "=" * 40,
    ]
    for sec in data.get("summary", []):
        lines += [sec.get("title", ""), sec.get("overview", "")]
        lines += sec.get("bullets", [])
        lines.append("")
    lines += ["Topics", ", ".join(data.get("topics", [])), "", "Action Items", "=" * 40]
    for grp in data.get("action_items", []):
        lines += [grp.get("group_title", ""), grp.get("description", "")]
        lines += [f"- {i['assignee']} {i['task']}" for i in grp.get("items", [])]
        lines.append("")
    lines += ["Transcript", "=" * 40]
    src = data.get("corrected_transcript") or transcript
    lines += [f"{e['speaker']}: {e['text']}" for e in src]
    return "\n".join(lines)


def render_results(data: dict, info: dict, transcript: list, key_prefix: str = "main",
                   audio_bytes: bytes | None = None, audio_filename: str = "recording") -> None:
    participants = info.get("participants", [])
    badges = " ".join(f'<span class="pbadge">[{p}]</span>' for p in participants)
    st.markdown(
        f'<div class="res-header"><h2>{info.get("title","會議記錄")}</h2>'
        f'<div class="meta">🕐 {info.get("date","")} &nbsp;·&nbsp; 參與者：{badges}</div></div>',
        unsafe_allow_html=True,
    )
    if audio_bytes:
        st.markdown('<div class="sec-title">🎵 原始錄音</div>', unsafe_allow_html=True)
        st.audio(audio_bytes)
        st.download_button("⬇ 下載原始錄音", audio_bytes, audio_filename,
                           key=f"{key_prefix}_dl_audio")
    if data.get("summary"):
        st.markdown('<div class="sec-title">📋 Meeting Summary</div>', unsafe_allow_html=True)
        for sec in data["summary"]:
            st.markdown(f'<div class="sum-h">### {sec.get("title","").replace("### ","")}</div>', unsafe_allow_html=True)
            if sec.get("overview"):
                st.markdown(f'<div class="sum-ov">{sec["overview"]}</div>', unsafe_allow_html=True)
            for b in sec.get("bullets", []):
                st.markdown(f'<div class="bullet">{b.lstrip("- ")}</div>', unsafe_allow_html=True)
    if data.get("topics"):
        st.markdown('<div class="sec-title">🏷 Topics</div>', unsafe_allow_html=True)
        st.markdown(" ".join(f'<span class="ttag">{t}</span>' for t in data["topics"]), unsafe_allow_html=True)
    if data.get("action_items"):
        st.markdown('<div class="sec-title">✅ Action Items</div>', unsafe_allow_html=True)
        for grp in data["action_items"]:
            st.markdown(f'<div class="ai-title">### {grp.get("group_title","").replace("### ","")}</div>', unsafe_allow_html=True)
            if grp.get("description"):
                st.markdown(f'<div class="ai-desc">{grp["description"]}</div>', unsafe_allow_html=True)
            for item in grp.get("items", []):
                st.markdown(
                    f'<div class="ai-item"><span class="ai-who">{item["assignee"]}</span> {item["task"]}</div>',
                    unsafe_allow_html=True,
                )
    st.markdown('<div class="sec-title">💬 Transcript</div>', unsafe_allow_html=True)
    src = data.get("corrected_transcript") or transcript
    st.markdown(
        "".join(f'<div class="tr-row"><span class="tr-spk">{e["speaker"]}:</span><span>{e["text"]}</span></div>' for e in src),
        unsafe_allow_html=True,
    )
    st.divider()
    fname = info.get("title", "meeting").replace(" ", "_")
    c1, c2, _ = st.columns([2, 2, 4])
    with c1:
        st.download_button("⬇ 下載會議記錄 (.txt)", plain_text(data, info, transcript), f"{fname}.txt",
                           type="primary", key=f"{key_prefix}_dl_txt")
    with c2:
        st.download_button("⬇ 下載 JSON（可重新載入）",
                           json.dumps({"transcript": transcript, "analysis": data, "meeting_info": info},
                                      ensure_ascii=False, indent=2), f"{fname}.json",
                           key=f"{key_prefix}_dl_json")


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎙 MeetTranscribe")
    st.caption("智能會議轉錄 & AI 分析")
    st.divider()

    with st.expander("🔑 API 金鑰", expanded=True):
        groq_key = st.text_input(
            "Groq API Key（免費）",
            type="password", placeholder="gsk_...",
            help="免費申請：console.groq.com，一個 key 同時用於轉錄和分析",
        )
        st.caption("📌 [免費取得 Groq Key](https://console.groq.com) — 用 Google 帳號即可註冊")

    with st.expander("📋 會議資訊", expanded=True):
        meeting_title = st.text_input("標題", key="meeting_title_key")
        language      = st.selectbox("語言", ["自動偵測", "中文 (zh)", "英文 (en)"])

    with st.expander("👤 發言者", expanded=True):
        n_sp = st.number_input("人數", 1, 6, 2, step=1)
        speaker_names = [
            st.text_input(f"發言者 {i+1}", value=f"speaker_{i+1}", key=f"spn{i}")
            for i in range(int(n_sp))
        ]

    st.divider()
    if st.button("🗑 清除重來", use_container_width=True):
        st.session_state.transcript        = []
        st.session_state.analysis          = None
        st.session_state.meeting_info      = {}
        st.session_state.current_record_id = None
        st.session_state["_last_uploaded"] = ""
        st.session_state["_pending_title"] = f"會議記錄 {datetime.now():%Y-%m-%d}"
        st.rerun()

# ── Hero ───────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
  <h1>🎙 MeetTranscribe</h1>
  <p>上傳音訊 · Groq Whisper 免費轉錄 · 指定發言者 · Llama AI 免費分析 · 一個 Key 搞定所有功能</p>
</div>
""", unsafe_allow_html=True)

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_up, tab_rec, tab_hist = st.tabs(["📁 上傳音檔", "🎤 即時錄音", "📚 歷史記錄"])

# ── Tab 1: Upload ──────────────────────────────────────────────────────────────
with tab_up:
    st.markdown("支援格式：**mp3 · wav · m4a · aac · ogg · flac · webm**　｜　最大 **100 MB**")
    uploaded = st.file_uploader(
        "拖曳音訊至此，或點擊選擇",
        type=["mp3", "wav", "m4a", "aac", "ogg", "flac", "webm"],
        label_visibility="collapsed",
    )
    if uploaded:
        if st.session_state["_last_uploaded"] != uploaded.name:
            st.session_state["_last_uploaded"] = uploaded.name
            st.session_state["_pending_title"] = Path(uploaded.name).stem
            st.rerun()
        st.audio(uploaded)
        col_info, col_btn = st.columns([5, 1])
        with col_info:
            st.caption(f"檔名：{uploaded.name}　｜　大小：{uploaded.size/1_048_576:.1f} MB")
        with col_btn:
            go = st.button("開始轉錄 →", type="primary", use_container_width=True)
        if go:
            if not groq_key:
                st.error("請在左側輸入 Groq API Key（免費申請：console.groq.com）")
            else:
                with st.spinner("Groq Whisper 轉錄中，請稍候…"):
                    try:
                        audio_data = uploaded.read()
                        segs = transcribe_audio(audio_data, uploaded.name, groq_key, LANG_MAP[language])
                        entries = [
                            {"speaker": speaker_names[0], "text": s["text"],
                             "displayTime": secs_hms(s["start"]), "rawTime": int(s["start"] * 1000)}
                            for s in segs
                        ]
                        info = {
                            "title":        meeting_title,
                            "date":         datetime.now().strftime("%Y/%m/%d %H:%M"),
                            "participants": [speaker_names[0]],
                        }
                        st.session_state.transcript        = entries
                        st.session_state.analysis          = None
                        st.session_state.meeting_info      = info
                        st.session_state.current_record_id = save_to_history(
                            entries, None, info,
                            audio_bytes=audio_data, audio_filename=uploaded.name,
                        )
                        st.success(f"轉錄完成！共 {len(segs)} 段，已自動儲存至歷史記錄。")
                        st.rerun()
                    except Exception as e:
                        st.error(_friendly_error(e))

# ── Tab 2: Record ──────────────────────────────────────────────────────────────
with tab_rec:
    st.info("💡 點擊麥克風錄音，完成後點「轉錄錄音」。需要 Groq API Key。")
    try:
        audio_val = st.audio_input("點擊麥克風開始錄音")
        if audio_val:
            _, col_btn2 = st.columns([5, 1])
            with col_btn2:
                go_rec = st.button("轉錄錄音 →", type="primary", use_container_width=True)
            if go_rec:
                if not groq_key:
                    st.error("請輸入 Groq API Key")
                else:
                    with st.spinner("Groq Whisper 轉錄中…"):
                        try:
                            audio_data = audio_val.read()
                            segs = transcribe_audio(audio_data, "recording.wav", groq_key, LANG_MAP[language])
                            entries = [
                                {"speaker": speaker_names[0], "text": s["text"],
                                 "displayTime": secs_hms(s["start"]), "rawTime": int(s["start"] * 1000)}
                                for s in segs
                            ]
                            info = {
                                "title":        meeting_title,
                                "date":         datetime.now().strftime("%Y/%m/%d %H:%M"),
                                "participants": [speaker_names[0]],
                            }
                            st.session_state.transcript        = entries
                            st.session_state.analysis          = None
                            st.session_state.meeting_info      = info
                            st.session_state.current_record_id = save_to_history(
                                entries, None, info,
                                audio_bytes=audio_data, audio_filename="recording.wav",
                            )
                            st.success("轉錄完成！已自動儲存至歷史記錄。")
                            st.rerun()
                        except Exception as e:
                            st.error(_friendly_error(e))
    except Exception:
        st.warning("即時錄音需要 Streamlit ≥ 1.31，請改用「上傳音檔」分頁。")

# ── Tab 3: History ─────────────────────────────────────────────────────────────
with tab_hist:
    st.markdown("**載入過去儲存的 JSON 紀錄**")
    loaded_file = st.file_uploader("上傳 .json 檔案", type=["json"],
                                   key="hist_upload", label_visibility="collapsed")
    if loaded_file:
        try:
            rec = json.loads(loaded_file.read().decode("utf-8"))
            if all(k in rec for k in ("transcript", "analysis", "meeting_info")):
                save_to_history(rec["transcript"], rec["analysis"], rec["meeting_info"])
                st.success(f"已載入：{rec['meeting_info'].get('title','')}")
                st.rerun()
            else:
                st.error("格式不正確，請上傳由本系統產生的 .json 檔案")
        except Exception as e:
            st.error(f"載入失敗：{e}")

    st.divider()
    history = st.session_state.history
    if not history:
        st.info("📭 還沒有歷史紀錄。完成 AI 分析後自動儲存，或上傳 .json 檔案。")
    else:
        st.markdown(f"**共 {len(history)} 筆紀錄**")
        col_list, col_detail = st.columns([1, 2])
        with col_list:
            for i, rec in enumerate(history):
                is_active = (st.session_state.hist_idx == i)
                tag = "" if rec.get("analysis") else ' <span style="font-size:.75rem;color:#9ca3af;">（逐字稿）</span>'
                st.markdown(
                    f'<div class="hist-card {"active" if is_active else ""}">'
                    f'<div class="hist-title">{rec["title"]}{tag}</div>'
                    f'<div class="hist-meta">{rec["date"]}</div>'
                    f'<div class="hist-meta">{" · ".join(rec.get("participants", []))}</div></div>',
                    unsafe_allow_html=True,
                )
                c_view, c_del = st.columns(2)
                with c_view:
                    if st.button("查看", key=f"view_{i}", use_container_width=True):
                        st.session_state.hist_idx = i
                        st.rerun()
                with c_del:
                    if st.button("🗑", key=f"del_{i}", use_container_width=True, help="刪除此記錄"):
                        st.session_state.history.pop(i)
                        if st.session_state.hist_idx == i:
                            st.session_state.hist_idx = None
                        elif st.session_state.hist_idx is not None and st.session_state.hist_idx > i:
                            st.session_state.hist_idx -= 1
                        st.rerun()
        with col_detail:
            idx = st.session_state.hist_idx
            if idx is not None and idx < len(history):
                rec = history[idx]
                ab = rec.get("audio_bytes")
                af = rec.get("audio_filename", "recording")
                if rec["analysis"] is None:
                    st.info("📝 此記錄尚未進行 AI 分析，僅顯示逐字稿。")
                    info = rec["meeting_info"]
                    st.markdown(f"**{info.get('title','')}**　{info.get('date','')}")
                    if ab:
                        st.audio(ab)
                        st.download_button("⬇ 下載原始錄音", ab, af,
                                           key=f"hist_{idx}_dl_audio_raw")
                    fname = info.get("title", "transcript").replace(" ", "_")
                    st.download_button(
                        "⬇ 下載逐字稿",
                        "\n".join(f"{e['speaker']}: {e['text']}" for e in rec["transcript"]),
                        f"{fname}.txt", key=f"hist_{idx}_dl_txt_raw",
                    )
                    for e in rec["transcript"]:
                        st.markdown(
                            f'<div class="tr-row"><span class="tr-spk">{e["speaker"]}:</span>'
                            f'<span>{e["text"]}</span></div>',
                            unsafe_allow_html=True,
                        )
                else:
                    render_results(rec["analysis"], rec["meeting_info"], rec["transcript"],
                                   key_prefix=f"hist_{idx}", audio_bytes=ab, audio_filename=af)
            else:
                st.info("← 點擊左側紀錄查看內容")

# ── Transcript editor ──────────────────────────────────────────────────────────
if st.session_state.transcript:
    st.divider()
    with st.expander(
        f"📝 逐字稿編輯　（{len(st.session_state.transcript)} 段，可修改文字 / 指定發言者）",
        expanded=True,
    ):
        for i, entry in enumerate(st.session_state.transcript):
            c_sp, c_time, c_txt = st.columns([2, 1, 7])
            with c_sp:
                idx = speaker_names.index(entry["speaker"]) if entry["speaker"] in speaker_names else 0
                st.session_state.transcript[i]["speaker"] = st.selectbox(
                    "sp", speaker_names, index=idx, key=f"sel{i}", label_visibility="collapsed")
            with c_time:
                st.markdown(
                    f"<p style='color:#9ca3af;font-size:.8rem;padding-top:.55rem'>{entry['displayTime']}</p>",
                    unsafe_allow_html=True)
            with c_txt:
                st.session_state.transcript[i]["text"] = st.text_input(
                    "txt", value=entry["text"], key=f"txt{i}", label_visibility="collapsed")

    c_ana, c_dl, _ = st.columns([2, 2, 4])
    with c_ana:
        do_analyze = st.button("🤖 AI 分析", type="primary", use_container_width=True)
    with c_dl:
        st.download_button(
            "⬇ 下載逐字稿",
            "\n".join(f"{e['speaker']}: {e['text']}" for e in st.session_state.transcript),
            f"transcript_{datetime.now():%Y%m%d_%H%M}.txt",
            use_container_width=True,
        )

    if do_analyze:
        if not groq_key:
            st.error("請輸入 Groq API Key")
        else:
            full_txt = "\n".join(e["text"] for e in st.session_state.transcript)
            if len(full_txt) > MAX_TRANSCRIPT_CHARS:
                st.warning(
                    f"⚠️ 逐字稿共 {len(full_txt):,} 字元，超過 Groq 免費方案上限（{MAX_TRANSCRIPT_CHARS:,} 字元）。"
                    " 系統將自動保留首尾最重要的片段進行分析。如需完整分析，請升級至 Groq Dev Tier。"
                )
            with st.spinner("Llama 分析中，請稍候…"):
                try:
                    info = {
                        "title":        meeting_title,
                        "date":         datetime.now().strftime("%Y/%m/%d %H:%M"),
                        "participants": list(dict.fromkeys(e["speaker"] for e in st.session_state.transcript)),
                    }
                    result = analyze_with_groq(st.session_state.transcript, info, groq_key)
                    st.session_state.analysis          = result
                    st.session_state.meeting_info      = info
                    st.session_state.current_record_id = save_to_history(
                        st.session_state.transcript, result, info,
                        st.session_state.current_record_id,
                    )
                    st.rerun()
                except Exception as e:
                    st.error(_friendly_error(e))

# ── Current results ────────────────────────────────────────────────────────────
if st.session_state.analysis:
    st.divider()
    st.markdown('<div class="sec-title">📋 本次分析結果</div>', unsafe_allow_html=True)
    render_results(
        st.session_state.analysis,
        st.session_state.meeting_info,
        st.session_state.transcript,
    )

# ── 每次 run 結束時將歷史記錄同步至 localStorage ───────────────────────────────
# 必須等 _history_loaded=True 才能寫入，否則第一次 render JS 尚未執行（回傳 0），
# history 還是空的，會把 localStorage 的舊資料覆蓋掉。
if st.session_state["_history_loaded"]:
    _persist_history()
