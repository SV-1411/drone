"""Severity fusion — combine Stage-2 audio score with environmental evidence.

A night-time scream in a dark spot with motion nearby is a different animal
from a daytime shout on a busy road. The fused severity drives both the
dispatch decision and the mission priority.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from .packets import Alert


@dataclass
class Severity:
    score: float       # 0.0 .. 1.0 fused severity
    priority: str      # "normal" | "high" — maps onto TriggerRequest.priority
    reasons: str       # human-readable trace for the log / dashboard


def fuse(alert: Alert, audio_score: float, now_hour: float | None = None) -> Severity:
    """Weighted evidence fusion.

    audio (stage-2) dominates; stage-1 confidence, PIR motion, darkness and
    night hours each nudge the score. Weights are prototype values — tune
    them against Phase-1 bench data.
    """
    if now_hour is None:
        now_hour = time.localtime().tm_hour + time.localtime().tm_min / 60.0

    darkness = 1.0 - (alert.light / 255.0)          # 1.0 = pitch dark
    is_night = 1.0 if (now_hour >= 20.0 or now_hour < 6.0) else 0.0

    score = (
        0.60 * audio_score +
        0.15 * alert.confidence +
        0.10 * (1.0 if alert.pir else 0.0) +
        0.08 * darkness +
        0.07 * is_night
    )
    score = round(min(1.0, max(0.0, score)), 3)

    reasons = (f"audio={audio_score:.2f} stage1={alert.confidence:.2f} "
               f"pir={'Y' if alert.pir else 'N'} dark={darkness:.2f} "
               f"night={'Y' if is_night else 'N'}")
    priority = "high" if score >= 0.75 or (audio_score >= 0.6 and alert.pir) else "normal"
    return Severity(score=score, priority=priority, reasons=reasons)
