"""Generate all paper diagrams from scratch with matplotlib.

Every figure is hand-coded in this file — no external image is loaded, no
clip-art is included, no third-party diagram is reused. The script is the
single source of truth, so the diagrams are guaranteed original.

Run from project root:
    python docs/build_diagrams.py

Output: docs/figures/architecture.png, state_machine.png, sequence.png,
flight_trajectory.png, failsafe_tree.png
"""
from __future__ import annotations

import math
import os

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
from matplotlib.patches import Circle, ConnectionPatch

HERE = os.path.dirname(os.path.abspath(__file__))
FIGDIR = os.path.join(HERE, "figures")
os.makedirs(FIGDIR, exist_ok=True)

# Project palette (navy / accent blue / amber / leaf / grey)
NAVY = "#1F3A5F"
DARK_NAVY = "#0D1F3D"
ACCENT = "#58A6FF"
AMBER = "#D29922"
LEAF = "#1F6F3A"
RUST = "#8A1F1F"
GREY = "#8B949E"
PAPER = "#F6F8FA"
INK = "#0D1117"


def _box(ax, x, y, w, h, text, fill=PAPER, edge=NAVY, text_color=INK, fs=10, bold=False):
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.04",
        linewidth=1.4, edgecolor=edge, facecolor=fill,
    )
    ax.add_patch(box)
    ax.text(x + w / 2, y + h / 2, text,
            ha="center", va="center", fontsize=fs,
            color=text_color, fontweight="bold" if bold else "normal", wrap=True)


def _arrow(ax, x1, y1, x2, y2, color=NAVY, label=None, label_pos=0.5, label_color=NAVY, lw=1.4, style="->"):
    arr = FancyArrowPatch((x1, y1), (x2, y2),
                          arrowstyle=style, mutation_scale=14,
                          linewidth=lw, color=color)
    ax.add_patch(arr)
    if label:
        lx = x1 + (x2 - x1) * label_pos
        ly = y1 + (y2 - y1) * label_pos
        ax.text(lx, ly + 0.08, label, ha="center", va="bottom",
                fontsize=8.5, color=label_color, style="italic")


# ----------------------------------------------------------------------------
# Figure 1 — Component architecture
# ----------------------------------------------------------------------------

def fig_architecture() -> str:
    fig, ax = plt.subplots(figsize=(10.4, 5.6), dpi=180)
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 6)
    ax.axis("off")

    # Title at very top
    ax.text(5.5, 5.7, "Figure 1. Component architecture",
            ha="center", fontsize=12, color=DARK_NAVY, fontweight="bold")

    # Row labels (placed at the top of each lane)
    ax.text(1.45, 5.0, "Browser process",
            ha="center", fontsize=8.5, color=GREY, style="italic")
    ax.text(5.5, 5.0, "Companion-computer process",
            ha="center", fontsize=8.5, color=GREY, style="italic")
    ax.text(9.65, 5.0, "Autopilot process / hardware",
            ha="center", fontsize=8.5, color=GREY, style="italic")

    # Dashboard (browser)
    _box(ax, 0.3, 2.9, 2.3, 1.7,
         "Dashboard\n(React 18 + Vite +\nLeaflet over OSM tiles)",
         fill="#EAF1FB", edge=NAVY, fs=10)

    # trigger_api (central)
    _box(ax, 4.0, 2.9, 3.0, 1.7,
         "trigger_api\n(FastAPI + uvicorn)\nPOST /trigger\nWS /ws/telemetry\nGET /mission/{id}",
         fill="#FFF6D9", edge=AMBER, fs=9.5)

    # Flight core (below trigger_api)
    _box(ax, 4.0, 0.5, 3.0, 1.6,
         "flight_core\nmission_executor\nmavlink_interface\nfailsafe_handler",
         fill="#FBF1D6", edge=AMBER, fs=9.5)

    # Vehicle (right)
    _box(ax, 8.5, 2.9, 2.3, 1.7,
         "ArduPilot\nSITL  or  Pixhawk\n(MAVLink endpoint)",
         fill="#E8F6EC", edge=LEAF, fs=10)

    # Arrows — Dashboard <-> trigger_api
    _arrow(ax, 2.6, 4.0, 4.0, 4.0, label="HTTP", label_pos=0.5)
    _arrow(ax, 4.0, 3.5, 2.6, 3.5, label="WebSocket /ws/telemetry", label_pos=0.5)

    # Arrows — trigger_api <-> autopilot
    _arrow(ax, 7.0, 4.0, 8.5, 4.0, label="MAVLink (TCP/UART)", label_pos=0.5)
    _arrow(ax, 8.5, 3.5, 7.0, 3.5, label="HEARTBEAT, GPS, BATTERY", label_pos=0.5)

    # Arrow — trigger_api <-> flight_core (vertical, in-process)
    _arrow(ax, 5.5, 2.9, 5.5, 2.1)
    _arrow(ax, 5.5, 2.1, 5.5, 2.9)
    ax.text(6.0, 2.5, "in-process\nthread-safe snapshot", ha="left", va="center",
            fontsize=8, color=NAVY, style="italic")

    # Caption underneath
    ax.text(5.5, 0.0,
            "All inter-process communication uses standard protocols. The dashboard never speaks MAVLink;\n"
            "the flight core never serves HTTP. The trigger API is the only component that holds both ends.",
            ha="center", fontsize=8.5, color=GREY, style="italic")

    path = os.path.join(FIGDIR, "architecture.png")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# ----------------------------------------------------------------------------
