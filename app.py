import streamlit as st
import os, json, re, time
import base64
from io import BytesIO
from PIL import Image
from components_gemini import (
    load_service_account_from_streamlit_secrets, fetch_url_text, smart_summarize,
    generate_action_items, export_to_pptx, _gemini_generate_text, tts_create_audio_bytes,
    stt_from_uploaded_bytes, analyze_emotion, estimate_audio_duration_seconds,
    generate_flashcards, generate_todos, translate_text
)

print(_gemini_generate_text("Say: Hello from Gemini", model="gemini-1.5-flash"))
b = tts_create_audio_bytes("Hello from PageBuddy", language_code="en-IN")
open("test.mp3", "wb").write(b)

# ---------- Constants ----------
PAGEBUDDY_PORT = int(os.environ.get("PAGEBUDDY_PORT", "6006"))
FLASK_API_BASE = f"http://localhost:{PAGEBUDDY_PORT}"

# =========================
# 🔌 Flask Microserver for Chrome Extension
# =========================
from flask import Flask, request, jsonify
import threading, uuid, hashlib

app_flask = Flask("pagebuddy_api")

@app_flask.route("/chrome-page", methods=["POST"])
def chrome_page():
    try:
        data = request.json
        content = data.get("content","")
        url = data.get("url","")
        st.session_state["chrome_content"] = content
        st.session_state["chrome_url"] = url
        return jsonify({"status":"ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app_flask.route("/upload-audio", methods=["POST"])
def upload_audio():
    try:
        audio_b64 = request.json.get("audio_b64")
        language = request.json.get("language","en-IN")
        if not audio_b64:
            return jsonify({"error":"no audio"}), 400
        audio_bytes = base64.b64decode(audio_b64.split(",")[-1])
        text = stt_from_uploaded_bytes(audio_bytes, language=language)
        return jsonify({"text": text}), 200
    except Exception as e:
        return jsonify({"error":str(e)}), 500

def run_flask():
    app_flask.run(host="0.0.0.0", port=PAGEBUDDY_PORT, debug=False, use_reloader=False)

# start Flask in background
threading.Thread(target=run_flask, daemon=True).start()

# ---------- Streamlit UI ----------
st.set_page_config(page_title="PageBuddy — NOVA", layout="wide", page_icon="🤖")
local_css = lambda f: st.markdown(f"<style>{open(f).read()}</style>", unsafe_allow_html=True)
local_css("styles.css")

# Header and avatar rendering helper (returns HTML)
def avatar_svg_html(state="listening", lipsync=False):
    # choose svg path based on state
    state_map = {
        "listening": "avatar/nova_idle.png",
        "happy": "avatar/nova_happy.png",
        "thinking": "avatar/nova_thinking.png",
        "excited": "avatar/nova_excited.png",
        "battle": "avatar/nova_battle.png"
    }
    svg_path = state_map.get(state, state_map["listening"])
    lips_class = "lipsync" if lipsync else ""
    html = f"""
    <div style="position:relative;display:flex;align-items:center;">
      <img id="nova_avatar" src="{svg_path}" class="holo-avatar avatar-{state} {lips_class}" width="160"/>
      <div style="margin-left:14px;">
        <div style="font-weight:800;color:#e7fbff">PageBuddy — NOVA</div>
        <div style="color:#bfeefd;font-size:13px">Meet NOVA. Your Web. Upgraded.</div>
      </div>
      <div id="nova_reaction" class="reaction-panel" style="display:none;">🙂</div>
    </div>
    """
    return html
    
# =========================
# 😎 Anime Hologram Avatar (Emotion Engine)
# =========================
from components_gemini import avatar_svg

if "avatar_state" not in st.session_state:
    st.session_state.avatar_state = "listening"

avatar_html = avatar_svg(st.session_state.avatar_state)
st.markdown(avatar_html, unsafe_allow_html=True)

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
    memory_mode = st.checkbox("Memory Mode — NOVA remembers what you like ❤️", value=True)
    st.markdown("---")

# Top header + avatar
col1, col2 = st.columns([1,4])
with col1:
    st.markdown(avatar_svg_html("listening", lipsync=False), unsafe_allow_html=True)
with col2:
    st.markdown("""
      <div class="block header">
        <div style="display:flex;flex-direction:column;">
          <div class="title">PageBuddy — NOVA</div>
          <div class="subtitle">Blue Electric Tokyo · Gemini-powered · Voice & Multilingual</div>
        </div>
      </div>
    """, unsafe_allow_html=True)
    
# Layout
left, right = st.columns([2,3])

with left:
    st.markdown("<div class='block'><h3>🔍 URL or Paste</h3>", unsafe_allow_html=True)
    url = st.text_input("Paste URL here")
    raw_text = st.text_area("Or paste article text (optional)", height=220)
    fetch = st.button("Fetch & Summarize")
    st.markdown("</div>", unsafe_allow_html=True)

    if fetch:
        # Priority: Chrome extension → raw text → URL
        if "chrome_content" in st.session_state:
            content = st.session_state.chrome_content
            st.info("✅ Loaded content from Chrome Extension!")
        elif raw_text and len(raw_text.strip()) > 50:
            content = raw_text.strip()
        elif url:
            content = fetch_url_text(url)
        else:
            st.warning("Paste URL/text or use Chrome extension.")
            content = ""
    
        if not content:
            st.stop()
    
        if content.startswith("ERROR"):
            st.error(content)
            st.stop()
    
        st.info("Summarizing...")
        summary = smart_summarize(content, model=model_choice, language=lang, style=style)
        actions = generate_action_items(content, model=model_choice, language=lang)
    
        # === Update Avatar Emotion ===
        emotion = analyze_emotion(summary)
        st.session_state.setdefault("avatar_state", emotion)
        st.markdown(avatar_svg_html(emotion, lipsync=False), unsafe_allow_html=True)
    
        st.markdown("### ✨ Summary")
        st.write(summary)
    
        st.markdown("### 🗒️ Action Items")
        st.write(actions)
        
        # flashcards & todos
        if st.button("Generate Flashcards"):
            cards = generate_flashcards(content, model=model_choice, count=6, language=lang)
            st.json(cards)
        if st.button("Generate Todos"):
            todos = generate_todos(content, model=model_choice, language=lang)
            st.write(todos)
            
        # Export PPTX
        if st.button("Export PPTX"):
            bullets = summary.split("\n")[:6]
            actions_list = actions.split("\n")[:6]
            pptx_bytes = export_to_pptx("PageBuddy Export", bullets, actions_list)
            st.download_button("Download PPTX", data=pptx_bytes,
                file_name="pagebuddy_export.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")
    
        # TTS + lipsync orchestration
        if enable_tts and st.button("🔊 Narrate Summary"):
            lang_map = {"English":"en-IN","Hindi":"hi-IN","Telugu":"te-IN"}
            tts_text = summary if len(summary) < 3500 else summary[:3500]
            audio_bytes = tts_create_audio_bytes(tts_text, language_code=lang_map.get(lang,"en-IN"))
            if audio_bytes:
                # play audio in streamlit and trigger lipsync via JS
                st.audio(audio_bytes, format="audio/mp3")
                duration = estimate_audio_duration_seconds(tts_text)
                # trigger client-side lipsync using HTML/JS
                js = f"""
                <script>
                const img = document.getElementById('nova_avatar');
                if (img) {{
                  img.classList.add('lipsync');
                  setTimeout(()=>{{ img.classList.remove('lipsync'); }}, {int(duration*1000)});
                }}
                </script>
                """
                st.markdown(js, unsafe_allow_html=True)
            else:
                st.warning("TTS unavailable (check credentials).")

with right:
    st.markdown("<div class='block'><h3>💬 Hologram Chat</h3>", unsafe_allow_html=True)
    if "history" not in st.session_state:
        st.session_state.history = []
    st.session_state.setdefault("memory", {})
    
    def append(role, txt):
        st.session_state.history.append({"role":role,"txt":txt})
        
    # render history
    for msg in st.session_state.history:
        if msg["role"] == "user":
            st.markdown(f"<div class='chat-right'>{msg['txt']}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='chat-left'>{msg['txt']}</div>", unsafe_allow_html=True)

    prompt = st.text_input("Ask NOVA...", key="prompt")
    if st.button("Send"):
        if not prompt.strip():
            st.warning("Write a prompt.")
        else:
            append("user", prompt)
            p = f"You are NOVA, a calm futuristic assistant. Respond in {lang} and style {style}.\nUser: {prompt}"
            if memory_mode:
                prefs = json.dumps(st.session_state.get("memory", {}))
                p += f"\nUser preferences: {prefs}"
            resp = _gemini_generate_text(p, model=model_choice, max_output_tokens=420)
            if not resp:
                resp = "Gemini not available — fallback: " + prompt[:240]
            append("assistant", resp)
            
            # update avatar emotion
            st.session_state["avatar_state"] = analyze_emotion(resp)
            # show updated avatar and lipsync while speaking (if TTS enabled)
            if enable_tts:
                audio = tts_create_audio_bytes(resp, language_code={"English":"en-IN","Hindi":"hi-IN","Telugu":"te-IN"}.get(lang,"en-IN"))
                if audio:
                    st.audio(audio, format="audio/mp3")
                    duration = estimate_audio_duration_seconds(resp)
                    st.markdown(f"<script>const img=document.getElementById('nova_avatar'); if(img){{img.classList.add('lipsync'); setTimeout(()=>img.classList.remove('lipsync'),{int(duration*1000)});}}</script>", unsafe_allow_html=True)
            st.experimental_rerun()
           
    st.markdown("</div>", unsafe_allow_html=True)
if memory_mode:
    st.session_state.setdefault("memory", {})["fav_language"] = lang

# Voice input (upload)
# Voice input (upload) + local mic streaming via client JS
if enable_voice_input:
    st.markdown("<div class='block'><h3>🎤 Voice Input (record or wake word)</h3></div>", unsafe_allow_html=True)
    st.markdown("""
    <div>
      <button id="pb-record" class="neon-btn">Start/Stop Recording</button>
      <button id="pb-wake" class="neon-btn">Enable Wake Word (Hey Nova)</button>
      <div id="pb-status" style="margin-top:10px;color:#9fdfff"></div>
    </div>

    <script>
    // Client-side recorder + wake-word using Web Speech API
    let recorder;
    let mediaStream;
    let chunks = [];
    let recOn = false;
    const recordBtn = document.getElementById("pb-record");
    const wakeBtn = document.getElementById("pb-wake");
    const status = document.getElementById("pb-status");

    recordBtn.onclick = async () => {
      if (!recOn) {
        if (!navigator.mediaDevices) { alert("Media devices not supported"); return; }
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        recorder = new MediaRecorder(mediaStream);
        recorder.ondataavailable = e => chunks.push(e.data);
        recorder.onstop = async () => {
          const blob = new Blob(chunks, { type: 'audio/webm' });
          chunks = [];
          const reader = new FileReader();
          reader.onload = async () => {
            const base64 = reader.result;
            status.innerText = "Uploading...";
            try {
              const res = await fetch("{FLASK_API_BASE}/upload-audio", {
                method: "POST",
                headers: { "Content-Type":"application/json" },
                body: JSON.stringify({ audio_b64: base64, language: "en-IN" })
              });
              const j = await res.json();
              if (j.text) {
                // put transcription into Streamlit input via streamlit API not available; user can copy
                alert("Transcription: " + j.text);
              } else {
                alert("Transcribe error: " + JSON.stringify(j));
              }
            } catch(e) {
              alert("Upload failed: " + e);
            }
            status.innerText = "";
          };
          reader.readAsDataURL(blob);
        };
        recorder.start();
        recOn = true;
        status.innerText = "Recording...";
        recordBtn.innerText = "Stop Recording";
      } else {
        recorder.stop();
        mediaStream.getTracks().forEach(t=>t.stop());
        recOn = false;
        recordBtn.innerText = "Start/Stop Recording";
        status.innerText = "Processing audio...";
      }
    };

    // Wake word via Web Speech API
    let recognition;
    let wakeOn = false;
    wakeBtn.onclick = () => {
      if (wakeOn) {
        wakeOn = false;
        recognition && recognition.stop();
        wakeBtn.innerText = "Enable Wake Word (Hey Nova)";
        status.innerText = "";
        return;
      }
      if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        alert("SpeechRecognition not supported in this browser. Use manual record.");
        return;
      }
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      recognition = new SpeechRecognition();
      recognition.lang = 'en-US';
      recognition.continuous = true;
      recognition.interimResults = false;
      recognition.onresult = function(event) {
        const transcript = event.results[event.results.length-1][0].transcript.trim();
        console.log("heard:", transcript);
        if (/hey nova|okay nova|okay nova/i.test(transcript)) {
          // notify Streamlit UI by showing alert and focusing input
          alert("Hey Nova detected! Click 'Send' in PageBuddy to interact or type your prompt.");
        }
      };
      recognition.start();
      wakeOn = true;
      wakeBtn.innerText = "Disable Wake Word";
      status.innerText = "Wake word active (listening)...";
    };
    </script>
    """, unsafe_allow_html=True)

st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
