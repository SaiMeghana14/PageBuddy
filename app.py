# app.py
import streamlit as st
import os
from components_gemini import (
    configure_genai, fetch_url_text, smart_summarize, generate_action_items,
    export_to_pptx, tts_say, speech_to_text_from_bytes
)
from PIL import Image
from io import BytesIO

st.set_page_config(page_title="PageBuddy — Gemini", layout="wide", page_icon="🤖")

# Load CSS
def local_css(file_name):
    with open(file_name) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
local_css("styles.css")

# Header
col1, col2 = st.columns([1,5])
with col1:
    st.image("anime_header.svg", width=72)
with col2:
    st.markdown("""
    <div class="block header">
      <div style="display:flex;flex-direction:column;">
        <div class="title">PageBuddy — Gemini Edition (Futuristic Cyber-Waifu)</div>
        <div class="subtitle">Blue Electric Tokyo theme · Gemini-powered · multilingual voice & narration</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

# Sidebar settings
with st.sidebar:
    st.header("⚙️ Settings")
    model_choice = st.selectbox("Gemini model", options=["gemini-1.5-flash", "gemini-1.5-pro"], index=0)
    api_key = st.text_input("Google API Key (optional)", type="password", value=os.getenv("GOOGLE_API_KEY",""))
    st.markdown("OR set `GOOGLE_APPLICATION_CREDENTIALS` env var to your service account JSON for full TTS & Gemini support.")
    if st.button("Configure Gemini"):
        if api_key:
            os.environ["GOOGLE_API_KEY"] = api_key
        ok = configure_genai(api_key=api_key if api_key else None)
        if ok:
            st.success("Gemini client configured (attempted).")
        else:
            st.warning("Gemini client not configured. You can still use fallback summarizer and local TTS.")

    st.markdown("---")
    st.markdown("**Voice & Language**")
    lang = st.selectbox("Language", options=["English","Hindi","Telugu"], index=0)
    lang_map = {"English":"en-IN","Hindi":"hi-IN","Telugu":"te-IN"}
    voice_input = st.checkbox("Enable voice input (record/upload)", value=True)
    enable_tts = st.checkbox("Enable TTS narration", value=True)
    st.markdown("---")
    st.markdown("Theme: Blue Electric Tokyo (Cyber-waifu avatar)")

# Main layout
left, right = st.columns([2,3])

with left:
    st.markdown("<div class='block'><h3>🔍 URL or Paste</h3>", unsafe_allow_html=True)
    url = st.text_input("Paste URL here")
    raw_text = st.text_area("Or paste article text (optional)", height=220)
    style = st.selectbox("Summary style", options=["anime","formal","corporate","emoji","genz"], index=0)
    fetch = st.button("Fetch & Summarize")
    st.markdown("</div>", unsafe_allow_html=True)

    if fetch:
        content = ""
        if raw_text and len(raw_text.strip())>50:
            content = raw_text.strip()
        elif url:
            content = fetch_url_text(url)
        else:
            st.warning("Paste a URL or article text.")
            content = ""
        if content.startswith("ERROR"):
            st.error(content)
        elif content:
            st.info("Summarizing with Gemini (or fallback)...")
            summary = smart_summarize(content, model=model_choice, language=lang, style=style)
            actions = generate_action_items(content, model=model_choice, language=lang)
            st.markdown("<div class='block'>", unsafe_allow_html=True)
            st.markdown("### ✨ Summary")
            st.markdown(summary)
            st.markdown("### 🧭 Action Items")
            st.markdown(actions)
            # quick export to pptx
            if st.button("Export to PPTX"):
                # parse bullets & actions heuristically
                bullets = [b.strip() for b in re.split(r'\n|- ', summary) if b.strip()][:6]
                actions_list = [a.strip() for a in re.split(r'\n|- ', actions) if a.strip()][:6]
                pptx_bytes = export_to_pptx("PageBuddy Export", bullets, actions_list)
                st.download_button("Download PPTX", data=pptx_bytes, file_name="pagebuddy_summary.pptx", mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")
            # narration
            if enable_tts:
                st.markdown("---")
                st.markdown("#### 🔊 Narration")
                tts_btn = st.button("Generate narration audio")
                if tts_btn:
                    # generate TTS (language mapping)
                    t = summary if len(summary) < 4000 else summary[:4000]
                    out = tts_say(t, language_code=lang_map.get(lang,"en-IN"))
                    if isinstance(out, BytesIO):
                        st.audio(out.getvalue(), format="audio/mp3")
                    elif isinstance(out, str) and os.path.exists(out):
                        with open(out, "rb") as f:
                            data = f.read()
                        st.audio(data, format="audio/mp3")
                    else:
                        st.info("Could not produce TTS audio (check Google credentials); consider local fallback.")

with right:
    st.markdown("<div class='block'><h3>💬 PageBuddy Chat</h3>", unsafe_allow_html=True)

    if "history" not in st.session_state:
        st.session_state.history = []

    def append(role, txt):
        st.session_state.history.append({"role":role,"txt":txt})

    # Render history
    for m in st.session_state.history:
        if m["role"] == "user":
            st.markdown(f"<div class='chat-right'>{m['txt']}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='chat-left'>{m['txt']}</div>", unsafe_allow_html=True)

    prompt = st.text_input("Ask PageBuddy (try: 'Give me 5 slide titles' or 'Summarize in Telugu')", key="prompt")
    if st.button("Send"):
        if prompt.strip() == "":
            st.warning("Please enter a prompt.")
        else:
            append("user", prompt)
            # call Gemini if configured
            from components_gemini import gemini_generate  # import late to honor config
            try:
                # Build model prompt with language
                p = f"You are PageBuddy, a futuristic cyber-waifu. Reply in {lang} and in style {style}. Answer concisely.\n\nUser:\n{prompt}"
                resp = gemini_generate(p, model=model_choice, max_output_tokens=400)
                if not resp:
                    # fallback
                    resp = "Gemini not available or not configured. Fallback: " + (prompt[:280])
            except Exception as e:
                resp = f"Error calling Gemini: {e}"
            append("assistant", resp)
            st.experimental_rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# Voice input area (upload or JS recorder)
if voice_input:
    st.markdown("<div class='block'><h3>🎙️ Voice Input</h3>", unsafe_allow_html=True)
    st.markdown("You can upload an audio file (wav/mp3) or record in-browser (button).", unsafe_allow_html=True)
    audio_file = st.file_uploader("Upload audio", type=["wav","mp3","m4a","ogg"])
    recorded = None
    # Simple in-browser recorder using HTML + JS
    st.markdown("""
    <script>
    // Simple recorder: will create a downloadable blob which user can upload back manually if needed.
    function recordAudio() {
      const recordBtn = document.getElementById("pb-record-btn");
      const stopBtn = document.getElementById("pb-stop-btn");
      let mediaRecorder;
      let audioChunks = [];
      recordBtn.onclick = async () => {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        mediaRecorder.start();
        audioChunks = [];
        mediaRecorder.ondataavailable = e => { audioChunks.push(e.data); };
        mediaRecorder.onstop = () => {
          const blob = new Blob(audioChunks, { type: 'audio/webm' });
          const url = URL.createObjectURL(blob);
          const anchor = document.getElementById("pb-download");
          anchor.href = url;
          anchor.download = "pagebuddy_recording.webm";
          anchor.style.display = "inline-block";
        };
      };
      stopBtn.onclick = () => {
        if (mediaRecorder) mediaRecorder.stop();
      }
    }
    window.addEventListener('load', recordAudio);
    </script>
    <div style="margin-top:8px;">
      <button id="pb-record-btn" class="neon-btn">Start Recording</button>
      <button id="pb-stop-btn" class="neon-btn" style="margin-left:8px;">Stop Recording</button>
      <a id="pb-download" style="display:none;margin-left:8px;" class="neon-btn">Download & Upload</a>
    </div>
    """, unsafe_allow_html=True)

    if audio_file:
        audio_bytes = audio_file.read()
        st.info("Running speech-to-text...")
        # choose language code
        code = {"English":"en-IN","Hindi":"hi-IN","Telugu":"te-IN"}[lang]
        stt = speech_to_text_from_bytes(audio_bytes, language=code)
        if str(stt).startswith("ERROR_STT"):
            st.error("Speech recognition failed. You can download the recorded file and upload a WAV for better results.")
        else:
            st.success("Transcribed.")
            st.text_area("Transcribed text", value=stt, height=160)
            if st.button("Use transcription as prompt"):
                st.session_state.prompt = stt
                st.experimental_rerun()

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
