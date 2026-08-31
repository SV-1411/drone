"""Narrow emergency-keyword matching shared by the speech-alert path."""
from __future__ import annotations

import re
import unicodedata


PHRASES = (
    # Longer phrases must precede their component words.
    "please help", "help me", "help us", "somebody help", "someone help", "send help",
    "save me", "save us", "rescue me", "call police", "call the police",
    "mujhe bachao", "bachao mujhe", "mujhe bachalo", "meri madad karo",
    "meri madad", "madad karo", "madad kijiye", "help", "bachao", "madad",
    "emergency", "danger", "fire", "police", "aag", "please",
)
DEVANAGARI = {
    "बचाओ": "bachao", "मदद": "madad", "मुझे बचाओ": "mujhe bachao",
    "मेरी मदद": "meri madad", "हेल्प": "help",
}

# Common Chrome/Android ASR renderings of a distressed Hindi call.  These are
# deliberately narrow aliases, not fuzzy matching: a high-pitched unrelated
# word must still fail the independent vocal-stress gate in speech_alert.
ASR_TOKEN_ALIASES = {
    "bajao": "bachao", "batao": "bachao", "bachau": "bachao",
    "bachaao": "bachao", "bacchao": "bachao", "madat": "madad",
    "maddad": "madad", "halp": "help", "halep": "help",
}


def normalize_transcript(transcript: str) -> str:
    """Retain word boundaries while accepting elongated ASR spellings."""
    text = str(transcript or "").casefold().strip()
    for source, replacement in DEVANAGARI.items():
        text = text.replace(source, replacement)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    # heeelp -> help and bachaaaooo -> bachao; hello remains helo, never help.
    text = re.sub(r"([a-z])\1+", r"\1", text)
    words = re.sub(r"[^a-z\s]", " ", text).split()
    return " ".join(ASR_TOKEN_ALIASES.get(word, word) for word in words)


def match_distress_keyword(transcript: str) -> str | None:
    normalized = normalize_transcript(transcript)
    padded = f" {normalized} "
    for phrase in PHRASES:
        if f" {phrase} " in padded:
            return phrase
    return None
