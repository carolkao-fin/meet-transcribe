"""
MeetTranscribe — Streamlit 版（使用 Google AI Studio / Gemini）
上傳音檔（最大 2 GB）→ Gemini 轉錄 → 指定發言者 → Gemini 分析
一個 API Key 搞定所有功能，完全免費。
"""

import json
import os
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

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
.bullet  {
    font-size: .9rem; padding-left: 1.1rem;
    position: relative; margin: .22rem 0; line-height: 1.56;
}
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
    padding: .75rem 1rem; margin-bottom: .5rem;
    background: white;
}
.hist-card.active { border-color: #1BA8A8; background: #e0f5f5; }
.hist-title { font-weight: 700; font-size: .95rem; color: #1f2937; }
.hist-meta  { font-size: .78rem; color: #9ca3af; margin-top: .2rem; }
</style>
""", unsafe_allow_html=True)

# ── Session state ──────────────────────────────────────────────────────────────
for k, v in {
    "transcript":   [],
    "analysis":     None,
    "meeting_info": {},
    "history":      [],
    "hist_idx":     None,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── 常數 ───────────────────────────────────────────────────────────────────────
LANG_MAP  = {"自動偵測": None, "中文 (zh)": "zh", "英文 (en)": "en"}
MODEL     = "gemini-2.0-flash"
MIME_MAP  = {
    ".mp3": "audio/mpeg", ".wav": "audio/wav",
    ".m4a": "audio/mp4",  ".aac": "audio/aac",
    ".ogg": "audio/ogg",  ".flac": "audio/flac",
    ".webm": "audio/webm",
}

# ── Helpers ────────────────────────────────────────────────────────────────────
def secs_hms(s: float) -> str:
    s = int(s)
    return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"


def _gemini_client(api_key: str):
    from google import genai
    return genai.Client(api_key=api_key)


def transcribe_audio(data: bytes, filename: str, api_key: str, lc: str | None) -> list[dict]:
    """上傳音檔到 Gemini File API，取得帶時間戳的逐字稿。"""
    from google import genai

    client = _gemini_client(api_key)
    suffix    = Path(filename).suffix.lower() or ".mp3"
    mime_type = MIME_MAP.get(suffix, "audio/mpeg")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        # 上傳檔案
        status_ph = st.empty()
        status_ph.info("⬆ 上傳音檔至 Gemini…")
        with open(tmp_path, "rb") as fh:
            uploaded = client.files.upload(
                file=fh,
                config={"mime_type": mime_type, "display_name": filename},
            )

        # 等候處理
        status_ph.info("⚙ Gemini 處理音檔中…")
        while uploaded.state.name == "PROCESSING":
            time.sleep(2)
            uploaded = client.files.get(name=uploaded.name)

        if uploaded.state.name == "FAILED":
            raise ValueError("音檔處理失敗，請換一個格式（mp3 / wav / m4a）再試。")

        status_ph.info("✍ Gemini 轉錄中…")

        lang_hint = {"zh": "（語言為繁體中文）", "en": "（the language is English）"}.get(lc or "", "")

        prompt = f"""請轉錄以下音檔{lang_hint}。

輸出格式（每行一段，不要其他說明）：
[MM:SS] 轉錄文字

規則：
- 每隔約 15–30 秒分一段
- 保留原始語言，不要翻譯
- 只輸出轉錄結果"""

        response = client.models.generate_content(
            model=MODEL,
            contents=[
                {"role": "user", "parts": [
                    {"file_data": {"file_uri": uploaded.uri, "mime_type": mime_type}},
                    {"text": prompt},
                ]},
            ],
        )

        # 刪除暫存檔案（Gemini File API 48 小時後自動刪除）
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass

        status_ph.empty()

        # 解析時間戳
        segs = []
        for line in response.text.strip().splitlines():
            m = re.match(r"\[(\d+):(\d+)\]\s*(.+)", line.strip())
            if m:
                mins, secs, text = m.groups()
                start = int(mins) * 60 + int(secs)
                if text.strip():
                    segs.append({"start": float(start), "text": text.strip()})

        # 若 Gemini 沒有輸出時間戳，視為一整段
        if not segs and response.text.strip():
            segs = [{"start": 0.0, "text": response.text.strip()}]

        return segs

    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def analyze_with_gemini(transcript: list, meeting_info: dict, api_key: str) -> dict:
    """用 Gemini 分析逐字稿，回傳結構化 JSON。"""
    client = _gemini_client(api_key)

    txt      = "\n".join(f"{e['speaker']}: {e['text']}" for e in transcript)
    has_zh   = any("\u4e00" <= c <= "\u9fff" for e in transcript for c in e["text"])
    out_lang = "繁體中文" if has_zh else "English"

    prompt = f"""你是一個專業的會議記錄分析師。請分析以下會議逐字稿，並以 {out_lang} 輸出結構化的分析結果。

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

    response = client.models.generate_content(
        model=MODEL,
        contents=[{"role": "user", "parts": [{"text": prompt}]}],
    )

    text = response.text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif text.startswith("```"):
        text = text.split("```")[1].split("```")[0].strip()
    return json.loads(text)


def save_to_history(transcript, analysis, meeting_info):
    record = {
        "id":           datetime.now().strftime("%Y%m%d_%H%M%S"),
        "title":        meeting_info.get("title", "未命名會議"),
        "date":         meeting_info.get("date", ""),
        "participants": meeting_info.get("participants", []),
        "transcript":   transcript,
        "analysis":     analysis,
        "meeting_info": meeting_info,
    }
    key = (record["title"], record["date"])
    if not any((r["title"], r["date"]) == key for r in st.session_state.history):
        st.session_state.history.insert(0, record)


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


def render_results(data: dict, info: dict, transcript: list) -> None:
    participants = info.get("participants", [])
    badges = " ".join(f'<span class="pbadge">[{p}]</span>' for p in participants)
    st.markdown(
        f'<div class="res-header">'
        f'<h2>{info.get("title","會議記錄")}</h2>'
        f'<div class="meta">🕐 {info.get("date","")} &nbsp;·&nbsp; 參與者：{badges}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
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
        "".join(
            f'<div class="tr-row"><span class="tr-spk">{e["speaker"]}:</span><span>{e["text"]}</span></div>'
            for e in src
        ),
        unsafe_allow_html=True,
    )

    st.divider()
    fname = info.get("title", "meeting").replace(" ", "_")
    c1, c2, _ = st.columns([2, 2, 4])
    with c1:
        st.download_button("⬇ 下載會議記錄 (.txt)", plain_text(data, info, transcript),
                           f"{fname}.txt", type="primary")
    with c2:
        st.download_button("⬇ 下載 JSON（可重新載入）",
                           json.dumps({"transcript": transcript, "analysis": data,
                                       "meeting_info": info}, ensure_ascii=False, indent=2),
                           f"{fname}.json")


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎙 MeetTranscribe")
    st.caption("智能會議轉錄 & AI 分析")
    st.divider()

    with st.expander("🔑 API 金鑰", expanded=True):
        api_key = st.text_input(
            "Google AI Studio API Key",
            type="password",
            placeholder="AIza...",
            help="免費取得：aistudio.google.com → Get API key",
        )
        st.caption("📌 [免費取得 API Key](https://aistudio.google.com/apikey)　一個 Key 搞定轉錄 + 分析")

    with st.expander("📋 會議資訊", expanded=True):
        meeting_title = st.text_input("標題", value=f"會議記錄 {datetime.now():%Y-%m-%d}")
        language      = st.selectbox("語言", ["自動偵測", "中文 (zh)", "英文 (en)"])

    with st.expander("👤 發言者", expanded=True):
        n_sp = st.number_input("人數", 1, 6, 2, step=1)
        speaker_names = [
            st.text_input(f"發言者 {i+1}", value=f"speaker_{i+1}", key=f"spn{i}")
            for i in range(int(n_sp))
        ]

    st.divider()
    if st.button("🗑 清除重來", use_container_width=True):
        st.session_state.transcript   = []
        st.session_state.analysis     = None
        st.session_state.meeting_info = {}
        st.rerun()

# ── Hero ───────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
  <h1>🎙 MeetTranscribe</h1>
  <p>上傳音訊 · Gemini 免費轉錄（最大 2 GB）· 指定發言者 · Gemini AI 分析 · 一個 Key 搞定所有功能</p>
</div>
""", unsafe_allow_html=True)

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_up, tab_rec, tab_hist = st.tabs(["📁 上傳音檔", "🎤 即時錄音", "📚 歷史記錄"])

# ── Tab 1: Upload ──────────────────────────────────────────────────────────────
with tab_up:
    st.markdown("支援格式：**mp3 · wav · m4a · aac · ogg · flac · webm**　｜　最大 **100 MB**（Streamlit 限制；Gemini 本身支援 2 GB）")
    uploaded = st.file_uploader(
        "拖曳音訊至此，或點擊選擇",
        type=["mp3", "wav", "m4a", "aac", "ogg", "flac", "webm"],
        label_visibility="collapsed",
    )
    if uploaded:
        st.audio(uploaded)
        col_info, col_btn = st.columns([5, 1])
        with col_info:
            st.caption(f"檔名：{uploaded.name}　｜　大小：{uploaded.size/1_048_576:.1f} MB")
        with col_btn:
            go = st.button("開始轉錄 →", type="primary", use_container_width=True)
        if go:
            if not api_key:
                st.error("請在左側輸入 Google AI Studio API Key")
            else:
                with st.spinner("Gemini 轉錄中，請稍候…"):
                    try:
                        segs = transcribe_audio(uploaded.read(), uploaded.name, api_key, LANG_MAP[language])
                        st.session_state.transcript   = [
                            {"speaker": speaker_names[0], "text": s["text"],
                             "displayTime": secs_hms(s["start"]), "rawTime": int(s["start"] * 1000)}
                            for s in segs
                        ]
                        st.session_state.analysis     = None
                        st.session_state.meeting_info = {}
                        st.success(f"轉錄完成！共 {len(segs)} 段")
                        st.rerun()
                    except Exception as e:
                        st.error(f"轉錄失敗：{e}")

# ── Tab 2: Record ──────────────────────────────────────────────────────────────
with tab_rec:
    st.info("💡 點擊麥克風錄音，完成後點「轉錄錄音」。")
    try:
        audio_val = st.audio_input("點擊麥克風開始錄音")
        if audio_val:
            _, col_btn2 = st.columns([5, 1])
            with col_btn2:
                go_rec = st.button("轉錄錄音 →", type="primary", use_container_width=True)
            if go_rec:
                if not api_key:
                    st.error("請輸入 Google AI Studio API Key")
                else:
                    with st.spinner("Gemini 轉錄中…"):
                        try:
                            segs = transcribe_audio(audio_val.read(), "recording.wav", api_key, LANG_MAP[language])
                            st.session_state.transcript   = [
                                {"speaker": speaker_names[0], "text": s["text"],
                                 "displayTime": secs_hms(s["start"]), "rawTime": int(s["start"] * 1000)}
                                for s in segs
                            ]
                            st.session_state.analysis     = None
                            st.session_state.meeting_info = {}
                            st.success("轉錄完成！")
                            st.rerun()
                        except Exception as e:
                            st.error(f"錯誤：{e}")
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
                st.markdown(
                    f'<div class="hist-card {"active" if is_active else ""}">'
                    f'<div class="hist-title">{rec["title"]}</div>'
                    f'<div class="hist-meta">{rec["date"]}</div>'
                    f'<div class="hist-meta">{" · ".join(rec.get("participants", []))}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if st.button("查看", key=f"view_{i}", use_container_width=True):
                    st.session_state.hist_idx = i
                    st.rerun()
        with col_detail:
            idx = st.session_state.hist_idx
            if idx is not None and idx < len(history):
                rec = history[idx]
                render_results(rec["analysis"], rec["meeting_info"], rec["transcript"])
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
        if not api_key:
            st.error("請輸入 Google AI Studio API Key")
        else:
            with st.spinner("Gemini 分析中，請稍候…"):
                try:
                    info = {
                        "title":        meeting_title,
                        "date":         datetime.now().strftime("%Y/%m/%d %H:%M"),
                        "participants": list(dict.fromkeys(e["speaker"] for e in st.session_state.transcript)),
                    }
                    result = analyze_with_gemini(st.session_state.transcript, info, api_key)
                    st.session_state.analysis     = result
                    st.session_state.meeting_info = info
                    save_to_history(st.session_state.transcript, result, info)
                    st.rerun()
                except Exception as e:
                    st.error(f"分析失敗：{e}")

# ── Current results ────────────────────────────────────────────────────────────
if st.session_state.analysis:
    st.divider()
    st.markdown('<div class="sec-title">📋 本次分析結果</div>', unsafe_allow_html=True)
    render_results(
        st.session_state.analysis,
        st.session_state.meeting_info,
        st.session_state.transcript,
    )
