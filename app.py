import streamlit as st
from components import fetch_url_text, smart_summarize, generate_action_items, OPENAI_KEY
import base64
import os
from PIL import Image
import io

st.set_page_config(page_title="PageBuddy — AI Smart Web Assistant", layout="wide",
                   page_icon="🪄")

# Load CSS
def local_css(file_name):
    with open(file_name) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

local_css("styles.css")

# header
col1, col2 = st.columns([1,5])
with col1:
    st.markdown("""
    <div class="logo block header">
      <img src="data:image/svg+xml;utf8,{}" width="56" height="56" style="border-radius:10px;">
    </div>
    """.format(open("anime_header.svg","r",encoding="utf-8").read().replace("\n"," ")), unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div class="block header">
      <div style="display:flex;flex-direction:column;">
        <div class="title">PageBuddy — AI Smart Web Assistant</div>
        <div class="subtitle">Paste a URL, drop article text, or chat — instant anime-guided insights ✨</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("## ⚙️ Settings")
    api_key_input = st.text_input("OpenAI API Key (optional)", type="password", value=os.getenv("OPENAI_API_KEY",""))
    if api_key_input:
        os.environ["OPENAI_API_KEY"] = api_key_input
        st.success("API key set for this session.")
    st.markdown("---")
    theme = st.selectbox("Theme", options=["Neon Blossom (default)", "Midnight Sakura", "Pastel"], index=0)
    st.markdown("**Quick tips**")
    st.markdown("- Paste a URL and click *Fetch & Summarize*.\n- Use Chat for clarifying prompts.\n- Export summaries to clipboard.")
    st.markdown("---")
    st.markdown("Made with ❤️ — anime theme enabled")

# Main layout
left, right = st.columns([2,3])

with left:
    st.markdown("<div class='block'><h3>🔍 URL / Text Inspector</h3>", unsafe_allow_html=True)
    url = st.text_input("Paste article or page URL here")
    raw_text = st.text_area("Or paste article text here (optional)", height=200)
    fetch_btn = st.button("Fetch & Summarize", key="fetch")
    st.markdown("</div>", unsafe_allow_html=True)

    if fetch_btn:
        with st.spinner("Fetching content..."):
            content = ""
            if raw_text and len(raw_text.strip())>50:
                content = raw_text.strip()
            elif url:
                content = fetch_url_text(url)
            else:
                st.warning("Please paste a URL or article text.")
                content = ""
        if content.startswith("ERROR:"):
            st.error(content)
        elif content:
            st.success("Content loaded — summarizing...")
            summary = smart_summarize(content)
            actions = generate_action_items(content)
            st.markdown("<div class='block'>", unsafe_allow_html=True)
            st.markdown("### ✨ Summary (PageBuddy)")
            st.markdown(summary)
            st.markdown("### 🗒️ Actionable items")
            st.markdown(actions)
            st.markdown("</div>", unsafe_allow_html=True)

with right:
    st.markdown("<div class='block'><h3>💬 PageBuddy Chat</h3>", unsafe_allow_html=True)
    # simple chat: user prompt -> system call (OpenAI or fallback)
    if "history" not in st.session_state:
        st.session_state.history = []

    def append_message(role, text):
        st.session_state.history.append({"role":role,"text":text})

    # render chat history
    for msg in st.session_state.history:
        if msg["role"] == "user":
            st.markdown(f"<div class='chat-right'>{msg['text']}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='chat-left'>{msg['text']}</div>", unsafe_allow_html=True)

    prompt = st.text_input("Ask PageBuddy (try: 'Summarize this page', 'Make 5 slide titles')", key="prompt_input")
    if st.button("Send", key="send"):
        if not prompt.strip():
            st.warning("Ask something first.")
        else:
            append_message("user", prompt)
            # call OpenAI if key present
            if os.getenv("OPENAI_API_KEY"):
                try:
                    import openai
                    openai.api_key = os.getenv("OPENAI_API_KEY")
                    resp = openai.ChatCompletion.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role":"system","content":"You are PageBuddy - a friendly anime-themed web assistant. Provide concise helpful answers."},
                            {"role":"user","content":prompt}
                        ],
                        temperature=0.35,
                        max_tokens=300
                    )
                    text = resp.choices[0].message.content.strip()
                except Exception as e:
                    text = f"OpenAI request failed: {e}"
            else:
                # offline fallback
                text = "No API key set — try giving me the text or set OPENAI_API_KEY for full features. Meanwhile, here is a short heuristic response: " + prompt[:240]
            append_message("assistant", text)
            st.experimental_rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# Footer: exporting
st.markdown("<div class='block' style='margin-top:16px'>", unsafe_allow_html=True)
st.markdown("### 📤 Export & Share")
if st.button("Copy latest summary to clipboard"):
    # attempt to copy - streamlit can't copy to clipboard from server; provide text area for user
    st.info("Below is the latest summary — copy manually if clipboard not supported.")
    if 'history' in st.session_state and st.session_state.history:
        latest = st.session_state.history[-1]['text']
        st.text_area("Latest message", value=latest, height=120)
    else:
        st.info("No messages yet.")
st.markdown("</div>", unsafe_allow_html=True)
