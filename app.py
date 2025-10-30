import streamlit as st
import os, json, re
from components_gemini import (
    load_service_account_from_streamlit_secrets, fetch_url_text, smart_summarize,
    generate_action_items, export_to_pptx, _gemini_generate_text, tts_create_audio_bytes, stt_from_uploaded_bytes
)
print(_gemini_generate_text("Say: Hello from Gemini", model="gemini-1.5-flash"))
b = tts_create_audio_bytes("Hello from PageBuddy", language_code="en-IN")
open("test.mp3", "wb").write(b)

from io import BytesIO
from PIL import Image

st.set_page_config(page_title="PageBuddy — Hologram Assistant", layout="wide", page_icon="🤖")

# Load CSS
def local_css(fname="styles.css"):
    with open(fname) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
local_css()

# Header
col1, col2 = st.columns([1,5])
with col1:
    st.image("anime_hologram.svg", width=80)
with col2:
    st.markdown("""
    <div class="block header">
      <div style="display:flex;flex-direction:column;">
        <div class="title">PageBuddy — Anime Hologram Assistant</div>
        <div class="subtitle">Blue Electric Tokyo · Gemini enabled · Voice & Multilingual</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

# Configure from Streamlit secrets if present
if "google" in st.secrets:
    ok = load_service_account_from_streamlit_secrets(st.secrets)
    if ok:
        st.sidebar.success("Google credentials loaded from Streamlit secrets")
    else:
        st.sidebar.warning("Could not load Google credentials from secrets")

# Sidebar settings
with st.sidebar:
    st.header("Settings")
    model_choice = st.selectbox("Gemini model", ["gemini-1.5-flash", "gemini-1.5-pro"], index=0)
    lang = st.selectbox("Language", ["English","Hindi","Telugu"], index=0)
    style = st.selectbox("Summary style", ["anime","formal","corporate","emoji","genz"], index=0)
    enable_voice_input = st.checkbox("Enable voice input (upload)", value=True)
    enable_tts = st.checkbox("Enable TTS narration", value=True)
    st.markdown("---")
    st.markdown("Note: Only `Vertex AI User` role is required on your service account.")

# Layout
left, right = st.columns([2,3])

with left:
    st.markdown("<div class='block'><h3>🔍 URL or Paste</h3>", unsafe_allow_html=True)
    url = st.text_input("Paste URL here")
    raw_text = st.text_area("Or paste article text (optional)", height=220)
    fetch = st.button("Fetch & Summarize")
    st.markdown("</div>", unsafe_allow_html=True)

    if fetch:
        content = ""
        if raw_text and len(raw_text.strip())>50:
            content = raw_text.strip()
        elif url:
            content = fetch_url_text(url)
        else:
            st.warning("Please paste URL or article text.")
            content = ""
        if content.startswith("ERROR"):
            st.error(content)
        elif content:
            st.info("Summarizing...")
            summary = smart_summarize(content, model=model_choice, language=lang, style=style)
            actions = generate_action_items(content, model=model_choice, language=lang)
            st.markdown("<div class='block'>", unsafe_allow_html=True)
            st.markdown("### ✨ Summary")
            st.markdown(summary)
            st.markdown("### 🗒️ Action Items")
            st.markdown(actions)
            st.markdown("</div>", unsafe_allow_html=True)
            # export
            if st.button("Export PPTX"):
                bullets = [b.strip() for b in re.split(r'\n|- ', summary) if b.strip()][:6]
                actions_list = [a.strip() for a in re.split(r'\n|- ', actions) if a.strip()][:6]
                pptx_bytes = export_to_pptx("PageBuddy Export", bullets, actions_list)
                st.download_button("Download PPTX", data=pptx_bytes, file_name="pagebuddy_export.pptx", mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")

            if enable_tts:
                if st.button("Generate Narration (TTS)"):
                    tts_text = summary if len(summary) < 3500 else summary[:3500]
                    lang_map = {"English":"en-IN","Hindi":"hi-IN","Telugu":"te-IN"}
                    audio_bytes = tts_create_audio_bytes(tts_text, language_code=lang_map.get(lang,"en-IN"))
                    if audio_bytes:
                        st.audio(audio_bytes, format="audio/mp3")
                    else:
                        st.warning("TTS not available (credentials missing).")

with right:
    st.markdown("<div class='block'><h3>💬 Hologram Chat</h3>", unsafe_allow_html=True)
    if "history" not in st.session_state:
        st.session_state.history = []
    def append(role, txt):
        st.session_state.history.append({"role":role,"txt":txt})
    # render history
    for m in st.session_state.history:
        if m["role"] == "user":
            st.markdown(f"<div class='chat-right'>{m['txt']}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='chat-left'>{m['txt']}</div>", unsafe_allow_html=True)
    prompt = st.text_input("Ask PageBuddy...", key="prompt")
    if st.button("Send"):
        if not prompt.strip():
            st.warning("Write a prompt.")
        else:
            append("user", prompt)
            # call Gemini via components_gemini._gemini_generate_text indirectly
            from components_gemini import _gemini_generate_text
            p = f"You are PageBuddy, a hologram anime assistant. Reply in {lang} and style {style}. Keep concise.\n\nUser:\n{prompt}"
            res = _gemini_generate_text(p, model=model_choice, max_output_tokens=400)
            if not res:
                res = "Gemini not configured or not available. Fallback: " + prompt[:240]
            append("assistant", res)
            st.experimental_rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# Voice input (upload)
if enable_voice_input:
    st.markdown("<div class='block'><h3>🎤 Voice Input (upload)</h3>", unsafe_allow_html=True)
    audio_file = st.file_uploader("Upload audio (wav/mp3/m4a/ogg)", type=["wav","mp3","m4a","ogg"])
    if audio_file:
        audio_bytes = audio_file.read()
        st.info("Transcribing...")
        code_map = {"English":"en-IN","Hindi":"hi-IN","Telugu":"te-IN"}
        stt = stt_from_uploaded_bytes(audio_bytes, language=code_map.get(lang,"en-IN"))
        if isinstance(stt, str) and stt.startswith("ERROR_STT"):
            st.error("STT failed.")
        else:
            st.success("Transcribed:")
            st.text_area("Transcription", value=stt, height=160)
            if st.button("Use transcription as prompt"):
                st.session_state.prompt = stt
                st.experimental_rerun()

st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
