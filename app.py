# app.py — PageBuddy (NOVA) single-file with Landing + Full UI
import streamlit as st
import os, json, re, time, base64
from io import BytesIO
from PIL import Image

# -------------------------
# Attempt to import components_gemini (safe fallbacks)
# -------------------------
try:
    from components_gemini import (
        load_service_account_from_streamlit_secrets, fetch_url_text, smart_summarize,
        generate_action_items, _gemini_generate_text, tts_create_audio_bytes,
        stt_from_uploaded_bytes, analyze_emotion, estimate_audio_duration_seconds,
        generate_flashcards, generate_todos, translate_text, export_to_pptx, render_avatar
    )
    COMPONENTS_OK = True
except Exception as e:
    COMPONENTS_OK = False
    _import_err = str(e)
if not COMPONENTS_OK:
    st.warning(f"⚠️ Using fallback — components_gemini missing or failed: {_import_err}")
    
st.write("Has STREAMLIT secrets loaded?",
         "✅ Yes" if "gemini_api_key" in st.secrets else "❌ No")
st.write("Env key check:",
         os.environ.get("GOOGLE_API_KEY", "Not set"))
    # Fallbacks to avoid app crash; functionality will be limited
def load_service_account_from_streamlit_secrets(x): return False
def fetch_url_text(url): return f"ERROR_FETCH: fetch_url_text not available ({url})"
def smart_summarize(text, **kw): return text[:800]
def generate_action_items(text, **kw): return "- (action items not available)"
def export_to_pptx(title, bullets, actions): return None
def _gemini_generate_text(prompt, **kw): return "Gemini not configured (fallback)."
def tts_create_audio_bytes(text, language_code="en-IN"): return None
def stt_from_uploaded_bytes(b, language="en-IN"): return "ERROR_STT: local fallback"
def analyze_emotion(text): return "listening"
def estimate_audio_duration_seconds(text): return max(1.0, len(text)/18.0)
def generate_flashcards(text, **kw): return []
def generate_todos(text, **kw): return []
def translate_text(text, **kw): return text
def render_avatar(state="listening"):
    img = f"avatar/nova_idle.png" if state in ("idle","listening") else f"avatar/nova_{state}.png"
    return f'<div><img id="nova_avatar" src="{img}" class="holo-avatar" width="160"/></div>'

# -------------------------
# Config & environment
# -------------------------
FLASK_API_BASE = os.getenv("FLASK_API_BASE", "https://pagebuddy-backend.onrender.com")
PAGEBUDDY_API_KEY = os.getenv("PAGEBUDDY_API_KEY", "")  # optional for extension headers
st.set_page_config(page_title="PageBuddy — NOVA", layout="wide", page_icon="🤖")

# try load optional CSS file
def local_css(fname="styles.css"):
    try:
        with open(fname) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except Exception:
        pass

local_css()

