import os
import re
import requests
from bs4 import BeautifulSoup
import openai
import nltk
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np
nltk.download('punkt', quiet=True)
from nltk.tokenize import sent_tokenize

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_KEY:
    openai.api_key = OPENAI_KEY

def fetch_url_text(url, timeout=8):
    """Fetch page and extract readable text (basic)."""
    try:
        headers = {"User-Agent":"PageBuddy/1.0 (+https://example.com)"}
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # remove scripts/styles
        for s in soup(["script","style","noscript","header","footer","svg","img","figure"]):
            s.decompose()

        # attempt to find article/main content
        main = soup.find("main")
        if main:
            text = main.get_text(separator=" ", strip=True)
        else:
            article = soup.find("article")
            if article:
                text = article.get_text(separator=" ", strip=True)
            else:
                # fallback use body
                body = soup.body
                text = body.get_text(separator=" ", strip=True) if body else soup.get_text(separator=" ", strip=True)

        # remove excessive whitespace and short lines
        text = re.sub(r'\s+', ' ', text)
        # shorten if huge
        if len(text) > 20000:
            text = text[:20000] + "..."
        return text
    except Exception as e:
        return f"ERROR: Could not fetch URL: {e}"

def openai_summarize(text, role="assistant", max_tokens=300):
    """Call OpenAI GPT summarization (if API key present)."""
    if not OPENAI_KEY:
        return None
    try:
        prompt = (f"You're PageBuddy, an anime-themed, friendly assistant. "
                  f"Summarize the following article into a concise, readable summary (3-6 bullets), then 3 action items and 3 tags.\n\nArticle:\n{text[:16000]}")
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini", # if not available, Streamlit user should set to a compatible model
            messages=[{"role":"system","content":"You are PageBuddy, an anime-themed assistant."},
                      {"role":"user","content":prompt}],
            temperature=0.25,
            max_tokens=max_tokens
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        # try older API
        try:
            resp = openai.Completion.create(
                engine="text-davinci-003",
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=0.25
            )
            return resp.choices[0].text.strip()
        except Exception as e2:
            return f"OpenAI Error: {e} / {e2}"

def extractive_summary(text, n_sentences=6):
    """Simple TF-IDF based extractive summarizer as fallback."""
    try:
        sents = sent_tokenize(text)
        if len(sents) <= n_sentences:
            return "\n\n".join(sents)
        vect = TfidfVectorizer(stop_words='english')
        X = vect.fit_transform(sents)
        scores = np.asarray(X.sum(axis=1)).ravel()
        ranked = np.argsort(scores)[::-1]
        top_idx = np.sort(ranked[:n_sentences])
        summary = " ".join([sents[i] for i in top_idx])
        return summary
    except Exception as e:
        return "Could not summarize (extractive)."

def smart_summarize(text):
    """Top-level: prefer OpenAI; fallback to extractive"""
    if OPENAI_KEY:
        out = openai_summarize(text)
        if out and not out.startswith("OpenAI Error"):
            return out
    # fallback
    return extractive_summary(text, n_sentences=6)

def generate_action_items(text, count=3):
    """Small heuristic action generator using OpenAI if present, else naive extraction."""
    if OPENAI_KEY:
        try:
            prompt = f"From the article below, generate {count} concise action items (single-line) that a reader can take.\n\n{text[:12000]}"
            resp = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role":"system","content":"You are PageBuddy, help the user act on content."},
                          {"role":"user","content":prompt}],
                temperature=0.25,
                max_tokens=180
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            pass
    # Naive fallback: pick leading sentences
    sents = sent_tokenize(text)
    items = []
    for s in sents[:count]:
        items.append("- " + s.strip())
    return "\n".join(items)
