"""Generate HARDWARE_COSTING.pdf — a student-focused hardware costing and
buyer's guide for the Drone Safety System.

Self-contained: builds the PDF directly with fpdf2 (no markdown/docx step) so
table layout and the rupee glyph are fully under control. Uses Windows Arial
TTFs for Unicode (the rupee sign is not representable in the core latin-1 fonts).

Usage (from project root):
    python docs/build_costing_pdf.py
Outputs: docs/HARDWARE_COSTING.pdf
"""
from __future__ import annotations

import os

from fpdf import FPDF

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "HARDWARE_COSTING.pdf")

# Palette (matches the docx pipeline's navy theme)
NAVY = (31, 58, 95)
DARK_NAVY = (13, 31, 61)
INK = (16, 16, 16)
GREY = (85, 91, 99)
LIGHT = (238, 241, 245)
ZEBRA = (247, 249, 251)
ACCENT = (5, 99, 193)
GOOD = (22, 120, 64)

RUPEE = "₹"


class PDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Arial", "I", 8)
        self.set_text_color(*GREY)
        self.cell(0, 8, "Drone Safety System  -  Hardware Costing & Buyer's Guide", align="L")
        self.set_y(10)
        self.set_draw_color(*LIGHT)
        self.line(self.l_margin, 16, self.w - self.r_margin, 16)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-13)
        self.set_font("Arial", "", 8)
        self.set_text_color(*GREY)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")


def rs(n):
    """Format a rupee amount with thousands separators."""
    return f"{RUPEE}{n:,}"


def setup_fonts(pdf: PDF):
    fdir = r"C:\Windows\Fonts"
    pdf.add_font("Arial", "", os.path.join(fdir, "arial.ttf"))
    pdf.add_font("Arial", "B", os.path.join(fdir, "arialbd.ttf"))
    pdf.add_font("Arial", "I", os.path.join(fdir, "ariali.ttf"))
    pdf.add_font("Arial", "BI", os.path.join(fdir, "arialbi.ttf"))


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def h1(pdf: PDF, text: str):
    pdf.ln(2)
    if pdf.get_y() > pdf.h - 45:
        pdf.add_page()
    pdf.set_font("Arial", "B", 15)
    pdf.set_text_color(*DARK_NAVY)
    pdf.multi_cell(0, 8, text)
    pdf.set_draw_color(*NAVY)
    pdf.set_line_width(0.5)
    y = pdf.get_y() + 1
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(3)


def h2(pdf: PDF, text: str):
    pdf.ln(1)
    if pdf.get_y() > pdf.h - 40:
        pdf.add_page()
    pdf.set_font("Arial", "B", 12)
    pdf.set_text_color(*NAVY)
    pdf.multi_cell(0, 7, text)
    pdf.ln(1)


def para(pdf: PDF, text: str, size=10.5, color=INK, gap=2.2):
    pdf.set_font("Arial", "", size)
    pdf.set_text_color(*color)
    pdf.multi_cell(0, 5.2, text)
    pdf.ln(gap)


def bullet(pdf: PDF, text: str, size=10.5):
    pdf.set_font("Arial", "", size)
    pdf.set_text_color(*INK)
    x = pdf.get_x()
    pdf.set_x(x + 4)
    pdf.set_font("Arial", "B", size)
    pdf.cell(4, 5.0, "•")
    pdf.set_font("Arial", "", size)
    pdf.multi_cell(0, 5.0, text)
    pdf.set_x(x)
    pdf.ln(0.6)