# -------------------------
# Core injected CSS + JS (hero, holo pulse, typing, glitch)
# We keep this as a raw string and then replace FLASK_BASE_PLACEHOLDER safely.
# -------------------------
core_frontend = """
<style>
:root{--bg:#041421;--accent1:#2ef0ff;--accent2:#7be1ff;}
body { background: linear-gradient(180deg, #021028 0%, #00121a 100%); color: #e7fbff; }

/* Landing hero glassmorphism */
.landing-wrap { max-width:1100px; margin:18px auto; }
.landing-hero {
  display:flex; gap:28px; align-items:center; justify-content:space-between;
  padding:44px; border-radius:16px;
  background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01));
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255,255,255,0.04);
  box-shadow: 0 12px 40px rgba(2,8,16,0.6);
}
.hero-left { max-width:62%; }
.hero-title { font-size:32px; font-weight:900; color:#dffcff; margin-bottom:8px; }
.hero-sub { color:#bfeefd; font-size:15px; margin-bottom:14px; }
.cta { display:inline-block; padding:12px 22px; border-radius:12px; font-weight:800; color:#001425; background: linear-gradient(90deg,var(--accent1),var(--accent2)); box-shadow:0 10px 30px rgba(46,240,255,0.08); border:none; cursor:pointer; }

/* hero right */
.hero-right { position:relative; width:320px; height:320px; display:flex; align-items:center; justify-content:center; }
.hero-avatar { width:220px; height:220px; border-radius:14px; object-fit:cover; filter: drop-shadow(0 18px 40px rgba(46,240,255,0.08)); transition: transform .28s ease; }
.holo-ring { position:absolute; width:360px; height:360px; border-radius:50%; pointer-events:none; opacity:0.9; mix-blend-mode:screen; animation: ringSpin 9s linear infinite; }
@keyframes ringSpin { 0%{transform:rotate(0deg)}100%{transform:rotate(360deg)} }
.particle { position:absolute; width:8px; height:8px; background: radial-gradient(circle at 30% 30%, #bfeefd, #2ef0ff); border-radius:50%; opacity:0.9; animation: floaty 6s ease-in-out infinite; }
@keyframes floaty { 0%{transform:translateY(0) translateX(0)}50%{transform:translateY(-18px) translateX(8px)}100%{transform:translateY(0)} }

/* holo avatar pulse */
.holo-avatar { transition: transform 0.35s ease, opacity 0.35s ease; border-radius:12px; }
.holo-pulse { animation: holoPulse 1.9s ease-in-out infinite; }
@keyframes holoPulse { 0% { transform: scale(1); } 50% { transform: scale(1.04) translateY(-4px); } 100% { transform: scale(1); } }

/* typing bubbles */
.typing { display:inline-block; height:12px; vertical-align:middle; }
.typing span { display:inline-block; width:6px; height:6px; margin:0 2px; background:#bfeefd; border-radius:50%; opacity:0.25; transform:translateY(0); animation: bounce 1.2s infinite; }
.typing span:nth-child(2){ animation-delay:0.12s; }
.typing span:nth-child(3){ animation-delay:0.24s; }
@keyframes bounce { 0% { opacity:.25; transform: translateY(0);} 50% { opacity:1; transform: translateY(-6px);} 100% { opacity:.25; transform: translateY(0);} }

/* chat bubble animations & glitch */
.chat-left, .chat-right { padding:10px 12px; border-radius:12px; margin:8px; max-width:86%; animation: bubblePop .32s ease-out; }
.chat-left { background: rgba(255,255,255,0.03); color: #e7fbff; text-align:left; }
.chat-right { background: linear-gradient(90deg,var(--accent1),var(--accent2)); color:#001425; text-align:right; margin-left:auto; }
@keyframes bubblePop { 0% { transform: scale(.96); opacity:0 } 100% { transform: scale(1); opacity:1 } }

/* lipsync quick */
.lipsync { animation: lips 0.14s linear infinite; transform-origin:center; }
@keyframes lips { 0%{transform:scaleY(1)}50%{transform:scaleY(0.96)}100%{transform:scaleY(1)} }

/* glitch */
.glitch { animation: glitchAnim .6s ease-in-out; }
@keyframes glitchAnim {
  0% { transform: translateX(0); }
  20% { transform: translateX(-6px) skewX(-2deg); }
  40% { transform: translateX(6px) skewX(2deg); }
  60% { transform: translateX(-4px) skewX(-1deg); }
  80% { transform: translateX(4px) skewX(1deg); }
  100% { transform: translateX(0); }
}

/* small blocks */
.block { background: rgba(255,255,255,0.02); padding:12px; border-radius:12px; border:1px solid rgba(255,255,255,0.03); }
.header .title{ font-size:20px; font-weight:800; color:#e7fbff; }
.header .subtitle{ font-size:13px; color:#bfeefd; }
.neon-btn { background: linear-gradient(90deg,var(--accent1),var(--accent2)); border:none; padding:8px 12px; border-radius:10px; font-weight:700; color:#001425; cursor:pointer; }
.small { font-size:12px; color:#bfeefd; margin-top:6px; }

.fade-scale-enter { animation: fadeScaleIn .42s ease forwards; }
@keyframes fadeScaleIn { 0% { opacity:0; transform: scale(.92) translateY(8px);} 100% { opacity:1; transform: scale(1) translateY(0);} }

</style>

<script>
// PageBuddy client helpers (no server-side dependency)
window.PageBuddy = window.PageBuddy || {};
window.PageBuddy.setAvatar = function(state, lipsync=false, pulse=true){
  const img = document.getElementById('nova_avatar') || document.getElementById('landing_avatar');
  if(!img) return;
  const map = {'listening':'avatar/nova_idle.png','idle':'avatar/nova_idle.png','happy':'avatar/nova_happy.png','thinking':'avatar/nova_thinking.png','excited':'avatar/nova_excited.png','battle':'avatar/nova_battle.png'};
  img.src = map[state] || map['idle'];
  img.classList.remove('lipsync','holo-pulse','glitch','fade-scale-enter');
  if(lipsync) img.classList.add('lipsync');
  if(pulse) img.classList.add('holo-pulse');
};
window.PageBuddy.showTyping = function(containerId){
  const c = document.getElementById(containerId);
  if(!c) return;
  c.innerHTML = '<div class="typing" id="pb_typing"><span></span><span></span><span></span></div>';
};
window.PageBuddy.hideTyping = function(containerId){
  const el = document.getElementById('pb_typing');
  if(el) el.remove();
};
window.PageBuddy.triggerGlitch = function(dur){
  document.body.classList.add('glitch');
  setTimeout(()=>document.body.classList.remove('glitch'), dur || 700);
};
window.PageBuddy.setExtensionStatus = function(text, ok){
  const el = document.getElementById('extension-status');
  if(!el) return;
  el.innerText = text;
  el.style.color = ok ? '#bfeefd' : '#ff8b8b';
};
</script>
"""