# Figure 2 — Mission state machine
# ----------------------------------------------------------------------------

def fig_state_machine() -> str:
    # Two rows of states + a terminal row to fit on the page cleanly
    fig, ax = plt.subplots(figsize=(11.4, 6.4), dpi=180)
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 8)
    ax.axis("off")

    ax.text(6, 7.6, "Figure 2. Mission state machine",
            ha="center", fontsize=12, color=DARK_NAVY, fontweight="bold")

    # Row 1 (top): pre-flight states
    row1 = [
        ("IDLE",        0.3,  6.0, "#EAF1FB", NAVY),
        ("CONNECTING",  2.4,  6.0, "#EAF1FB", NAVY),
        ("WAITING_GPS", 4.7,  6.0, "#EAF1FB", NAVY),
        ("ARMING",      7.4,  6.0, "#FFF6D9", AMBER),
        ("TAKEOFF",     9.6,  6.0, "#FFF6D9", AMBER),
    ]
    # Row 2 (middle): flight + return states
    row2 = [
        ("ENROUTE",     0.3,  4.0, "#E8F6EC", LEAF),
        ("HOVERING",    2.4,  4.0, "#E8F6EC", LEAF),
        ("RTL",         4.7,  4.0, "#E8F6EC", LEAF),
        ("LANDED",      7.4,  4.0, "#E8F6EC", LEAF),
        ("COMPLETED",   9.6,  4.0, "#D7EFDD", LEAF),
    ]
    box_w = 1.9
    box_h = 0.75

    for name, x, y, fill, edge in row1 + row2:
        _box(ax, x, y, box_w, box_h, name, fill=fill, edge=edge, fs=9.5, bold=True)

    # Arrows row 1 (left to right)
    for i in range(len(row1) - 1):
        x1 = row1[i][1] + box_w
        x2 = row1[i + 1][1]
        y  = row1[i][2] + box_h / 2
        _arrow(ax, x1, y, x2, y, color=NAVY, lw=1.5)

    # Wrap-around arrow: TAKEOFF (row 1, far right) -> ENROUTE (row 2, far left)
    arr = ConnectionPatch((row1[-1][1] + box_w / 2, row1[-1][2]),
                          (row2[0][1] + box_w / 2, row2[0][2] + box_h),
                          coordsA="data", coordsB="data",
                          axesA=ax, axesB=ax,
                          arrowstyle="->", mutation_scale=14, color=NAVY,
                          linewidth=1.5,
                          connectionstyle="arc3,rad=-0.25")
    ax.add_patch(arr)

    # Arrows row 2 (left to right)
    for i in range(len(row2) - 1):
        x1 = row2[i][1] + box_w
        x2 = row2[i + 1][1]
        y  = row2[i][2] + box_h / 2
        _arrow(ax, x1, y, x2, y, color=NAVY, lw=1.5)

    # Terminal failure states (bottom row, red)
    _box(ax, 0.3, 1.7, 1.9, 0.75, "ABORTED", fill="#FDECEC", edge=RUST, fs=9.5, bold=True)
    _box(ax, 2.4, 1.7, 1.9, 0.75, "FAILED",  fill="#FDECEC", edge=RUST, fs=9.5, bold=True)

    # Dashed red: failsafe -> ABORTED from any phase
    failsafe_sources = [(row1[3][1] + box_w / 2, row1[3][2]),  # ARMING
                        (row1[4][1] + box_w / 2, row1[4][2]),  # TAKEOFF
                        (row2[0][1] + box_w / 2, row2[0][2]),  # ENROUTE
                        (row2[1][1] + box_w / 2, row2[1][2]),  # HOVERING
                        (row2[2][1] + box_w / 2, row2[2][2])]  # RTL
    for sx, sy in failsafe_sources:
        arr = ConnectionPatch((sx, sy), (1.25, 1.7 + 0.75),
                              coordsA="data", coordsB="data",
                              axesA=ax, axesB=ax,
                              arrowstyle="->", mutation_scale=10,
                              color=RUST, linewidth=0.9, linestyle="--", alpha=0.55)
        ax.add_patch(arr)

    # Dash-dot: exception -> FAILED
    arr = ConnectionPatch((row2[2][1] + box_w / 2, row2[2][2]), (3.35, 1.7 + 0.75),
                          coordsA="data", coordsB="data",
                          axesA=ax, axesB=ax,
                          arrowstyle="->", mutation_scale=10,
                          color=RUST, linewidth=0.9, linestyle="-.", alpha=0.7)
    ax.add_patch(arr)

    # Legend
    ax.text(0.3, 0.95, "— Solid:    nominal transition",      fontsize=9, color=NAVY)
    ax.text(0.3, 0.55, "-- Dashed:  failsafe abort",          fontsize=9, color=RUST)
    ax.text(0.3, 0.15, "-·- Dash-dot: uncaught exception",     fontsize=9, color=RUST)

    ax.text(11.9, 0.45,
            "Every transition is logged with\na wall-clock timestamp; no phase\never waits for human input.",
            ha="right", fontsize=8.5, color=GREY, style="italic")

    path = os.path.join(FIGDIR, "state_machine.png")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# ----------------------------------------------------------------------------
