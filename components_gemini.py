import os
import re
import requests
from bs4 import BeautifulSoup
import nltk
from nltk.tokenize import sent_tokenize
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np
from io import BytesIO
from pptx import Presentation
from pptx.util import Inches, Pt

# Audio / TTS
import pyttsx3
try:
    from google.cloud import texttospeech
    GCTTS_AVAILABLE = True
except Exception:
    GCTTS_AVAILABLE = False

# Gemini / Google generative AI client
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except Exception:
    GENAI_AVAILABLE = False

nltk.download('punkt', quiet=True)

# ---------------------------------------------------------
# Configuration: set via environment variables
# - GOOGLE_API_KEY (optional) OR set GOOGLE_APPLICATION_CREDENTIALS for service account
# - GEMINI_MODEL: 'gemini-1.5-flash' or 'gemini-1.5-pro' (default provided in app)
# ---------------------------------------------------------

def configure_genai(api_key=None):
    """Configure google generative ai client if available."""
    if not GENAI_AVAILABLE:
        return False
    key = api_key or os.getenv("GOOGLE_API_KEY")
    if key:
        genai.configure(api_key=key)
        return True
    # genai can also pick up GOOGLE_APPLICATION_CREDENTIALS
    try:
        genai.configure()  # will attempt ADC
        return True
    except Exception:
        return False

# ---------------------------------------------------------
# Web fetcher
# ---------------------------------------------------------
def fetch_url_text(url, timeout=8):
    try:
        headers = {"User-Agent":"PageBuddy-Gemini/1.0"}
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for s in soup(["script","style","noscript","header","footer","svg","img","figure"]):
            s.decompose()
        main = soup.find("main") or soup.find("article") or soup.body
        text = main.get_text(separator=" ", strip=True) if main else soup.get_text(separator=" ", strip=True)
        text = re.sub(r'\s+', ' ', text)
        if len(text) > 25000:
            text = text[:25000] + "..."
        return text
    except Exception as e:
        return f"ERROR: Could not fetch URL: {e}"

# ---------------------------------------------------------
# Extractive fallback summarizer
# ---------------------------------------------------------
def extractive_summary(text, n_sentences=6):
    try:
        sents = sent_tokenize(text)
        if len(sents) <= n_sentences:
            return "\n".join(sents)
        vect = TfidfVectorizer(stop_words='english')
        X = vect.fit_transform(sents)
        scores = np.asarray(X.sum(axis=1)).ravel()
        ranked = np.argsort(scores)[::-1]
        top_idx = np.sort(ranked[:n_sentences])
        summary = " ".join([sents[i] for i in top_idx])
        return summary
    except Exception as e:
        return "Could not summarize (extractive)."

# ---------------------------------------------------------
# Gemini text generation wrapper
# ---------------------------------------------------------
def gemini_generate(prompt, model="gemini-1.5-flash", max_output_tokens=400, temperature=0.2):
    """Generate text using Gemini if configured; otherwise return None."""
    if not GENAI_AVAILABLE:
        return None
    try:
        # try to use genai.generate_text (API surface may vary by client library version)
        # The code handles multiple possible client method names.
        resp = None
        try:
            # new-style: genai.generate_text
            resp = genai.generate_text(model=model, prompt=prompt, max_output_tokens=max_output_tokens, temperature=temperature)
            # some versions return a dict-like; others return an object with .text
            if isinstance(resp, dict):
                return resp.get("candidates",[{}])[0].get("content", "").strip()
            else:
                # attempt to access .text or .content
                return getattr(resp, "text", getattr(resp, "content", str(resp))).strip()
        except Exception:
            # fallback attempt using genai.create or genai.chat.create
            try:
                resp = genai.chat.create(model=model, messages=[{"role":"user","content":prompt}], temperature=temperature, max_output_tokens=max_output_tokens)
                # parse
                return resp.last or str(resp)
            except Exception:
                return None
    except Exception as e:
        return None

# ---------------------------------------------------------
# Top-level summarizer: prefer Gemini -> fallback extractive
# ---------------------------------------------------------
def smart_summarize(text, model="gemini-1.5-flash", language="English", style="anime"):
    """
    language: "English" / "Hindi" / "Telugu"
    style: one of 'anime','formal','corporate','emoji','genz'
    """
    # construct prompt for Gemini
    prompt = (f"You are PageBuddy, an anime-styled futuristic assistant. Summarize the article below into 4 concise bullet points, "
              f"then produce 3 short action items, and 5 short tags. Language: {language}. Style: {style}.\n\nArticle:\n{text[:20000]}")
    out = gemini_generate(prompt, model=model, max_output_tokens=400, temperature=0.15)
    if out:
        return out
    return extractive_summary(text, n_sentences=6)