def table(pdf: PDF, headers, rows, widths, aligns=None, font_size=8.8,
          header_fill=NAVY, note_rows=None):
    """Render a bordered, zebra-striped, page-break-aware table.

    note_rows: set of row indices to render in italic across all columns
               (used for 'subtotal' / category rows).
    """
    note_rows = note_rows or set()
    aligns = aligns or ["L"] * len(headers)
    total_w = sum(widths)
    avail = pdf.w - pdf.l_margin - pdf.r_margin
    x0 = pdf.l_margin + max(0, (avail - total_w) / 2)
    line_h = 4.6

    def draw_header():
        pdf.set_x(x0)
        pdf.set_font("Arial", "B", font_size)
        pdf.set_fill_color(*header_fill)
        pdf.set_text_color(255, 255, 255)
        pdf.set_draw_color(*header_fill)
        for txt, w, al in zip(headers, widths, aligns):
            pdf.cell(w, 7, " " + txt, border=1, align=al, fill=True)
        pdf.ln(7)

    draw_header()
    pdf.set_draw_color(170, 180, 195)
    zebra = False
    for ridx, row in enumerate(rows):
        is_note = ridx in note_rows
        style = "I" if is_note else ""
        pdf.set_font("Arial", "B" if is_note else "", font_size)
        # measure wrapped height
        heights = []
        for txt, w in zip(row, widths):
            pdf.set_font("Arial", "B" if is_note else style or "", font_size)
            n = len(pdf.multi_cell(w - 2, line_h, str(txt), dry_run=True,
                                   output="LINES", align="L"))
            heights.append(max(1, n))
        rh = max(heights) * line_h + 2.4
        if pdf.get_y() + rh > pdf.h - 16:
            pdf.add_page()
            draw_header()
            zebra = False
        y_start = pdf.get_y()
        pdf.set_x(x0)
        if is_note:
            pdf.set_fill_color(*LIGHT)
            fill = True
        elif zebra:
            pdf.set_fill_color(*ZEBRA)
            fill = True
        else:
            pdf.set_fill_color(255, 255, 255)
            fill = True
        pdf.set_text_color(*INK)
        x = x0
        for txt, w, al in zip(row, widths, aligns):
            pdf.set_xy(x, y_start)
            pdf.set_font("Arial", ("BI" if is_note else "I") if (is_note) else "", font_size)
            if is_note:
                pdf.set_font("Arial", "B", font_size)
            else:
                pdf.set_font("Arial", "", font_size)
            pdf.rect(x, y_start, w, rh, style="DF" if fill else "D")
            pdf.set_xy(x + 1, y_start + 1.2)
            pdf.multi_cell(w - 2, line_h, str(txt), align=al)
            x += w
        pdf.set_y(y_start + rh)
        zebra = not zebra
    pdf.ln(3)


def callout(pdf: PDF, title: str, text: str, color=ACCENT):
    if pdf.get_y() > pdf.h - 40:
        pdf.add_page()
    pdf.set_draw_color(*color)
    pdf.set_fill_color(*ZEBRA)
    x0, y0 = pdf.l_margin, pdf.get_y()
    w = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_font("Arial", "B", 10)
    # measure
    pdf.set_xy(x0 + 4, y0 + 2)
    body_lines = pdf.multi_cell(w - 8, 4.8, text, dry_run=True, output="LINES")
    h = 8 + len(body_lines) * 4.8 + 3
    pdf.set_fill_color(*ZEBRA)
    pdf.rect(x0, y0, w, h, style="DF")
    pdf.set_fill_color(*color)
    pdf.rect(x0, y0, 1.6, h, style="F")
    pdf.set_xy(x0 + 5, y0 + 2.2)
    pdf.set_text_color(*color)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 5, title)
    pdf.set_xy(x0 + 5, y0 + 7.6)
    pdf.set_text_color(*INK)
    pdf.set_font("Arial", "", 9.6)
    pdf.multi_cell(w - 9, 4.8, text)
    pdf.set_y(y0 + h + 3)


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------