# Figure 3 — Sequence diagram (a successful mission)
# ----------------------------------------------------------------------------

def fig_sequence() -> str:
    fig, ax = plt.subplots(figsize=(9.8, 7.2), dpi=180)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12)
    ax.axis("off")

    ax.text(5, 11.6, "Figure 3. Sequence diagram of one successful mission",
            ha="center", fontsize=11, color=DARK_NAVY, fontweight="bold")

    # Lanes
    lanes = [("Operator",        1.0, NAVY),
             ("trigger_api",     3.2, AMBER),
             ("mission_queue",   5.2, AMBER),
             ("mission_executor",7.2, AMBER),
             ("autopilot",       9.2, LEAF)]
    for name, x, color in lanes:
        _box(ax, x - 0.85, 10.6, 1.7, 0.55, name, fill="#FFFFFF", edge=color, fs=9.0, bold=True)
        ax.plot([x, x], [0.4, 10.6], linestyle=":", color=GREY, linewidth=0.9)

    # Sequence rows (y from top to bottom, with labels and arrows)
    rows = [
        # (y, source_idx, target_idx, label)
        (10.0, 0, 1, "POST /trigger {lat,lon,priority}"),
        ( 9.5, 1, 2, "enqueue(spec)"),
        ( 9.0, 2, 3, "pop highest-priority"),
        ( 8.5, 3, 4, "connect (MAVLink)"),
        ( 8.0, 4, 3, "HEARTBEAT, ready"),
        ( 7.5, 3, 4, "param ARMING_CHECK=0 (SITL only)"),
        ( 7.0, 3, 4, "SET_MODE GUIDED (DroneKit)"),
        ( 6.5, 3, 4, "COMMAND_LONG DO_SET_MODE (raw fallback)"),
        ( 6.0, 4, 3, "HEARTBEAT mode=GUIDED"),
        ( 5.5, 3, 4, "arm"),
        ( 5.0, 4, 3, "armed=true"),
        ( 4.5, 3, 4, "MAV_CMD_NAV_TAKEOFF(15m)"),
        ( 4.0, 4, 3, "altitude updates  ...  alt=15m"),
        ( 3.5, 3, 4, "simple_goto(target)"),
        ( 3.0, 4, 3, "GLOBAL_POSITION_INT  ...  d_target=0.4m"),
        ( 2.5, 3, 4, "SET_MODE RTL"),
        ( 2.0, 4, 3, "altitude updates  ...  alt=0m, armed=false"),
        ( 1.5, 3, 2, "status=done, final_state=COMPLETED"),
        ( 1.0, 0, 1, "GET /telemetry  (anytime)"),
    ]
    xs = [l[1] for l in lanes]
    for y, src, tgt, label in rows:
        x1 = xs[src]
        x2 = xs[tgt]
        color = NAVY if src < 4 and tgt < 4 else LEAF
        _arrow(ax, x1, y, x2, y, color=color, lw=1.1)
        # Label centered between
        midx = (x1 + x2) / 2
        ax.text(midx, y + 0.07, label, ha="center", va="bottom", fontsize=7.8, color=INK)

    ax.text(5, 0.05,
            "Vertical lines are component lifelines; horizontal arrows are MAVLink or HTTP/WebSocket messages.",
            ha="center", fontsize=8.5, color=GREY, style="italic")

    path = os.path.join(FIGDIR, "sequence.png")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# ----------------------------------------------------------------------------
