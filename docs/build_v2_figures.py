"""Publication figures for the VanniKawachh papers (journal/thesis/research).

Clean IEEE-style figures: white background, Times New Roman, restrained
grayscale + one accent. Output: docs/figures/v2/fig1..fig8 PNG @ 300 dpi.

Run:  ..\.venv\Scripts\python.exe build_v2_figures.py
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Rectangle, Polygon

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "figures", "v2")
os.makedirs(OUT, exist_ok=True)

matplotlib.rcParams.update({
    "font.family": ["Times New Roman", "DejaVu Serif"],
    "font.size": 11,
    "savefig.facecolor": "white",
})

INK = "#1a1a1a"; GRAY = "#666666"; LIGHT = "#f2f2f2"; ACC = "#2e5e8c"; RED = "#a03030"; GRN = "#3a6b35"


def newax(w, h):
    fig = plt.figure(figsize=(w, h))
    ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off"); ax.set_aspect("equal")
    return fig, ax


def box(ax, x, y, w, h, label, ec=INK, fc="white", fs=10, lw=1.3, tc=None, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.35",
                                ec=ec, fc=fc, lw=lw))
    ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=fs,
            color=tc or INK, weight="bold" if bold else "normal", linespacing=1.25)


def diamond(ax, cx, cy, w, h, label, ec=INK, fs=9):
    ax.add_patch(Polygon([(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2),
                          (cx - w / 2, cy)], closed=True, ec=ec, fc="white", lw=1.3))
    ax.text(cx, cy, label, ha="center", va="center", fontsize=fs, color=INK, linespacing=1.2)


def arr(ax, p1, p2, c=INK, lw=1.3, style="-|>", rad=0.0, label=None, loff=(0, 1.2), fs=9):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=13, lw=lw,
                                 color=c, connectionstyle=f"arc3,rad={rad}",
                                 shrinkA=4, shrinkB=4))
    if label:
        mx, my = (p1[0] + p2[0]) / 2 + loff[0], (p1[1] + p2[1]) / 2 + loff[1]
        ax.text(mx, my, label, ha="center", va="center", fontsize=fs, color=GRAY, style="italic")


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=300, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print("wrote", path)


# ---- Fig. 1 — system architecture (three tiers) ---------------------------
fig, ax = newax(9.4, 5.0); ax.set_xlim(0, 94); ax.set_ylim(0, 50)
ax.add_patch(Rectangle((2, 33), 90, 15, ec=GRAY, fc=LIGHT, lw=1.0))
ax.text(4, 46.2, "TIER 1 — SENSING NODE (per pole, solar powered)", fontsize=9, color=GRAY, weight="bold")
box(ax, 5, 36, 13, 7, "INMP441\nI2S microphone", fs=9)
box(ax, 23, 36, 17, 7, "ESP32-S3\nMFCC + CNN (TFLM)\nStage 1, < 50 ms", ec=ACC, fs=9)
box(ax, 45, 36, 12, 7, "PIR + LDR\ncontext", fs=9)
box(ax, 62, 36, 12, 7, "SX1278\nLoRa TX", fs=9)
box(ax, 79, 36, 11, 7, "Wi-Fi\nclip TX", fs=9)
arr(ax, (18, 39.5), (23, 39.5)); arr(ax, (40, 39.5), (45, 39.5), style="<|-")
arr(ax, (40, 41), (62, 41), rad=-0.25); arr(ax, (40, 38), (79, 38), rad=0.3)

ax.add_patch(Rectangle((2, 14), 90, 15, ec=GRAY, fc=LIGHT, lw=1.0))
ax.text(4, 27.2, "TIER 2 — HUB (Raspberry Pi 5, per locality)", fontsize=9, color=GRAY, weight="bold")
box(ax, 5, 17, 14, 7, "LoRa gateway\n(ESP32 · USB)", fs=9)
box(ax, 24, 17, 18, 7, "AES-128 unseal\nHMAC + replay check", fs=9)
box(ax, 47, 17, 18, 7, "PANNs Stage 2\n+ PIR/LDR/time fusion", ec=ACC, fs=9)
box(ax, 70, 17, 20, 7, "Police dashboard\nlive map + alarm", fs=9)
arr(ax, (19, 20.5), (24, 20.5)); arr(ax, (42, 20.5), (47, 20.5)); arr(ax, (65, 20.5), (70, 20.5))
arr(ax, (68, 36), (12, 24), label="sealed alert (25 B)", loff=(-12, 1.5))
arr(ax, (84.5, 36), (56, 24), label="4 s WAV clip", loff=(8, 2))

ax.add_patch(Rectangle((2, 1), 90, 9, ec=GRAY, fc=LIGHT, lw=1.0))
ax.text(4, 8.2, "TIER 3 — RESPONSE DRONE (Pixhawk + companion computer)", fontsize=9, color=GRAY, weight="bold")
box(ax, 8, 2.5, 20, 5, "Trigger API + queue\n(landing interlock)", fs=9)
box(ax, 34, 2.5, 22, 5, "Mission executor\n13-state FSM · failsafes", ec=ACC, fs=9)
box(ax, 62, 2.5, 26, 5, "Hover-record → kit drop (3 m)\n→ return to launch", fs=9)
arr(ax, (28, 5), (34, 5)); arr(ax, (56, 5), (62, 5))
arr(ax, (56, 17), (18, 7.5), label="POST /trigger {lat, lon, priority}", loff=(16, 1.5))
save(fig, "fig1_architecture.png")

# ---- Fig. 2 — methodology flowchart ----------------------------------------
fig, ax = newax(6.4, 8.6); ax.set_xlim(0, 64); ax.set_ylim(0, 86)
cx = 27
box(ax, cx - 13, 79, 26, 5, "Victim shouts (“Bachao!” / “Help!”)", fs=9.5, bold=True)
box(ax, cx - 13, 70.5, 26, 5, "INMP441 microphone — listens 24×7", fs=9.5)
box(ax, cx - 13, 62, 26, 5, "Stage 1: MFCC + CNN\nESP32-S3 · < 50 ms", ec=ACC, fs=9.5)
diamond(ax, cx, 54, 22, 7.5, "distress-like?", fs=9.5)
box(ax, cx - 13, 42.5, 26, 5, "Stage 2: PANNs + sensor fusion\nRaspberry Pi 5 · PIR + LDR + time", ec=ACC, fs=9.5)
diamond(ax, cx, 34.5, 24, 7.5, "genuine distress?", fs=9.5)
box(ax, cx - 13, 23, 26, 5, "AES-128 alert + node GPS\n(25-byte sealed packet)", fs=9.5)
box(ax, cx - 13, 14.5, 26, 5, "LoRa uplink — no cellular", fs=9.5)
box(ax, 2, 3, 26, 6, "Police dashboard\nlive map + audible alarm", fs=9.5)
box(ax, 36, 3, 26, 6, "Drone auto-dispatch\nfly → record → kit drop → RTL", ec=ACC, fs=9.5)
arr(ax, (cx, 79), (cx, 75.5)); arr(ax, (cx, 70.5), (cx, 67))
arr(ax, (cx, 62), (cx, 57.8))
arr(ax, (cx, 50.2), (cx, 47.5), label="yes", loff=(3, 0))
arr(ax, (38, 54), (52, 54), label="no", loff=(0, 1.6))
ax.plot([52, 52], [54, 73], color=INK, lw=1.3)
arr(ax, (52, 73), (40, 73), style="-|>")
ax.text(53.5, 63, "keep listening", rotation=90, fontsize=8.5, color=GRAY, style="italic")
arr(ax, (cx, 42.5), (cx, 38.3))
arr(ax, (cx, 30.7), (cx, 28), label="yes", loff=(3, 0))
arr(ax, (39, 34.5), (57, 34.5), label="discard", loff=(0, 1.6))
arr(ax, (cx, 23), (cx, 19.5)); arr(ax, (cx, 14.5), (15, 9), rad=0.12); arr(ax, (cx, 14.5), (49, 9), rad=-0.12)
save(fig, "fig2_methodology.png")

# ---- Fig. 3 — two-stage pipeline (signal view) -----------------------------
fig, ax = newax(9.4, 3.6); ax.set_xlim(0, 94); ax.set_ylim(0, 36)
box(ax, 2, 14, 10, 8, "audio\n16 kHz", fs=9)
box(ax, 16, 14, 13, 8, "pre-emphasis\n+ framing\n(32 ms)", fs=9)
box(ax, 33, 14, 13, 8, "mel filterbank\n+ log + DCT\n(13 MFCC)", fs=9)
box(ax, 50, 14, 13, 8, "CNN (int8)\n3 conv + dense\nsoftmax", ec=ACC, fs=9)
diamond(ax, 71, 18, 13, 9, "p ≥ 0.60?", fs=9)
box(ax, 81, 24, 12, 8, "alert +\n4 s clip", ec=RED, fs=9)
box(ax, 81, 6, 12, 8, "discard\n(on device)", fs=9)
for x1, x2 in [(12, 16), (29, 33), (46, 50), (63, 64.5)]:
    arr(ax, (x1, 18), (x2, 18))
arr(ax, (74.5, 22), (81, 27), label="yes", loff=(-1, 1.5))
arr(ax, (74.5, 14), (81, 10.5), label="no", loff=(-1, -1.6))
ax.text(32, 30.5, "STAGE 1 — on the ESP32-S3 (recall-tuned)", fontsize=9.5, color=GRAY, weight="bold")
ax.text(32, 2.5, "Stage 2 (hub): PANNs AudioSet tagging over the clip → fused with PIR/LDR/time → dispatch gates",
        fontsize=9, color=GRAY, style="italic", ha="center")
save(fig, "fig3_pipeline.png")

# ---- Fig. 4 — packet wire format -------------------------------------------
fig, ax = newax(9.4, 2.9); ax.set_xlim(0, 94); ax.set_ylim(0, 29)
fields = [("magic\n“VK”", 2, LIGHT), ("ver", 1, LIGHT), ("node_id", 2, LIGHT),
          ("counter (replay)", 4, LIGHT), ("AES-128-CTR ciphertext\nevent·conf·PIR·light·batt", 8, "#dce8f4"),
          ("HMAC-SHA256 tag\n(truncated)", 8, "#f4dcdc")]
x = 3; total = 88.0 / 25.0
for label, nbytes, fc in fields:
    w = nbytes * total
    ax.add_patch(Rectangle((x, 12), w, 9, ec=INK, fc=fc, lw=1.2))
    ax.text(x + w / 2, 16.5, label, ha="center", va="center", fontsize=8.5, linespacing=1.2)
    ax.text(x + w / 2, 9.8, f"{nbytes} B", ha="center", fontsize=8, color=GRAY)
    x += w
ax.text(3, 25.5, "Sealed alert packet — 25 bytes total (one LoRa frame)", fontsize=10, weight="bold")
ax.text(3, 4.5, "cleartext header (selects per-node key; CTR nonce)          "
                "confidentiality: AES-128-CTR          authenticity: encrypt-then-MAC",
        fontsize=8.5, color=GRAY)
save(fig, "fig4_packet.png")

# ---- Fig. 5 — mission state machine (13 states) ----------------------------
fig, ax = newax(9.4, 4.4); ax.set_xlim(0, 94); ax.set_ylim(0, 44)
r1 = ["IDLE", "CONNECTING", "WAITING_GPS", "ARMING", "TAKEOFF"]
r2 = ["ENROUTE", "HOVERING", "DELIVERING", "RTL", "LANDED"]
xs = [3, 21.5, 40, 58.5, 77]; w = 14; hb = 6
for i, lab in enumerate(r1):
    box(ax, xs[i], 31, w, hb, lab, fs=9)
    if i:
        arr(ax, (xs[i - 1] + w, 34), (xs[i], 34))
for i, lab in enumerate(r2):
    ec = ACC if lab == "DELIVERING" else INK
    box(ax, xs[i], 17, w, hb, lab, ec=ec, fs=9)
    if i:
        arr(ax, (xs[i - 1] + w, 20), (xs[i], 20))
arr(ax, (xs[4] + w / 2, 31), (xs[0] + w / 2, 23), rad=0.35)
box(ax, 12, 4, 15, 6, "COMPLETED", ec=GRN, fs=9)
box(ax, 40, 4, 14, 6, "ABORTED", ec=RED, fs=9)
box(ax, 62, 4, 14, 6, "FAILED", ec=RED, fs=9)
arr(ax, (xs[4] + w / 2, 17), (19.5, 10), rad=0.25)
arr(ax, (47, 17), (47, 10), c=RED, label="any phase", loff=(8, 0))
arr(ax, (69, 17), (69, 10), c=RED)
ax.text(47, 41.5, "DELIVERING: descend to 3 m → servo release → climb back (release failure ⇒ proceed to RTL)",
        fontsize=9, color=GRAY, style="italic", ha="center")
save(fig, "fig5_state_machine.png")

# ---- Fig. 6 — five-gate safety interlock -----------------------------------
fig, ax = newax(9.4, 2.7); ax.set_xlim(0, 94); ax.set_ylim(0, 27)
gates = [("1\nEdge validation\ngeofence + bounds",), ("2\nSerial queue\none mission at a time",),
         ("3\nGPS-lock\npre-arm gate",), ("4\nFailsafe arbiter\n1 Hz, severity-ordered",),
         ("5\nLanding interlock\nblock until disarm",)]
gx = 3; gw = 16; gap = 2.5
for i, (lab,) in enumerate(gates):
    box(ax, gx, 8, gw, 12, lab, fs=8.8, ec=ACC if i == 4 else INK)
    if i:
        arr(ax, (gx - gap, 14), (gx, 14), lw=1.6)
    gx += gw + gap
ax.text(47, 3, "Invariant: no mission is ever commenced against an armed or airborne vehicle.",
        fontsize=9.5, color=GRAY, style="italic", ha="center")
save(fig, "fig6_interlock.png")

# ---- Fig. 7 — evidence fusion block ----------------------------------------
fig, ax = newax(7.6, 4.2); ax.set_xlim(0, 76); ax.set_ylim(0, 42)
inputs = [("Stage-2 audio score  a", "0.60", 35), ("Stage-1 confidence  c", "0.15", 28),
          ("PIR motion  p ∈ {0,1}", "0.10", 21), ("darkness  d = 1 − L/255", "0.08", 14),
          ("night  n ∈ {0,1}", "0.07", 7)]
for lab, wt, y in inputs:
    box(ax, 2, y, 26, 5, lab, fs=9)
    arr(ax, (28, y + 2.5), (40, 23), label=f"w = {wt}", loff=(0, 1.4), rad=0.06)
ax.add_patch(Circle((43, 23), 3.4, ec=INK, fc="white", lw=1.4))
ax.text(43, 23, "Σ", fontsize=15, ha="center", va="center")
box(ax, 51, 19.5, 22, 7, "severity S ∈ [0, 1]\ndispatch iff a ≥ 0.50 ∧ S ≥ 0.60", ec=ACC, fs=9)
arr(ax, (46.5, 23), (51, 23))
ax.text(38, 3.5, "S = 0.60a + 0.15c + 0.10p + 0.08d + 0.07n", fontsize=11, ha="center", style="italic")
save(fig, "fig7_fusion.png")

# ---- Fig. 8 — Phase-0 mission altitude profile ------------------------------
fig = plt.figure(figsize=(8.2, 3.4))
axp = fig.add_subplot(111)
t =  [0, 12, 25, 38, 48, 160, 165, 175, 205, 215, 225, 235, 250, 350, 395, 410]
alt = [0, 0,  5.5, 13.8, 15, 15, 15,  15,  14,  6.5, 3.1, 7.0, 15,  15,  2.0, 0.1]
axp.plot(t, alt, color=ACC, lw=1.8)
axp.fill_between(t, alt, color=ACC, alpha=0.08)
for tx, ty, lab in [(30, 8, "takeoff"), (100, 16.2, "enroute (896 m)"), (170, 16.2, "hover +\nrecord"),
                    (222, 4.5, "kit drop\n@ 3.1 m"), (300, 16.2, "return to launch"), (398, 4.5, "land")]:
    axp.annotate(lab, xy=(tx, ty), fontsize=9, color=GRAY, ha="center", style="italic")
axp.axhline(3.0, color=RED, lw=0.9, ls=(0, (4, 3)), alpha=0.6)
axp.text(6, 3.5, "drop altitude 3 m", fontsize=8, color=RED)
axp.set_xlabel("mission time (s)"); axp.set_ylabel("altitude AGL (m)")
axp.set_ylim(0, 18); axp.set_xlim(0, 415)
axp.spines[["top", "right"]].set_visible(False)
save(fig, "fig8_mission_profile.png")

print("all v2 figures generated")
