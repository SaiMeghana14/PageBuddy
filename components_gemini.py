import os, json, re, time
import requests, base64
from bs4 import BeautifulSoup
import nltk
from nltk.tokenize import sent_tokenize
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np
from io import BytesIO

# Audio
try:
    from google.cloud import texttospeech, speech
    GCP_AUDIO_AVAILABLE = True
except Exception:
    GCP_AUDIO_AVAILABLE = False

# Gemini client detection
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

# unify name for client
GEN_CLIENT = GENAI

# Optional GCP TTS/STT clients
GCP_AUDIO = False
try:
    from google.cloud import texttospeech, speech
    GCP_AUDIO = True
except Exception:
    GCP_AUDIO = False
    
nltk.download('punkt', quiet=True)

# --------------- credential helpers ---------------
def load_service_account_from_streamlit_secrets(st_secrets):
    """
    Writes service account JSON from st.secrets["google"]["credentials"] to /tmp and sets env var.
    Returns True if file written.
    """
    try:
        creds = st_secrets["google"]["credentials"]
        if isinstance(creds, str):
            cred_dict = json.loads(creds)
        else:
            cred_dict = creds
        path = "/tmp/gcp_pagebuddy_creds.json"
        with open(path, "w") as f:
            json.dump(cred_dict, f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
        # configure genai if available
        try:
            if GEN_CLIENT == "genai":
                genai.configure()  # will use ADC
        except Exception:
            pass
        return True
    except Exception:
        return False

# ----------------- Gemini wrapper -----------------
def _gemini_generate_text(prompt, model="gemini-1.5-flash", max_output_tokens=400, temperature=0.2):
    """Return string or None if unavailable."""
    try:
        if GEN_CLIENT == "genai":
            resp = genai.generate_text(model=model, prompt=prompt, max_output_tokens=max_output_tokens, temperature=temperature)
            if isinstance(resp, dict):
                return resp.get("candidates",[{}])[0].get("content","").strip()
            return getattr(resp, "text", getattr(resp, "content", str(resp))).strip()
        elif GEN_CLIENT == "vertexai":
            from vertexai import language as vlang
            model_obj = vlang.TextGenerationModel.from_pretrained(model)
            response = model_obj.predict(prompt, max_output_tokens=max_output_tokens, temperature=temperature)
            return response.text
    except Exception as e:
        return None
    return None

# ----------------- Summarize & actions -----------------
def smart_summarize(text, model="gemini-1.5-flash", language="English", style="anime"):
    prompt = (f"You are NOVA, a calm futuristic assistant. Summarize the article into 4 short bullets, "
              f"then 3 action items and 5 tags. Language: {language}. Style: {style}.\n\nArticle:\n{text[:16000]}")
    out = _gemini_generate_text(prompt, model=model, max_output_tokens=420, temperature=0.15)
    if out:
        return out
    # fallback extractive
    return extractive_summary(text, 6)

def generate_action_items(text, model="gemini-1.5-flash", language="English"):
    prompt = f"Create 4 concise action items from the text in {language}:\n\n{text[:12000]}"
    out = _gemini_generate_text(prompt, model=model, max_output_tokens=200, temperature=0.2)
    if out:
        return out
    sents = sent_tokenize(text)
    return "\n".join(["- " + s.strip() for s in sents[:4]])

# ----------------- Extractive fallback -----------------
def extractive_summary(text, n_sentences=6):
    try:
        sents = sent_tokenize(text)
        if len(sents) <= n_sentences:
            return "\n".join(sents)
        from sklearn.feature_extraction.text import TfidfVectorizer
        import numpy as np
        vect = TfidfVectorizer(stop_words='english')
        X = vect.fit_transform(sents)
        scores = np.asarray(X.sum(axis=1)).ravel()
        ranked = np.argsort(scores)[::-1]
        top_idx = np.sort(ranked[:n_sentences])
        return " ".join([sents[i] for i in top_idx])
    except Exception:
        return text[:800] + ("..." if len(text) > 800 else "")

# ----------------- Flashcards / topics / todos -----------------
def extract_topics(text, model="gemini-1.5-flash", top_n=6):
    prompt = f"Extract {top_n} short topics/section headers from this article, comma-separated:\n\n{text[:12000]}"
    out = _gemini_generate_text(prompt, model=model, max_output_tokens=180, temperature=0.0)
    if out:
        parts = re.split(r'[\n,;]+', out)
        return [p.strip() for p in parts if p.strip()][:top_n]
    # fallback naive
    sents = sent_tokenize(text)
    return [s[:40] for s in sents[:top_n]]

def generate_flashcards(text, model="gemini-1.5-flash", count=8, language="English"):
    prompt = (f"Create {count} concise flashcards (Q -> A) from the article below. Provide them as JSON list of objects "
              f'like [{{"q":"...", "a":"..."}}]. Language: {language}.\n\n{text[:15000]}')
    out = _gemini_generate_text(prompt, model=model, max_output_tokens=420, temperature=0.2)
    if out:
        try:
            return json.loads(out)
        except Exception:
            # simple parse
            cards=[]
            lines = [l.strip() for l in out.splitlines() if l.strip()]
            q,a=None,None
            for l in lines:
                if l.lower().startswith("q:"):
                    q = l.split(":",1)[1].strip()
                elif l.lower().startswith("a:"):
                    a = l.split(":",1)[1].strip()
                if q and a:
                    cards.append({"q":q,"a":a})
                    q,a=None,None
            return cards[:count]
    sents = sent_tokenize(text)
    cards=[]
    for i in range(count):
        q = sents[i*2] if i*2 < len(sents) else f"Concept {i+1}"
        a = sents[i*2+1] if i*2+1 < len(sents) else ""
        cards.append({"q":q,"a":a})
    return cards

def generate_todos(text, model="gemini-1.5-flash", language="English"):
    prompt = f"From the article, generate 6 actionable to-do items. Language: {language}\n\n{text[:12000]}"
    out = _gemini_generate_text(prompt, model=model, max_output_tokens=180, temperature=0.15)
    if out:
        return [l.strip("-• \n") for l in out.splitlines() if l.strip()][:6]
    return ["Save article","Summarize key points","Make flashcards","Find references","Share with a peer","Schedule review"]

# ----------------- Sentiment -> Emotion mapping -----------------
def sentiment_of_text(text, model="gemini-1.5-flash"):
    prompt = f"Provide one-word sentiment (positive/neutral/negative) for the text:\n\n{text[:5000]}"
    out = _gemini_generate_text(prompt, model=model, max_output_tokens=40, temperature=0.0)
    if out:
        first = out.splitlines()[0].lower()
        if "positive" in first: return "positive"
        if "negative" in first: return "negative"
    return "neutral"

def analyze_emotion(text):
    s = sentiment_of_text(text)
    mapping = {"positive":"happy","neutral":"listening","negative":"concerned"}
    return mapping.get(s,"listening")

# ----------------- Translate helper -----------------
def translate_text(text, target_language="Hindi", model="gemini-1.5-flash"):
    prompt = f"Translate to {target_language}:\n\n{text[:12000]}"
    out = _gemini_generate_text(prompt, model=model, max_output_tokens=400, temperature=0.0)
    if out:
        return out.strip()
    return text

# ----------------- TTS (GCP) and fallback -----------------
def tts_create_audio_bytes(text, language_code="en-IN"):
    """
    Return bytes of MP3 if possible else None.
    """
    if GCP_AUDIO and os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        try:
            client = texttospeech.TextToSpeechClient()
            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams(language_code=language_code, ssml_gender=texttospeech.SsmlVoiceGender.FEMALE)
            audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
            response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
            return response.audio_content
        except Exception:
            pass
    # fallback: pyttsx3 on server (might not be available on Streamlit Cloud)
    try:
        import pyttsx3
        tmp="/tmp/pagebuddy_tts.mp3"
        engine = pyttsx3.init()
        engine.save_to_file(text, tmp)
        engine.runAndWait()
        with open(tmp,"rb") as f:
            return f.read()
    except Exception:
        return None

# ----------------- STT (GCP or SpeechRecognition fallback) -----------------
def stt_from_uploaded_bytes(audio_bytes, language="en-IN"):
    if GCP_AUDIO and os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        try:
            client = speech.SpeechClient()
            audio = speech.RecognitionAudio(content=audio_bytes)
            config = speech.RecognitionConfig(encoding=speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED,
                                              sample_rate_hertz=16000, language_code=language)
            response = client.recognize(config=config, audio=audio)
            return " ".join([r.alternatives[0].transcript for r in response.results])
        except Exception:
            pass
    # fallback local
    try:
        import speech_recognition as sr
        from pydub import AudioSegment
        with open("/tmp/tmp_in_audio", "wb") as f:
            f.write(audio_bytes)
        aud = AudioSegment.from_file("/tmp/tmp_in_audio")
        aud.export("/tmp/tmp_out.wav", format="wav")
        r = sr.Recognizer()
        with sr.AudioFile("/tmp/tmp_out.wav") as source:
            audio = r.record(source)
        return r.recognize_google(audio)
    except Exception as e:
        return f"ERROR_STT:{e}"

# ----------------- tiny lipsync helper (estimate durations) -----------------
def estimate_audio_duration_seconds(text):
    # rough heuristic: 12-15 chars per second spoken
    chars = max(1, len(text))
    return max(1.0, chars / 18.0)
    