# Figure 4 — Flight trajectory (synthesized from Run 5 telemetry)
# ----------------------------------------------------------------------------

def fig_trajectory() -> str:
    """Top-down view of one successful run.

    Coordinates approximate Run 5 — they are reconstructed from the d_target
    and d_home distances reported by the test harness. We do not claim
    sub-metre fidelity here; the figure is illustrative.
    """
    home = (28.6139, 77.2090)
    target = (28.6200, 77.2150)
    # Straight line outbound (sample every ~50m), then inbound on same line.
    n = 30
    outbound = [(home[0] + (target[0] - home[0]) * i / n,
                 home[1] + (target[1] - home[1]) * i / n) for i in range(n + 1)]
    hover = [target] * 3
    inbound = [(target[0] + (home[0] - target[0]) * i / n,
                target[1] + (home[1] - target[1]) * i / n) for i in range(n + 1)]
    path = outbound + hover + inbound

    fig, ax = plt.subplots(figsize=(8.4, 7.0), dpi=180)
    ax.set_facecolor("#F4F7FA")
    lats = [p[0] for p in path]
    lons = [p[1] for p in path]
    # Plot outbound + inbound separately so we can colour them
    ax.plot([p[1] for p in outbound], [p[0] for p in outbound],
            color=ACCENT, linewidth=2.4, label="Outbound (ENROUTE)")
    ax.plot([p[1] for p in inbound], [p[0] for p in inbound],
            color=LEAF, linewidth=2.4, linestyle="--", label="Return (RTL)")
    # Markers
    ax.plot(home[1], home[0], marker="o", color=LEAF, markersize=14, markeredgecolor=DARK_NAVY)
    ax.text(home[1], home[0] - 0.0005, "Home\n(28.6139, 77.2090)", ha="center", va="top", fontsize=9, color=DARK_NAVY)
    ax.plot(target[1], target[0], marker="*", color=AMBER, markersize=16, markeredgecolor=DARK_NAVY)
    ax.text(target[1], target[0] + 0.0004, "Target\n(28.6200, 77.2150)", ha="center", va="bottom", fontsize=9, color=DARK_NAVY)
    # Hover annotation
    ax.annotate("HOVERING 5s\nclosest approach 0.4 m",
                xy=(target[1], target[0]),
                xytext=(target[1] - 0.003, target[0] + 0.0015),
                fontsize=9, color=AMBER, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=AMBER, lw=1.0))

    # Distance / scale bar
    ax.text(0.5 * (home[1] + target[1]),
            0.5 * (home[0] + target[0]) - 0.0009,
            "896 m great-circle distance,\n15 m cruise altitude, ~8 m/s ground speed",
            ha="center", fontsize=9, color=NAVY, style="italic",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFFFFF", edgecolor=NAVY, lw=0.8))

    ax.set_xlabel("Longitude (°E)", fontsize=10)
    ax.set_ylabel("Latitude (°N)", fontsize=10)
    ax.set_title("Figure 4. Reconstructed flight trajectory (Run 5)",
                 fontsize=11, color=DARK_NAVY, fontweight="bold", pad=10)
    ax.grid(True, color="#E1E5EA", linestyle="-", linewidth=0.7)
    ax.legend(loc="lower right", fontsize=9, frameon=True)
    fig.tight_layout()
    path_out = os.path.join(FIGDIR, "flight_trajectory.png")
    fig.savefig(path_out, facecolor="white")
    plt.close(fig)
    return path_out


# ----------------------------------------------------------------------------
# Figure 5 — Failsafe decision tree
# ----------------------------------------------------------------------------

def fig_failsafe() -> str:
    fig, ax = plt.subplots(figsize=(11.0, 7.6), dpi=180)
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 9)
    ax.axis("off")

    ax.text(6, 8.6, "Figure 5. Failsafe monitor — trigger conditions and actions",
            ha="center", fontsize=12, color=DARK_NAVY, fontweight="bold")

    # Root
    _box(ax, 4.5, 7.2, 3.0, 0.8, "Failsafe monitor (1 Hz)",
         fill="#EAF1FB", edge=NAVY, bold=True, fs=11)

    # Conditions — stack vertically so labels never overlap
    conds = [
        # (label,                                        action,  edge)
        ("Battery <= CRIT_BATTERY_PCT (10% default)",    "LAND",  RUST),
        ("Battery <= LOW_BATTERY_PCT (20% default)",     "RTL",   AMBER),
        ("GPS fix_type < 2 (poor or no GPS lock)",       "LAND",  RUST),
        ("Distance from home > GEOFENCE_RADIUS",         "RTL",   AMBER),
        ("Mission wall-clock > MAX_MISSION_DURATION",    "RTL",   AMBER),
    ]
    y = 5.9
    dy = 0.85
    cond_centers = []
    for label, action, color in conds:
        _box(ax, 0.5, y, 6.5, 0.65, label, fill="#FFFFFF", edge=color, fs=10)
        cond_centers.append((7.0, y + 0.325, action, color))
        y -= dy

    # Connector from root down to first condition
    arr = ConnectionPatch((6.0, 7.2), (6.0, 6.55),
                          coordsA="data", coordsB="data",
                          axesA=ax, axesB=ax,
                          arrowstyle="-", color=NAVY, lw=1.0)
    ax.add_patch(arr)
    # Vertical spine connecting all conditions
    spine_top = 6.55
    spine_bot = cond_centers[-1][1] - 0.1
    arr = ConnectionPatch((6.0, spine_top), (6.0, spine_bot),
                          coordsA="data", coordsB="data",
                          axesA=ax, axesB=ax,
                          arrowstyle="-", color=NAVY, lw=0.8, alpha=0.5)
    ax.add_patch(arr)
    # Stub from spine into each condition box (right edge)
    for _, cy, _, _ in cond_centers:
        arr = ConnectionPatch((6.0, cy), (6.5 + 0.5, cy),
                              coordsA="data", coordsB="data",
                              axesA=ax, axesB=ax,
                              arrowstyle="-", color=NAVY, lw=0.8, alpha=0.6)
        ax.add_patch(arr)

    # Action boxes (right side)
    _box(ax,  8.5, 5.0, 2.6, 0.9, "LAND\n(immediate descent)",
         fill="#FDECEC", edge=RUST, bold=True, fs=10)
    _box(ax,  8.5, 3.4, 2.6, 0.9, "RTL\n(climb to RTL_ALT, fly home)",
         fill="#FFF6D9", edge=AMBER, bold=True, fs=10)

    # Map each condition to its action
    for x_cond, y_cond, action, color in cond_centers:
        if action == "LAND":
            tx, ty = 8.5, 5.45
        else:
            tx, ty = 8.5, 3.85
        arr = ConnectionPatch((x_cond, y_cond), (tx, ty),
                              coordsA="data", coordsB="data",
                              axesA=ax, axesB=ax,
                              arrowstyle="->", mutation_scale=10,
                              color=color, lw=1.0)
        ax.add_patch(arr)

    # Both actions feed into ABORTED state
    _box(ax, 8.5, 1.6, 2.6, 0.9, "ABORTED state\n(reason + timestamp logged)",
         fill="#EAF1FB", edge=NAVY, bold=True, fs=10)
    _arrow(ax,  9.8, 5.0,  9.8, 2.5, color=NAVY, lw=1.0)
    _arrow(ax,  9.8, 3.4,  9.8, 2.5, color=NAVY, lw=1.0)

    # Footer notes
    ax.text(6, 0.85,
            "All five conditions evaluated 1x per second on a daemon thread.\n"
            "At the next phase boundary the executor checks the triggered flag and aborts cleanly.",
            ha="center", fontsize=9, color=NAVY)
    ax.text(6, 0.05,
            "On real hardware these are supplemented by ArduPilot's own FS_THR_ENABLE / FS_GCS_ENABLE /\n"
            "FENCE_* parameters so a single-point software failure cannot strand the airframe.",
            ha="center", fontsize=8.5, color=GREY, style="italic")

    path = os.path.join(FIGDIR, "failsafe_tree.png")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# ----------------------------------------------------------------------------