# ---------------------------------------------------------
# Action items
# ---------------------------------------------------------
def generate_action_items(text, model="gemini-1.5-flash", language="English"):
    prompt = f"From the article below, generate 4 concise action items in {language}, single line each:\n\n{text[:12000]}"
    out = gemini_generate(prompt, model=model, max_output_tokens=200, temperature=0.2)
    if out:
        return out
    # fallback
    sents = sent_tokenize(text)
    return "\n".join(["- " + s.strip() for s in sents[:4]])

# ---------------------------------------------------------
# PPTX export (simple slides)
# ---------------------------------------------------------
def export_to_pptx(title, bullets, actions, filename="pagebuddy_export.pptx"):
    prs = Presentation()
    # title slide
    slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(slide_layout)
    slide.shapes.title.text = title
    # bullet slide
    slide_layout = prs.slide_layouts[1]
    slide = prs.slides.add_slide(slide_layout)
    slide.shapes.title.text = "Key points"
    body = slide.shapes.placeholders[1].text_frame
    for b in bullets:
        p = body.add_paragraph()
        p.text = b
        p.level = 0
        p.font.size = Pt(18)
    # actions slide
    slide = prs.slides.add_slide(slide_layout)
    slide.shapes.title.text = "Action items"
    body = slide.shapes.placeholders[1].text_frame
    for a in actions:
        p = body.add_paragraph()
        p.text = a
        p.level = 0
        p.font.size = Pt(18)
    # save to bytes
    bio = BytesIO()
    prs.save(bio)
    bio.seek(0)
    return bio

# ---------------------------------------------------------
# Text-to-Speech (Google TTS preferred; fallback to pyttsx3)
# ---------------------------------------------------------
def tts_say(text, language_code="en-IN", out_path=None):
    """
    language_code examples: 'en-IN', 'hi-IN', 'te-IN'
    If google cloud tts is available and GOOGLE_APPLICATION_CREDENTIALS is set, uses it.
    Else uses pyttsx3 (local).
    """
    # Try Google Cloud TTS
    if GCTTS_AVAILABLE and os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        try:
            client = texttospeech.TextToSpeechClient()
            synthesis_input = texttospeech.SynthesisInput(text=text)
            # pick voice locale according to language_code
            voice = texttospeech.VoiceSelectionParams(language_code=language_code, ssml_gender=texttospeech.SsmlVoiceGender.FEMALE)
            audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
            response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
            if out_path:
                with open(out_path, "wb") as f:
                    f.write(response.audio_content)
                return out_path
            return BytesIO(response.audio_content)
        except Exception as e:
            # fallback to local
            pass

    # Local TTS fallback
    try:
        engine = pyttsx3.init()
        # try to set voice based on language (best-effort)
        voices = engine.getProperty('voices')
        # best-effort mapping
        for v in voices:
            if language_code.startswith("hi") and "hindi" in v.name.lower():
                engine.setProperty('voice', v.id)
                break
            if language_code.startswith("te") and "telugu" in v.name.lower():
                engine.setProperty('voice', v.id)
                break
        if out_path:
            engine.save_to_file(text, out_path)
            engine.runAndWait()
            return out_path
        # else produce file at temp path
        tmp = "pagebuddy_tts_out.mp3"
        engine.save_to_file(text, tmp)
        engine.runAndWait()
        return tmp
    except Exception as e:
        return None

# ---------------------------------------------------------
# Speech recognition: accepts uploaded audio bytes (wav/mp3)
# Requires SpeechRecognition and pydub
# ---------------------------------------------------------
def speech_to_text_from_bytes(audio_bytes, language="en-IN"):
    import speech_recognition as sr
    from pydub import AudioSegment
    r = sr.Recognizer()
    try:
        # write bytes to temp file
        with open("tmp_audio_in", "wb") as f:
            f.write(audio_bytes)
        # convert to wav if needed
        try:
            aud = AudioSegment.from_file("tmp_audio_in")
            aud.export("tmp_out.wav", format="wav")
            audio_file = sr.AudioFile("tmp_out.wav")
        except Exception:
            audio_file = sr.AudioFile("tmp_audio_in")
        with audio_file as source:
            audio = r.record(source)
        text = r.recognize_google(audio, language=language)
        return text
    except Exception as e:
        return f"ERROR_STT:{e}"