def build():
    pdf = PDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(18, 18, 18)
    setup_fonts(pdf)

    # ---- Cover ----
    pdf.add_page()
    pdf.ln(34)
    pdf.set_font("Arial", "B", 26)
    pdf.set_text_color(*DARK_NAVY)
    pdf.multi_cell(0, 12, "Drone Safety System", align="C")
    pdf.ln(2)
    pdf.set_font("Arial", "B", 17)
    pdf.set_text_color(*NAVY)
    pdf.multi_cell(0, 9, "Hardware Costing &\nStudent Buyer's Guide", align="C")
    pdf.ln(6)
    pdf.set_draw_color(*NAVY)
    pdf.set_line_width(0.6)
    pdf.line(60, pdf.get_y(), pdf.w - 60, pdf.get_y())
    pdf.ln(8)
    pdf.set_font("Arial", "I", 12)
    pdf.set_text_color(*GREY)
    pdf.multi_cell(0, 6,
        "Full bill of materials, component-by-component comparisons,\n"
        "and budget builds for a trigger-driven autonomous UAV.", align="C")
    pdf.ln(14)

    # Tier summary box on the cover
    pdf.set_font("Arial", "B", 11)
    pdf.set_text_color(*DARK_NAVY)
    pdf.multi_cell(0, 6, "Four ways to build it:", align="C")
    pdf.ln(2)
    summary = [
        ("Simulation only", f"{RUPEE}0", "Full software on any PC - all dev happens here"),
        ("Student / rock-bottom", f"~{RUPEE}23,800", "Cheapest real quad that flies the stack safely"),
        ("Minimum airframe", f"~{RUPEE}28,400", "Proven workhorse build (Pixhawk 2.4.8)"),
        ("Recommended", f"~{RUPEE}51,600", "Current-gen autopilot + telemetry + 2nd battery"),
    ]
    table(pdf,
          ["Tier", "Cost", "What it gets you"],
          summary,
          widths=[42, 28, 104],
          aligns=["L", "R", "L"],
          font_size=9.6)
    pdf.ln(2)
    pdf.set_font("Arial", "I", 8.5)
    pdf.set_text_color(*GREY)
    pdf.multi_cell(0, 4.4,
        "Prices verified June 2026 against robu.in / Robokits / IndiaMART / ElectroPi "
        "listings; they drift over time - treat every figure as plus/minus 15%. "
        f"All amounts in Indian Rupees ({RUPEE}, INR).", align="C")

    # ---- 1. How to read this guide ----
    pdf.add_page()
    h1(pdf, "1.  Start here: spend nothing first")
    para(pdf,
        "This project is a software-first system. The entire flight stack - auto-arm, "
        "take-off, fly-to-GPS, hover, return, land, plus every failsafe - runs in "
        "ArduPilot SITL (Software In The Loop) on any laptop for zero rupees. You can "
        "dispatch, divert, recall and failsafe-abort hundreds of simulated missions "
        "before a single screw is turned.")
    callout(pdf, "Honest advice for students",
        "Spend " + RUPEE + "0 first. Run the simulator until you can predict what the "
        "aircraft will do before it does it. The hardware below then behaves like a "
        "faster, windier, more expensive version of the simulator you already trust. "
        "Buy parts only when you have a real reason to fly.", color=GOOD)
    para(pdf,
        "When you are ready for real flight, the rest of this guide gives you (2) four "
        "complete budget builds, (3) a part-by-part comparison so you can mix and match "
        "by price, (4) where the money actually goes, and (5) student money-saving "
        "tactics and traps to avoid.")

    callout(pdf, "Safety & legality (India)",
        "Civil drone flight is governed by the Drone Rules, 2021. This class of build is "
        "Micro/Small category: register on DigitalSky for a UIN, fly only in green-zone "
        "airspace, and ALWAYS keep a trained pilot with an RC transmitter and kill switch "
        "in visual line of sight. Autonomous does not mean unsupervised.", color=(176, 96, 0))

    # ---- 2. The four builds ----
    pdf.add_page()
    h1(pdf, "2.  The four complete builds")

    h2(pdf, "2.1  Student / rock-bottom build  (~" + RUPEE + "23,800)")
    para(pdf,
        "The cheapest configuration that still flies this stack safely. It swaps the "
        "Pixhawk for a low-cost ArduPilot-capable flight controller and assumes you "
        "already own a laptop to act as the ground station (no dedicated companion "
        "computer yet - you tether over USB/telemetry for early flights).")
    rows = [
        ["1", "Frame", "F450-class glass-fibre quad + PDB", "1", "1,200"],
        ["2", "Flight controller", "SpeedyBee F405 V3 / Matek F405 (runs ArduPilot 4.x)", "1", "4,800"],
        ["3", "GPS + compass", "u-blox NEO-M8N with stand", "1", "2,000"],
        ["4", "Motors", "2212 920kV brushless", "4", "2,200"],
        ["5", "ESCs", "30A BLHeli, 3S", "4", "2,000"],
        ["6", "Propellers", "1045 self-locking + spares", "2 sets", "650"],
        ["7", "Battery", "3S 2200mAh 30C LiPo, XT60", "1", "1,200"],
        ["8", "Power / BEC", "Voltage+current sense module + 5V BEC", "1", "600"],
        ["9", "RC TX + RX", "FlySky FS-i6 + FS-iA6B (6ch)", "1", "4,200"],
        ["10", "Charger", "IMAX B6-class balance charger + supply", "1", "2,000"],
        ["11", "Telemetry (optional but advised)", "433/915MHz SiK radio pair", "1", "2,200"],
        ["12", "Consumables", "XT60, silicone wire, heat-shrink, zip ties, thread-lock", "-", "750"],
        ["", "Total", "", "", RUPEE + "~23,800"],
    ]
    table(pdf, ["#", "Item", "Spec / example", "Qty", "Price (" + RUPEE + ")"],
          rows, widths=[8, 34, 78, 14, 30],
          aligns=["C", "L", "L", "C", "R"], note_rows={len(rows) - 1})
    bullet(pdf, "Trade-off: an F405 board has less RAM/flash and fewer redundant IMUs "
                "than a Pixhawk. It runs the same ArduPilot firmware and the same "
                "parameter set, so this codebase does not change - but you lose dual-IMU "
                "redundancy. Fine for line-of-sight student flights; step up before BVLOS.")
    bullet(pdf, "Smaller 2200mAh pack = ~6-8 min flight. Cheap and light for learning; "
                "buy a 5200mAh pack once you stop crashing.")
    bullet(pdf, "No companion computer: run the API on your laptop tethered to the FC. "
                "Add a Pi later (+" + RUPEE + "2,800) for on-board autonomy.")

    h2(pdf, "2.2  Minimum build  (~" + RUPEE + "28,400)")
    para(pdf, "The proven, recommended-for-most-people starting point from the project's "
              "Build & Operations Guide: a real Pixhawk and an on-board Raspberry Pi so "
              "the aircraft is autonomous without a tethered laptop.")
    rows = [
        ["1", "Frame", "F450-class glass-fibre quad + PDB", "1", "1,200"],
        ["2", "Flight controller", "Pixhawk 2.4.8 (FMUv2/v3) + buzzer + safety switch", "1", "6,500"],
        ["3", "GPS + compass", "u-blox NEO-M8N with stand", "1", "2,000"],
        ["4", "Motors", "2212 920kV brushless", "4", "2,400"],
        ["5", "ESCs", "30A BLHeli, 3S", "4", "2,200"],
        ["6", "Propellers", "1045 self-locking + spares", "2 sets", "700"],
        ["7", "Battery", "3S 5200mAh 35C LiPo, XT60", "1", "3,000"],
        ["8", "Power module", "Pixhawk power module (V+I sense, XT60)", "1", "500"],
        ["9", "RC TX + RX", "FlySky FS-i6 + FS-iA6B (6ch)", "1", "4,200"],
        ["10", "Companion computer", "Raspberry Pi Zero 2 W + 32GB card + UART cable", "1", "2,800"],
        ["11", "Charger", "IMAX B6-class balance charger + supply", "1", "2,000"],
        ["12", "Consumables", "XT60, silicone wire, heat-shrink, zip ties, thread-lock", "-", "900"],
        ["", "Total", "", "", RUPEE + "~28,400"],
    ]
    table(pdf, ["#", "Item", "Spec / example", "Qty", "Price (" + RUPEE + ")"],
          rows, widths=[8, 34, 78, 14, 30],
          aligns=["C", "L", "L", "C", "R"], note_rows={len(rows) - 1})

    h2(pdf, "2.3  Recommended build  (~" + RUPEE + "51,600)")
    para(pdf, "Everything in the Minimum build, with these upgrades for current-gen "
              "reliability and sustained testing throughput:")
    rows = [
        ["Pixhawk 6C / Cube Orange Lite (vs 2.4.8)", "Current-gen IMUs, better EKF, vibration isolation", "+10,500"],
        ["M9N / M10 GPS (vs M8N)", "Faster fix, better multipath rejection", "+2,000"],
        ["Raspberry Pi 4 (4GB) (vs Zero 2 W)", "Headroom for camera + on-board dashboard", "+3,000"],
        ["Second 5200mAh battery", "Continuous test cycles, double throughput", "+3,000"],
        ["433/915MHz SiK telemetry pair", "Live telemetry + params from the bench, no USB", "+3,500"],
        ["Spare props x4 sets + spare motor", "You WILL break props learning", "+1,200"],
        ["Subtotal of upgrades over Minimum", "", "+23,200"],
    ]
    table(pdf, ["Upgrade", "Why", "Delta (" + RUPEE + ")"],
          rows, widths=[66, 76, 22],
          aligns=["L", "L", "R"], note_rows={len(rows) - 1})

    # ---- 3. Part-by-part comparison ----
    pdf.add_page()
    h1(pdf, "3.  Part-by-part comparison (mix & match by price)")
    para(pdf, "Each subsystem below lists a Budget / Mid / Better option. Build your own "
              "tier by picking one row per subsystem. The 'Pick for students' note tells "
              "you the value choice.")

    def comp(title, headers, rows, widths, aligns, pick):
        h2(pdf, title)
        table(pdf, headers, rows, widths, aligns, font_size=8.6)
        pdf.set_font("Arial", "I", 9.2)
        pdf.set_text_color(*GOOD)
        pdf.multi_cell(0, 4.6, "Pick for students:  " + pick)
        pdf.ln(2.5)

    comp("3.1  Flight controller  (the single biggest cost lever)",
         ["Option", "Key specs", "Notes", "Price"],
         [
            ["SpeedyBee/Matek F405", "F405 MCU, 1 IMU, baro, 5 UART", "Runs ArduPilot 4.x; no IMU redundancy", "4,000-5,300"],
            ["Pixhawk 2.4.8 (clone)", "FMUv2/v3, dual IMU, 5 UART", "Budget workhorse; same params as costly boards", "5,000-7,000"],
            ["Pixhawk 6C", "STM32H7, triple IMU, vibration-iso", "Current-gen, far better EKF behaviour", "16,000-19,000"],
            ["Cube Orange Lite/Plus", "H7, isolated IMU, robust", "Pro-grade; overkill for first build", "24,000-32,000"],
         ],
         widths=[34, 52, 56, 22], aligns=["L", "L", "L", "R"],
         pick="The Pixhawk 2.4.8 has dropped to ~" + RUPEE + "6,500 - only ~" + RUPEE +
              "1,700 over the F405 - so take it for dual-IMU redundancy unless you "
              "need absolute rock-bottom, then the F405.")

    comp("3.2  GPS + compass module",
         ["Option", "Key specs", "Notes", "Price"],
         [
            ["NEO-6M", "~1Hz, older, no good compass", "AVOID for autonomy - slow, weak fix", "600-1,000"],
            ["NEO-M8N", "10Hz, GPS+GLONASS, HMC/IST compass", "The sweet spot; what the project uses", "1,100-2,200"],
            ["NEO-M9N / M10", "Multi-band, faster fix, better multipath", "Worth it in cluttered/urban sites", "3,800-4,800"],
         ],
         widths=[30, 56, 56, 22], aligns=["L", "L", "L", "R"],
         pick="NEO-M8N. The M9N is a real upgrade only near buildings; skip the M6N entirely.")

    comp("3.3  Frame",
         ["Option", "Key specs", "Notes", "Price"],
         [
            ["F450 clone (glass-fibre)", "450mm, integrated PDB", "Cheap, repairable, plenty of room", "900-1,400"],
            ["S500 (glass-fibre)", "500mm, more payload room", "Steadier, fits bigger props/battery", "1,600-2,400"],
            ["Carbon-fibre 450/500", "Stiffer, lighter, pricier", "Nice-to-have, not needed for this mission", "3,500-6,000"],
         ],
         widths=[34, 48, 58, 22], aligns=["L", "L", "L", "R"],
         pick="F450 glass-fibre. Cheapest, easiest to repair after the inevitable learning crash.")

    pdf.add_page()
    comp("3.4  Motors + ESCs (propulsion, buy as a matched set of 4)",
         ["Option", "Key specs", "Notes", "Price (set of 4)"],
         [
            ["2212 920kV + 30A ESC", "3S, 1045 props, ~800g thrust/motor", "Standard F450 combo; well documented", "4,000-5,000"],
            ["2213 935kV + 30A BLHeli-S", "Slightly more thrust, smoother", "Good if you add weight (Pi, telemetry)", "5,000-6,500"],
            ["4-in-1 ESC + 2306 motors", "Compact, clean wiring", "More for racing; not needed here", "6,500-9,000"],
         ],
         widths=[38, 48, 52, 24], aligns=["L", "L", "L", "R"],
         pick="2212 920kV + 30A ESC. Cheapest proven combo; spares are everywhere.")

    comp("3.5  Battery (3S LiPo) - your main recurring cost",
         ["Option", "Key specs", "Notes", "Price"],
         [
            ["3S 2200mAh 30C", "~6-8 min, light", "Great for learning; cheap to replace if puffed", "900-1,500"],
            ["3S 5200mAh 35C", "~10-12 min", "Project default; best flight-time value", "2,600-3,500"],
            ["3S 6000mAh 50C", "~13-15 min", "Heavier; diminishing returns on small quad", "4,500-6,000"],
         ],
         widths=[30, 40, 58, 24], aligns=["L", "L", "L", "R"],
         pick="Start with a cheap 2200mAh to learn on, then add a 5200mAh. Buying two "
              "small packs beats one big one for test throughput.")

    comp("3.6  RC transmitter + receiver (safety-critical: do not cheap out blindly)",
         ["Option", "Key specs", "Notes", "Price"],
         [
            ["FlySky FS-i6 + iA6B", "6ch, iBUS/PPM, 2.4GHz", "Reliable budget standard; kill switch ok", "4,000-5,000"],
            ["RadioMaster Pocket + RX", "ELRS, expandable, model memory", "Future-proof; long range", "5,500-8,000"],
            ["FrSky Taranis-class", "16ch, telemetry, premium feel", "More than this project needs", "12,000+"],
         ],
         widths=[34, 46, 54, 22], aligns=["L", "L", "L", "R"],
         pick="FlySky FS-i6. Cheap, dependable, and supports the mandatory pilot "
              "override + kill switch. Never run a build without a working RC override.")

    comp("3.7  Companion computer (runs flight_core + the API on-board)",
         ["Option", "Key specs", "Notes", "Price"],
         [
            ["None (laptop tether)", "Use your own laptop as GCS", "Free; fine for early line-of-sight flights", "0"],
            ["Raspberry Pi Zero 2 W", "Quad A53, 512MB", "Runs the stack; project default (board ~1,900)", "1,900-3,200"],
            ["Raspberry Pi 4 (2-4GB)", "Quad A72, 2-4GB", "Headroom for dashboard + camera later", "5,000-8,000"],
         ],
         widths=[34, 40, 56, 22], aligns=["L", "L", "L", "R"],
         pick="Skip it at first (tether your laptop), then a Pi Zero 2 W when you want "
              "the aircraft to be self-contained.")

    comp("3.8  Charger + accessories",
         ["Option", "Key specs", "Notes", "Price"],
         [
            ["IMAX B6 clone + 12V supply", "Balance, 1-6S, 50W", "Essential; never charge LiPo without balance", "1,500-2,200"],
            ["ISDT / HOTA dual charger", "Faster, safer, 2 packs", "Nice once you own several batteries", "4,500-7,000"],
            ["LiPo safe bag + checker", "Storage + cell-voltage alarm", "Cheap insurance against fire", "400-700"],
         ],
         widths=[36, 40, 54, 22], aligns=["L", "L", "L", "R"],
         pick="IMAX B6-class + a " + RUPEE + "150 cell checker + a LiPo safe bag. "
              "Non-negotiable safety basics.")

    # ---- 4. Where the money goes ----
    pdf.add_page()
    h1(pdf, "4.  Where the money actually goes")
    para(pdf, "On the Minimum build, three line items - the flight controller, the RC "
              "set, and the battery - are roughly half the cost. Those are exactly the "
              "items you should NOT cheap out on for safety, except the FC where a "
              "credible cheaper option (F405) exists.")
    rows = [
        ["Flight controller", "6,500", "23%"],
        ["RC transmitter + receiver", "4,200", "15%"],
        ["Battery", "3,000", "11%"],
        ["Companion computer", "2,800", "10%"],
        ["Motors", "2,400", "8%"],
        ["ESCs", "2,200", "8%"],
        ["Charger", "2,000", "7%"],
        ["GPS + compass", "2,000", "7%"],
        ["Frame", "1,200", "4%"],
        ["Consumables", "900", "3%"],
        ["Props", "700", "2%"],
        ["Power module", "500", "2%"],
        ["Total (Minimum build)", "28,400", "100%"],
    ]
    table(pdf, ["Item", "Cost (" + RUPEE + ")", "Share"],
          rows, widths=[80, 30, 26], aligns=["L", "R", "R"],
          note_rows={len(rows) - 1})

    callout(pdf, "What changed since the original guide",
        "Pixhawk 2.4.8 (" + RUPEE + "10,500 -> ~" + RUPEE + "6,500) and the NEO-M8N GPS "
        "(" + RUPEE + "2,500 -> ~" + RUPEE + "2,000) have fallen sharply, so the Minimum "
        "build dropped from ~" + RUPEE + "35,600 to ~" + RUPEE + "28,400. The Pixhawk is "
        "now so cheap that the F405 saves only ~" + RUPEE + "1,700 - the Student build's "
        "real savings now come from dropping the on-board Pi (tether a laptop, -" + RUPEE +
        "2,800) and starting on a small 2200mAh pack (-" + RUPEE + "1,800).")

    # ---- 5. Money-saving tips & traps ----
    h1(pdf, "5.  Student money-saving tactics")
    for t in [
        "Simulate first, buy later. Every rupee of hardware is optional until you have flown the SITL stack dozens of times.",
        "Share a kit. One FC + RC + charger can be a lab/club asset; students buy their own consumables (props, a battery).",
        "Buy the airframe and a cheap 2200mAh pack to learn on. Crash damage is cheaper when the parts are cheap.",
        "Reuse a laptop as the ground station - defer the Raspberry Pi until you actually need on-board autonomy.",
        "Buy props in bulk (you will break them) and motors as a matched set of 4 to keep thrust balanced.",
        "Watch for festival/clearance sales on robu.in, robokits, quartzcomponents; FC and RC prices swing the most.",
        "Skip what the mission does not use: no camera/gimbal, no lidar/optical-flow, no 4G link for the first build.",
    ]:
        bullet(pdf, t)
    pdf.ln(1)

    h2(pdf, "Traps to avoid")
    for t in [
        "NEO-6M GPS - too slow/weak for reliable autonomy. The few hundred rupees saved is not worth it.",
        "No-name ESCs without BLHeli - random behaviour during arming. Buy known brands.",
        "Charging LiPo without a balance charger or safe bag - a genuine fire risk, not a corner to cut.",
        "Cheapest possible RC - the transmitter is your pilot override and kill switch; keep it dependable.",
        "Setting ARMING_CHECK=0 on real hardware to 'make it arm' - never do this off the simulator.",
    ]:
        bullet(pdf, t)

    # ---- Footer note page ----
    pdf.ln(4)
    callout(pdf, "Bottom line for a student team",
        "Target the ~" + RUPEE + "23,800 Student build, or ~" + RUPEE + "27,000 if you "
        "add an on-board Pi and telemetry radio across the team. Spend " + RUPEE + "0 in "
        "simulation until you are confident, buy a cheap battery to learn on, and only "
        "upgrade the flight controller and battery once you have stopped crashing.",
        color=GOOD)
    pdf.ln(2)
    pdf.set_font("Arial", "I", 8)
    pdf.set_text_color(*GREY)
    pdf.multi_cell(0, 4,
        "Generated from the project's Build & Operations Guide; prices refreshed against "
        "robu.in / Robokits / IndiaMART / ElectroPi listings, June 2026, plus/minus 15% - "
        "verify before buying. Companion documents: BUILD_AND_OPERATIONS_GUIDE.md, "
        "HARDWARE_INTEGRATION.md.")

    pdf.output(OUT)
    return OUT


if __name__ == "__main__":
    print("wrote:", build())
