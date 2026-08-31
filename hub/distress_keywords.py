"""Narrow emergency-keyword matching shared by the speech-alert path."""
from __future__ import annotations

import re
import unicodedata


PHRASES = (
    "help me", "please help", "somebody help", "someone help", "send help",
    "save me", "save us", "rescue me", "emergency", "bachao", "madad",
    "mujhe bachao", "meri madad", "help",
)
DEVANAGARI = {
    "बचाओ": "bachao", "मदद": "madad", "मुझे बचाओ": "mujhe bachao",
    "मेरी मदद": "meri madad", "हेल्प": "help",
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
    return " ".join(re.sub(r"[^a-z\s]", " ", text).split())


def match_distress_keyword(transcript: str) -> str | None:
    normalized = normalize_transcript(transcript)
    padded = f" {normalized} "
    for phrase in PHRASES:
        if f" {phrase} " in padded:
            return phrase
    return None
