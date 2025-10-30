import os
import json
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

# Audio
import pyttsx3
try:
    from google.cloud import texttospeech, speech
    GCP_AUDIO_AVAILABLE = True
except Exception:
    GCP_AUDIO_AVAILABLE = False

# Gemini client options: try google.generativeai then vertexai
GENAI = None
try:
    import google.generativeai as genai
    GENAI = "genai"
except Exception:
    try:
        from vertexai import language as vlang
        GENAI = "vertexai"
    except Exception:
        GENAI = None

nltk.download('punkt', quiet=True)

# --------------- credential helpers ---------------
def load_service_account_from_streamlit_secrets(st_secrets):
    """
    st_secrets should contain st.secrets["google"]["credentials"] JSON (string or dict)
    Writes temp file and sets env var GOOGLE_APPLICATION_CREDENTIALS
    """
    if not st_secrets:
        return False
    try:
        creds = st_secrets["google"]["credentials"]
        if isinstance(creds, str):
            cred_dict = json.loads(creds)
        else:
            cred_dict = creds
        tmp_path = "/tmp/gcp_pagebuddy_creds.json"
        with open(tmp_path, "w") as f:
            json.dump(cred_dict, f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp_path
        # if genai available, configure
        try:
            if GENAI == "genai":
                genai.configure(api_key=os.environ.get("GOOGLE_API_KEY", None))
        except Exception:
            pass
        return True
    except Exception:
        return False

# --------------- web fetcher & extractive fallback ---------------
def fetch_url_text(url, timeout=8):
    try:
        headers = {"User-Agent":"PageBuddy/1.0"}
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
    except Exception:
        return "Could not summarize."

# --------------- Gemini wrapper ---------------
def _gemini_generate_text(prompt, model="gemini-1.5-flash", max_output_tokens=420, temperature=0.2):
    """Try to generate with available client, return string or None."""
    try:
        if GENAI == "genai":
            resp = genai.generate_text(model=model, prompt=prompt, max_output_tokens=max_output_tokens, temperature=temperature)
            # some client versions return dict-like
            if isinstance(resp, dict):
                return resp.get("candidates",[{}])[0].get("content","").strip()
            # else try attribute
            return getattr(resp, "text", getattr(resp, "content", str(resp))).strip()
        elif GENAI == "vertexai":
            # minimal usage of vertexai language
            from vertexai import language as vlang
            model_obj = vlang.TextGenerationModel.from_pretrained(model)
            response = model_obj.predict(prompt, max_output_tokens=max_output_tokens, temperature=temperature)
            return response.text
    except Exception:
        return None

def smart_summarize(text, model="gemini-1.5-flash", language="English", style="anime"):
    prompt = (f"You are PageBuddy, an anime hologram assistant. "
              f"Summarize the article below into 4 concise bullet points, then give 3 short action items and 5 tags. "
              f"Language: {language}. Style: {style}.\n\nArticle:\n{text[:18000]}")
    out = _gemini_generate_text(prompt, model=model, max_output_tokens=420, temperature=0.15)
    if out:
        return out
    return extractive_summary(text, n_sentences=6)

def generate_action_items(text, model="gemini-1.5-flash", language="English"):
    prompt = f"From the article below, generate 4 concise action items in {language}, one per line:\n\n{text[:12000]}"
    out = _gemini_generate_text(prompt, model=model, max_output_tokens=200, temperature=0.2)
    if out:
        return out
    sents = sent_tokenize(text)
    return "\n".join(["- " + s.strip() for s in sents[:4]])

# --------------- PPTX export ---------------
def export_to_pptx(title, bullets, actions):
    prs = Presentation()
    slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(slide_layout)
    slide.shapes.title.text = title
    slide_layout = prs.slide_layouts[1]
    slide = prs.slides.add_slide(slide_layout)
    slide.shapes.title.text = "Key points"
    body = slide.shapes.placeholders[1].text_frame
    for b in bullets:
        p = body.add_paragraph()
        p.text = b
        p.level = 0
        p.font.size = Pt(18)
    slide = prs.slides.add_slide(slide_layout)
    slide.shapes.title.text = "Action items"
    body = slide.shapes.placeholders[1].text_frame
    for a in actions:
        p = body.add_paragraph()
        p.text = a
        p.level = 0
        p.font.size = Pt(18)
    bio = BytesIO()
    prs.save(bio)
    bio.seek(0)
    return bio

# --------------- TTS ---------------
def tts_create_audio_bytes(text, language_code="en-IN"):
    """
    Returns bytes (mp3) or None.
    Prefer Google Cloud TTS if creds present, else fallback to pyttsx3 file path.
    """
    if GCP_AUDIO_AVAILABLE and os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        try:
            client = texttospeech.TextToSpeechClient()
            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams(language_code=language_code, ssml_gender=texttospeech.SsmlVoiceGender.FEMALE)
            audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
            response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
            return response.audio_content  # bytes
        except Exception:
            pass
    # fallback to local pyttsx3 -> save file and return bytes
    try:
        tmp = "/tmp/pagebuddy_tts.mp3"
        engine = pyttsx3.init()
        engine.save_to_file(text, tmp)
        engine.runAndWait()
        with open(tmp, "rb") as f:
            return f.read()
    except Exception:
        return None

# --------------- Speech-to-text for uploaded audio ---------------
def stt_from_uploaded_bytes(audio_bytes, language="en-IN"):
    """
    Tries Google Speech-to-Text if available; else fallback to recognize_google via SpeechRecognition.
    """
    if GCP_AUDIO_AVAILABLE and os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        try:
            client = speech.SpeechClient()
            audio = speech.RecognitionAudio(content=audio_bytes)
            config = speech.RecognitionConfig(encoding=speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED,
                                              sample_rate_hertz=16000, language_code=language)
            response = client.recognize(config=config, audio=audio)
            results = [r.alternatives[0].transcript for r in response.results]
            return " ".join(results)
        except Exception:
            pass
    # fallback using SpeechRecognition + pydub
    try:
        import speech_recognition as sr
        from pydub import AudioSegment
        with open("/tmp/tmp_audio_in", "wb") as f:
            f.write(audio_bytes)
        try:
            aud = AudioSegment.from_file("/tmp/tmp_audio_in")
            aud.export("/tmp/tmp_audio_out.wav", format="wav")
            filename = "/tmp/tmp_audio_out.wav"
        except Exception:
            filename = "/tmp/tmp_audio_in"
        r = sr.Recognizer()
        with sr.AudioFile(filename) as source:
            audio = r.record(source)
        text = r.recognize_google(audio, language=language)
        return text
    except Exception as e:
        return f"ERROR_STT:{e}"
