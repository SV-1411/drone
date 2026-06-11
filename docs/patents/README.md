# Patent Drafts — Landscape, Strategy, and Filing Checklist

Two draft complete specifications, structured per Indian Patent Office
Form 2 (Patents Act 1970, Patents Rules 2003):

| Draft | Title (short) | Claimed core |
|---|---|---|
| [PATENT_1_VERIFIED_DISPATCH.md](PATENT_1_VERIFIED_DISPATCH.md) | Verified flight-mode command delivery + landing-interlocked dispatch | Telemetry-confirmed mode transitions with layered MAVLink re-encoding and RTL⇄LAND cross-fallback; queue invariant that no mission starts against an airborne vehicle |
| [PATENT_2_FAILSAFE_ARBITER.md](PATENT_2_FAILSAFE_ARBITER.md) | Debounced, severity-ordered failsafe arbitration | Monotone LAND ≻ RTL demand, N-sample GPS debounce, mid-RTL escalation, fire-once incident record |

## Prior-art landscape (disclosed in both drafts)

The *trigger → fly to GPS coordinate* concept is heavily patented and is
**not** claimed:

- US 10,216,181 B2 — rescue UAV launched by sensor trigger to a recorded
  GPS location
- US 10,089,889 B2 — UAV dispatch from emergency-call events, self-guided
  to scene
- US 12,184,803 B2 — UAV emergency dispatch + diagnostics
- US 9,573,684 B2 / US 10,737,782 B2 / US 2016/0033966 A1 — delivery
  dispatch families
- ArduPilot / PX4 documentation — firmware-level battery/geofence/GCS
  failsafes (non-patent prior art)

The drafts claim the layers *above* that concept: command-delivery
verification and arbitration semantics in the companion computer.

## Filing checklist (do these before anything else)

1. **Novelty search** on the claims via IPO InPASS
   (<https://iprsearch.ipindia.gov.in>), WIPO PATENTSCOPE, and Google
   Patents. The drafts disclose known art honestly, but only a fresh
   search against the *claims* establishes filing-worthiness.
2. **Engage a registered patent agent** (mandatory in practice; they
   will re-scope claims, prepare Rule-15-compliant drawings from
   `docs/figures/`, and file Forms 1/2/3/5 + 18).
3. Decide **provisional first** (cheap priority date, 12 months to
   complete) vs **direct complete** filing. Given the working
   implementation exists, direct complete is viable.
4. **Do not publicly disclose new claim material before filing.** Note:
   this repository is public — the code and papers already published
   constitute self-disclosure. In India a 12-month grace period under
   Section 31 is narrow; the patent agent must assess the impact of the
   repository's publication dates on novelty. **Filing soon matters
   more than polishing.**
5. Startup/individual applicants qualify for reduced IPO fees and
   expedited examination (Form 18A).

> These drafts are technical-authorship work products, not legal advice.