# Figure 6 — Drone hardware architecture (airframe block diagram)
# ----------------------------------------------------------------------------

def fig_hardware() -> str:
    fig, ax = plt.subplots(figsize=(11.0, 6.8), dpi=180)
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 8)
    ax.axis("off")

    ax.text(6, 7.7, "Figure 6. Airframe hardware architecture",
            ha="center", fontsize=12, color=DARK_NAVY, fontweight="bold")

    # Power column (left)
    _box(ax, 0.3, 5.6, 2.2, 1.0, "LiPo battery\n3S 5200 mAh", fill="#FDECEC", edge=RUST, fs=9.5, bold=True)
    _box(ax, 0.3, 3.9, 2.2, 1.0, "Power module\n(V/I sense)", fill="#FDECEC", edge=RUST, fs=9.5)
    _box(ax, 0.3, 2.2, 2.2, 1.0, "PDB + 5 V BEC\n(frame plate)", fill="#FDECEC", edge=RUST, fs=9.5)
    _arrow(ax, 1.4, 5.6, 1.4, 4.9, color=RUST)
    _arrow(ax, 1.4, 3.9, 1.4, 3.2, color=RUST)

    # Flight controller (center)
    _box(ax, 4.4, 3.7, 3.2, 2.0,
         "Flight controller\nPixhawk (ArduPilot\nCopter 4.x)\nEKF · failsafes · motors",
         fill="#FFF6D9", edge=AMBER, fs=9.5, bold=True)
    _arrow(ax, 2.5, 4.4, 4.4, 4.4, color=RUST, label="power + V/I telemetry", label_pos=0.45)

    # Sensors (top center)
    _box(ax, 4.6, 6.3, 2.8, 0.9, "GPS + compass\n(u-blox M8N, mast-mounted)", fill="#E8F6EC", edge=LEAF, fs=9)
    _arrow(ax, 6.0, 6.3, 6.0, 5.7, color=LEAF, label="UART + I²C", label_pos=0.4)

    # RC (bottom center)
    _box(ax, 4.6, 1.6, 2.8, 0.9, "RC receiver (iBUS/PPM)\npilot override + kill switch", fill="#EAF1FB", edge=NAVY, fs=9)
    _arrow(ax, 6.0, 2.5, 6.0, 3.7, color=NAVY, label="RCIN", label_pos=0.45)

    # Companion computer (right)
    _box(ax, 8.9, 4.2, 2.8, 1.6,
         "Companion computer\nRaspberry Pi\nflight_core + trigger_api",
         fill="#EAF1FB", edge=NAVY, fs=9.5, bold=True)
    _arrow(ax, 7.6, 4.9, 8.9, 4.9, color=NAVY, label="TELEM2 UART\nMAVLink 921600", label_pos=0.5)
    _arrow(ax, 8.9, 4.6, 7.6, 4.6, color=NAVY)

    # Network cloud (right bottom)
    _box(ax, 8.9, 1.9, 2.8, 1.2, "Operator network\n(Wi-Fi / LTE)\ndashboard + REST + WS", fill=PAPER, edge=GREY, fs=9)
    _arrow(ax, 10.3, 4.2, 10.3, 3.1, color=GREY, label="HTTP / WebSocket", label_pos=0.5)

    # Motors/ESCs (far left bottom, fed by PDB)
    _box(ax, 0.3, 0.4, 2.2, 1.2, "4 × ESC 30 A\n→ 4 × 2212 920 kV\n+ 1045 props", fill="#FFF6D9", edge=AMBER, fs=9)
    _arrow(ax, 1.4, 2.2, 1.4, 1.6, color=RUST)
    _arrow(ax, 4.4, 4.0, 2.5, 1.3, color=AMBER, label="PWM MAIN OUT 1-4", label_pos=0.55)

    ax.text(6, 0.15,
            "Power (red), control (navy), sensing (green). The RC link is hardware-level pilot authority that no software state can block.",
            ha="center", fontsize=8.5, color=GREY, style="italic")

    path = os.path.join(FIGDIR, "hardware_architecture.png")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# ----------------------------------------------------------------------------