# Replace placeholder if needed (no placeholders used here)
st.markdown(core_frontend, unsafe_allow_html=True)

# -------------------------
# Landing page logic (show landing first — option 1)
# -------------------------
if "show_app" not in st.session_state:
    st.session_state.show_app = False  # show landing by default

# Landing HTML + JS (we use a replace sentinel for FLASK API base in JS if needed later)
landing_html = """
<div class="landing-wrap">
  <div class="landing-hero" id="landing-hero">
    <div class="hero-left">
      <div class="hero-title">🔮 PageBuddy</div>
      <div class="hero-sub"><strong>Your Hologram Companion</strong> — Think Less. Know More.</div>
      <div style="margin-top:14px;">
        <button id="activate-btn" class="cta">Activate Nova</button>
        <span style="margin-left:12px;color:#bfeefd">• Quick demo: click Activate Nova then try "Fetch & Summarize"</span>
      </div>
      <div style="margin-top:12px;">
        <small style="color:#9fdfff">Tip: Allow microphone for voice and wake-word features.</small>
      </div>
    </div>

    <div class="hero-right">
      <div id="hero-particles" style="position:absolute; inset:0;"></div>
      <div class="holo-ring" style="background: conic-gradient(from 90deg, rgba(46,240,255,0.06), rgba(123,225,255,0.02));"></div>
      <img id="landing_avatar" src="avatar/nova_idle.png" class="hero-avatar holo-avatar holo-pulse" />
    </div>
  </div>
</div>

<script>
(function(){
  // particles
  const container = document.getElementById('hero-particles');
  if(container){
    for(let i=0;i<10;i++){
      const p = document.createElement('div');
      p.className = 'particle';
      const left = 6 + Math.random()*88;
      const top = 6 + Math.random()*88;
      const size = 5 + Math.random()*14;
      p.style.left = left + '%';
      p.style.top = top + '%';
      p.style.width = size + 'px';
      p.style.height = size + 'px';
      p.style.opacity = 0.5 + Math.random()*0.5;
      p.style.animationDuration = (4 + Math.random()*6) + 's';
      container.appendChild(p);
    }
  }

  // gaze tracking
  const avatar = document.getElementById('landing_avatar');
  if(avatar){
    document.addEventListener('mousemove', (e) => {
      const rect = avatar.getBoundingClientRect();
      const cx = rect.left + rect.width/2;
      const cy = rect.top + rect.height/2;
      const dx = (e.clientX - cx)/40;
      const dy = (e.clientY - cy)/60;
      avatar.style.transform = `translate(${dx}px, ${dy}px)`;
    });
  }

  // Activate button - sets a small session cookie via reload strategy
  const btn = document.getElementById('activate-btn');
  if(btn){
    btn.addEventListener('click', async () => {
      btn.innerText = "Activating...";
      btn.disabled = true;
      btn.style.transform = "scale(.98)";
      // We can't set Streamlit session directly from JS reliably.
      // Instead, we use a quick navigation hack: append ?__launch=1 to URL then reload.
      const url = new URL(window.location.href);
      url.searchParams.set('__launch', '1');
      window.location.href = url.toString();
    });
  }
})();
</script>
"""