# Figure 7 — Safety interlock chain (dispatch pipeline guarantees)
# ----------------------------------------------------------------------------

def fig_interlock() -> str:
    fig, ax = plt.subplots(figsize=(11.4, 6.4), dpi=180)
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 8)
    ax.axis("off")

    ax.text(6, 7.7, "Figure 7. Safety interlock chain — from trigger to landing",
            ha="center", fontsize=12, color=DARK_NAVY, fontweight="bold")

    steps = [
        ("1. Edge validation", "coords bounded\nalt 2-120 m\ntarget inside geofence\nauth (X-API-Key)", 0.3),
        ("2. Queue admission", "depth cap\npriority ordering\nserial execution", 2.65),
        ("3. Pre-flight interlock", "refuse launch\nwhile vehicle armed\nGPS lock required", 5.0),
        ("4. In-flight guard", "1 Hz failsafe poll\ndebounced GPS\nleg-stall detector\noperator cancel", 7.35),
        ("5. Abort guarantee", "confirmed mode set\n(raw-MAVLink fallback)\nLAND ≻ RTL\nblock until disarm", 9.7),
    ]
    for title, body, x in steps:
        _box(ax, x, 4.6, 2.0, 1.0, title, fill="#EAF1FB", edge=NAVY, fs=9, bold=True)
        _box(ax, x, 2.6, 2.0, 1.7, body, fill=PAPER, edge=GREY, fs=8)
        _arrow(ax, x + 1.0, 4.6, x + 1.0, 4.3, color=GREY, lw=1.0)
    for i in range(len(steps) - 1):
        x1 = steps[i][2] + 2.0
        x2 = steps[i + 1][2]
        _arrow(ax, x1, 5.1, x2, 5.1, color=NAVY, lw=1.6)

    # Invariant banner
    _box(ax, 1.5, 0.8, 9.0, 0.9,
         "Invariant: the mission queue can never start a new flight against an airborne vehicle —\n"
         "aborts block until landing + disarm, and launches re-verify the disarmed state.",
         fill="#E8F6EC", edge=LEAF, fs=9, bold=True)
    _arrow(ax, 10.7, 2.6, 6.0, 1.7, color=LEAF, lw=1.2)
    _arrow(ax, 6.0, 2.6, 6.0, 1.7, color=LEAF, lw=1.2)

    path = os.path.join(FIGDIR, "safety_interlock.png")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# ----------------------------------------------------------------------------
# Figure 8 — Wiring diagram (bench reference)
# ----------------------------------------------------------------------------

def fig_wiring() -> str:
    fig, ax = plt.subplots(figsize=(11.0, 7.2), dpi=180)
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 9)
    ax.axis("off")

    ax.text(6, 8.7, "Figure 8. Wiring reference (F450-class build)",
            ha="center", fontsize=12, color=DARK_NAVY, fontweight="bold")

    # Central FC with labelled ports
    _box(ax, 4.5, 3.6, 3.0, 2.6, "", fill="#FFF6D9", edge=AMBER)
    ax.text(6.0, 5.85, "PIXHAWK", ha="center", fontsize=11, color=DARK_NAVY, fontweight="bold")
    ports = [
        ("POWER", 4.5, 5.3, "left"), ("TELEM2", 4.5, 4.7, "left"),
        ("RCIN", 4.5, 4.1, "left"),
        ("GPS", 7.5, 5.3, "right"), ("I2C", 7.5, 4.7, "right"),
        ("MAIN OUT 1-4", 7.5, 4.1, "right"), ("SWITCH/BUZZ", 6.0, 3.6, "bottom"),
    ]
    for name, px, py, side in ports:
        ha = {"left": "left", "right": "right", "bottom": "center"}[side]
        ox = {"left": 0.08, "right": -0.08, "bottom": 0}[side]
        oy = {"left": 0, "right": 0, "bottom": 0.12}[side]
        ax.text(px + ox, py + oy, name, ha=ha, va="center", fontsize=7.5, color=NAVY, fontweight="bold")

    # Left column: power module, RC RX, Pi
    _box(ax, 0.4, 5.0, 2.4, 0.9, "Power module\n(from battery XT60)", fill="#FDECEC", edge=RUST, fs=8.5)
    _arrow(ax, 2.8, 5.4, 4.5, 5.35, color=RUST, label="6-pin DF13", label_pos=0.5)

    _box(ax, 0.4, 3.3, 2.4, 0.9, "Raspberry Pi\nGPIO14 TX / GPIO15 RX / GND", fill="#EAF1FB", edge=NAVY, fs=8.5)
    _arrow(ax, 2.8, 3.9, 4.5, 4.7, color=NAVY, label="TX→RX  RX→TX  GND→GND", label_pos=0.45)

    _box(ax, 0.4, 1.6, 2.4, 0.9, "FS-iA6B receiver\n(iBUS/PPM out)", fill="#EAF1FB", edge=NAVY, fs=8.5)
    _arrow(ax, 2.8, 2.1, 4.5, 4.05, color=NAVY, label="RCIN 3-wire", label_pos=0.4)

    # Right column: GPS, ESC fan-out
    _box(ax, 9.0, 5.0, 2.5, 0.9, "u-blox M8N\nGPS + compass (mast)", fill="#E8F6EC", edge=LEAF, fs=8.5)
    _arrow(ax, 9.0, 5.5, 7.5, 5.35, color=LEAF, label="GPS port", label_pos=0.5)
    _arrow(ax, 9.0, 5.2, 7.5, 4.75, color=LEAF, label="I²C (compass)", label_pos=0.55)

    _box(ax, 9.0, 2.6, 2.5, 1.8,
         "ESC 1  motor FR (CCW)\nESC 2  motor BL (CCW)\nESC 3  motor FL (CW)\nESC 4  motor BR (CW)",
         fill="#FFF6D9", edge=AMBER, fs=8.5)
    _arrow(ax, 9.0, 3.5, 7.5, 4.05, color=AMBER, label="signal leads → MAIN OUT", label_pos=0.5)

    # Bottom: battery + PDB chain
    _box(ax, 3.4, 0.6, 2.0, 0.9, "LiPo 3S\nXT60", fill="#FDECEC", edge=RUST, fs=8.5, bold=True)
    _box(ax, 6.4, 0.6, 2.2, 0.9, "PDB (frame plate)\nESC power pads + 5 V BEC", fill="#FDECEC", edge=RUST, fs=8.5)
    _arrow(ax, 5.4, 1.05, 6.4, 1.05, color=RUST, label="via power module", label_pos=0.5)
    _arrow(ax, 8.6, 1.05, 10.2, 2.6, color=RUST, label="ESC power", label_pos=0.5)
    _arrow(ax, 6.4, 1.0, 1.6, 3.3, color=RUST, label="5 V BEC → Pi", label_pos=0.35)

    ax.text(6, 0.1,
            "Quad-X motor order/rotation per ArduPilot convention. Props stay OFF until the props-off arming test passes.",
            ha="center", fontsize=8.5, color=GREY, style="italic")

    path = os.path.join(FIGDIR, "wiring.png")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def build_all():
    paths = [fig_architecture(), fig_state_machine(), fig_sequence(),
             fig_trajectory(), fig_failsafe(), fig_hardware(),
             fig_interlock(), fig_wiring()]
    for p in paths:
        print(f"wrote: {p}")


if __name__ == "__main__":
    build_all()