# Render landing page if show_app False
if not st.session_state.show_app:
    st.markdown(landing_html, unsafe_allow_html=True)
    # server-side "Activate Nova" fallback: query param detection
    qp = st.query_params
    if qp.get("__launch") == ["1"]:
        st.session_state.show_app = True
        st.query_params.clear()
        st.rerun()
    
    # Also render reliable server button
    if st.button("Activate Nova"):
        st.session_state.show_app = True
        st.rerun()
    
    st.stop()  # stop rendering landing page

# -------------------------
# MAIN APP UI (PageBuddy) - shown after Activate Nova
# -------------------------
# ensure some session state
st.session_state.setdefault("emotion", "listening")
st.session_state.setdefault("history", [])
st.session_state.setdefault("memory", {})

# top header and avatar
col1, col2 = st.columns([1,4])
with col1:
    st.markdown(render_avatar(st.session_state.get("emotion","listening")), unsafe_allow_html=True)
with col2:
    st.markdown("""
      <div class="block header">
        <div style="display:flex;flex-direction:column;">
          <div class="title">PageBuddy — NOVA</div>
          <div class="subtitle">Blue Electric Tokyo · Gemini-powered · Voice & Multilingual</div>
        </div>
      </div>
    """, unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("Settings")
    model_choice = st.selectbox("Gemini model", ["gemini-1.5-flash", "gemini-1.5-pro"], index=0)
    lang = st.selectbox("Language", ["English","Hindi","Telugu"], index=0)
    style = st.selectbox("Summary style", ["anime","formal","corporate","emoji","genz"], index=0)
    enable_voice_input = st.checkbox("Enable voice input (upload)", value=True)
    enable_tts = st.checkbox("Enable TTS narration", value=True)
    memory_mode = st.checkbox("Memory Mode — NOVA remembers what you like ❤️", value=True)
    st.markdown("---")
    st.markdown("**Extension status**")
    st.markdown('<div id="extension-status">Unknown</div>', unsafe_allow_html=True)
    if st.button("Ping Backend"):
        import requests
        try:
            r = requests.get(f"{FLASK_API_BASE}/", timeout=3)
            ok = r.status_code == 200
            st.markdown(f"<script>window.PageBuddy.setExtensionStatus('Backend reachable: {ok}', {str(ok).lower()});</script>", unsafe_allow_html=True)
        except Exception:
            st.markdown("<script>window.PageBuddy.setExtensionStatus('Backend unreachable', false); window.PageBuddy.triggerGlitch(700);</script>", unsafe_allow_html=True)

# Main layout
left_col, right_col = st.columns([2,3])

# LEFT: Fetch / Summarize / Flashcards / TTS
with left_col:
    st.markdown("<div class='block'><h3>🔍 URL or Paste</h3>", unsafe_allow_html=True)
    url = st.text_input("Paste URL here")
    raw_text = st.text_area("Or paste article text (optional)", height=240)
    fetch_btn = st.button("Fetch & Summarize")
    st.markdown("</div>", unsafe_allow_html=True)

    if fetch_btn:
        # choose content source
        content = ""
        if st.session_state.get("chrome_content"):
            content = st.session_state["chrome_content"]
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

        if isinstance(content, str) and content.startswith("ERROR"):
            st.error(content)
            st.markdown("<script>window.PageBuddy.triggerGlitch(700);</script>", unsafe_allow_html=True)
            st.stop()

        # client-side: set thinking avatar + typing
        st.markdown("<script>window.PageBuddy.setAvatar('thinking', false, true); window.PageBuddy.showTyping('left-typing')</script>", unsafe_allow_html=True)
        st.markdown('<div id="left-typing"></div>', unsafe_allow_html=True)

        # call summarization
        try:
            summary = smart_summarize(content, model=model_choice, language=lang, style=style)
            actions = generate_action_items(content, model=model_choice, language=lang)
        except Exception as e:
            summary = f"ERROR: summarization failed: {e}"
            actions = ""
            st.markdown("<script>window.PageBuddy.triggerGlitch(800);</script>", unsafe_allow_html=True)

        # update avatar emotion
        try:
            emotion = analyze_emotion(summary)
        except Exception:
            emotion = "listening"

        st.markdown("<script>window.PageBuddy.hideTyping('left-typing'); window.PageBuddy.setAvatar('%s', false, true);</script>" % emotion, unsafe_allow_html=True)

        st.markdown("### ✨ Summary")
        st.write(summary)
        st.markdown("### 🗒️ Action Items")
        st.write(actions)

        # optional features
        if st.button("Generate Flashcards"):
            try:
                cards = generate_flashcards(content, model=model_choice, count=6, language=lang)
                st.json(cards)
            except Exception:
                st.warning("Flashcards failed.")

        if st.button("Generate Todos"):
            try:
                todos = generate_todos(content, model=model_choice, language=lang)
                st.write(todos)
            except Exception:
                st.warning("Todos failed.")

        if st.button("Export PPTX"):
            try:
                bullets = [b.strip() for b in re.split(r'\n|- ', summary) if b.strip()][:6]
                actions_list = [a.strip() for a in re.split(r'\n|- ', actions) if a.strip()][:6]
                pptx_bytes = export_to_pptx("PageBuddy Export", bullets, actions_list)
                if pptx_bytes:
                    data = pptx_bytes.getvalue() if hasattr(pptx_bytes, "getvalue") else pptx_bytes
                    st.download_button("Download PPTX", data=data, file_name="pagebuddy_export.pptx", mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")
            except Exception:
                st.warning("Export failed.")

        # TTS narration + lipsync
        if enable_tts and st.button("🔊 Narrate Summary"):
            try:
                lang_map = {"English":"en-IN","Hindi":"hi-IN","Telugu":"te-IN"}
                tts_text = summary if len(summary) < 3500 else summary[:3500]
                audio_bytes = tts_create_audio_bytes(tts_text, language_code=lang_map.get(lang,"en-IN"))
                if audio_bytes:
                    st.audio(audio_bytes, format="audio/mp3")
                    dur = estimate_audio_duration_seconds(tts_text)
                    st.markdown(f"<script>window.PageBuddy.setAvatar('happy', true, true); setTimeout(()=>window.PageBuddy.setAvatar('listening', false, true), {int(dur*1000)});</script>", unsafe_allow_html=True)
                else:
                    st.warning("TTS unavailable (check credentials).")
            except Exception:
                st.warning("TTS failed.")
                st.markdown("<script>window.PageBuddy.triggerGlitch(700);</script>", unsafe_allow_html=True)

# RIGHT: Chat UI
with right_col:
    st.markdown("<div class='block'><h3>💬 Hologram Chat</h3></div>", unsafe_allow_html=True)

    # render history
    for msg in st.session_state["history"]:
        if msg.get("role") == "user":
            st.markdown(f"<div class='chat-right'>{msg.get('txt','')}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='chat-left'>{msg.get('txt','')}</div>", unsafe_allow_html=True)

    prompt = st.text_input("Ask NOVA...", key="prompt")
    if st.button("Send"):
        if not prompt.strip():
            st.warning("Write a prompt.")
        else:
            st.session_state["history"].append({"role":"user","txt":prompt})
            # show thinking avatar + typing
            st.markdown("<script>window.PageBuddy.setAvatar('thinking', false, true); window.PageBuddy.showTyping('chat-typing');</script>", unsafe_allow_html=True)
            st.markdown('<div id="chat-typing"></div>', unsafe_allow_html=True)

            p = f"You are NOVA, a hologram anime assistant. Reply in {lang} and style {style}. Keep concise.\\nUser:\\n{prompt}"
            if memory_mode:
                p += "\\n\\nUser preferences: " + json.dumps(st.session_state.get("memory", {}))

            try:
                res = _gemini_generate_text(p, model=model_choice, max_output_tokens=420)
            except Exception as e:
                res = f"ERROR: model call failed: {e}"
                st.markdown("<script>window.PageBuddy.triggerGlitch(700);</script>", unsafe_allow_html=True)

            if not res:
                res = "Gemini not configured or not available. Fallback reply."

            # remove typing, append assistant
            st.markdown("<script>window.PageBuddy.hideTyping('chat-typing');</script>", unsafe_allow_html=True)
            st.session_state["history"].append({"role":"assistant","txt":res})

            # emotion + avatar update
            try:
                emot = analyze_emotion(res)
            except Exception:
                emot = "listening"
            st.markdown(f"<script>window.PageBuddy.setAvatar('{emot}', false, true);</script>", unsafe_allow_html=True)
            st.markdown(f"<div class='chat-left'>{res}</div>", unsafe_allow_html=True)

            # TTS + lipsync
            if enable_tts:
                try:
                    audio = tts_create_audio_bytes(res, language_code={"English":"en-IN","Hindi":"hi-IN","Telugu":"te-IN"}.get(lang,"en-IN"))
                    if audio:
                        st.audio(audio, format="audio/mp3")
                        dur = estimate_audio_duration_seconds(res)
                        st.markdown(f"<script>window.PageBuddy.setAvatar('{emot}', true, true); setTimeout(()=>window.PageBuddy.setAvatar('listening', false, true), {int(dur*1000)});</script>", unsafe_allow_html=True)
                except Exception:
                    st.markdown("<script>window.PageBuddy.triggerGlitch(600);</script>", unsafe_allow_html=True)

            st.experimental_rerun()

# persist memory choices
if memory_mode:
    st.session_state.setdefault("memory", {})["fav_language"] = lang

# Voice input (client record & wake-word)
if enable_voice_input:
    st.markdown("<div class='block'><h3>🎤 Voice Input (record or wake word)</h3></div>", unsafe_allow_html=True)

    voice_js = """
    <div>
      <button id="pb-record" class="neon-btn">Start/Stop Recording</button>
      <button id="pb-wake" class="neon-btn">Enable Wake Word (Hey Nova)</button>
      <div id="pb-status" style="margin-top:10px;color:#9fdfff"></div>
    </div>

    <script>
    (function(){
      FLASK_BASE = f"{FLASK_API_BASE}"
      const recordBtn = document.getElementById("pb-record");
      const wakeBtn = document.getElementById("pb-wake");
      const status = document.getElementById("pb-status");
      let recorder, mediaStream, chunks = [], recOn=false;

      recordBtn && (recordBtn.onclick = async () => {
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
                const res = await fetch(FLASK_BASE + "/upload-audio", {
                  method: "POST",
                  headers: { "Content-Type":"application/json" },
                  body: JSON.stringify({ audio_b64: base64, language: "en-IN" })
                });
                const j = await res.json();
                if (j.text) {
                  try { await navigator.clipboard.writeText(j.text); } catch(e){}
                  alert("Transcription copied to clipboard:\\n" + j.text + "\\n\\nPaste in PageBuddy prompt");
                } else {
                  alert("Transcribe error: " + JSON.stringify(j));
                }
              } catch(e) {
                alert("Upload failed: " + e);
                document.body.classList.add('glitch');
                setTimeout(()=>document.body.classList.remove('glitch'),700);
              }
              status.innerText = "";
            };
            reader.readAsDataURL(blob);
          };
          recorder.start();
          recOn=true; status.innerText="Recording..."; recordBtn.innerText="Stop Recording";
        } else {
          recorder.stop();
          mediaStream.getTracks().forEach(t=>t.stop());
          recOn=false; recordBtn.innerText="Start/Stop Recording"; status.innerText="Processing audio...";
        }
      });

      // Wake word
      let recognition, wakeOn=false;
      wakeBtn && (wakeBtn.onclick = () => {
        if (wakeOn) { wakeOn=false; recognition && recognition.stop(); wakeBtn.innerText="Enable Wake Word (Hey Nova)"; status.innerText=""; return; }
        if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) { alert("SpeechRecognition not supported"); return; }
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.lang = 'en-US';
        recognition.continuous = true;
        recognition.interimResults = false;
        recognition.onresult = function(event) {
          const transcript = event.results[event.results.length-1][0].transcript.trim();
          if (/hey nova|okay nova|ok nova/i.test(transcript)) {
            status.innerText = "✨ Hey Nova detected! Paste into prompt or click Send.";
            setTimeout(()=>status.innerText="",2300);
          }
        };
        recognition.start();
        wakeOn=true; wakeBtn.innerText="Disable Wake Word"; status.innerText="Wake word active (listening)...";
      });

    })();
    </script>
    """
    voice_js = voice_js.replace("FLASK_BASE_PLACEHOLDER", FLASK_API_BASE)
    st.markdown(voice_js, unsafe_allow_html=True)

st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
