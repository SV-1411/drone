# Phone Test Mode (no hardware needed)

Test the whole VanniKawachh pipeline with just phones and this computer. No
ESP32, no LoRa, no drone. This proves the detection-to-response chain works on
real audio before you build hardware.

The computer runs the hub (it stands in for the Raspberry Pi and runs the
Stage-1 and Stage-2 models). The phones open web pages in their browser:

* `/node`        one phone is the pole microphone (sensing node)
* `/drone-phone` another phone is the drone (reports its GPS as it moves)
* `/`            the police dashboard (open on any screen)

What this tests: audio capture, Stage-1 detection, Stage-2 verification, fusion,
the dispatch decision, and the response shown live on the dashboard.
What it does NOT test: LoRa radio range, the ESP32 itself, the real microphone
hardware, or physical flight. Those stay the hardware phases
(`docs/HARDWARE_PHASES.md`). In the paper, call this a software-in-the-loop test
with real phone audio.

---

## 1. Start the hub on this computer

```
cd D:\drone-safety-system
.venv\Scripts\python.exe -m hub.main --web-only
```

For phone GPS and live microphone you need HTTPS (browsers block them on plain
http from a LAN address). Add `--https` (it makes a self-signed cert with
openssl):

```
.venv\Scripts\python.exe -m hub.main --web-only --https
```

The hub prints the URLs. Find this PC's WiFi IP with `ipconfig` (the IPv4
address, e.g. 192.168.1.42). All phones must be on the same WiFi.

## 2. Open the pages on your phones

Replace `<PC-IP>` with the address from step 1, and use `https://` if you
started with `--https`. On the first HTTPS visit each phone will warn about the
self-signed certificate: tap Advanced, then Proceed. That is expected.

| Device | Open this URL | Role |
|---|---|---|
| Phone A | `http(s)://<PC-IP>:8990/node` | sensing node (microphone) |
| Phone B | `http(s)://<PC-IP>:8990/drone-phone` | drone unit |
| Any screen | `http(s)://<PC-IP>:8990/` | police dashboard |

## 3. Run a test

**Single phone (auto drone).** On Phone A tap **SIMULATE DISTRESS**. It sends a
scream clip to the hub. The hub detects it, verifies it, and dispatches. On the
dashboard you see the alert, and an animated drone flies from its base to the
spot, hovers, drops the kit, and returns. No second phone needed.

**Real audio.** On Phone A (needs `--https`) tap **Start live mic** and shout
"help" or "bachao". The hub runs the model and the loudness gate on your real
audio and triggers the same response.

**Two phones (Phone B is the drone).** After Phone A triggers an alert, Phone B
(the `/drone-phone` page) shows the incident location and the distance to it.
Now either:
* Tap **Follow my GPS** (needs `--https`) and physically walk toward the spot.
  Your real movement shows on the dashboard as the drone moving.
* Or tap **STEP toward incident** a few times to advance without walking.
Tap **DROP FIRST-AID KIT** when you arrive, then **RETURN TO BASE**. Everything
Phone B does appears on the dashboard in real time. When a drone phone is
reporting, the dashboard shows it instead of the auto animation.

## 4. What you should see on the dashboard

* A red incident marker at the alert location, with an alarm sound.
* The alert in the list on the left (event, severity, priority, mission id).
* The drone marker moving (auto animation, or Phone B's real GPS).
* A "first-aid kit dropped" marker when the kit is released.

## Tuning

* Default incident location (when a phone cannot share GPS): `test_lat` /
  `test_lon` in `hub/config.py` (set to your area).
* Detection/dispatch thresholds: `verify_threshold` (0.50) and
  `dispatch_threshold` (0.60) in `hub/config.py`.
* The hub uses the trained Stage-1 model (`ml/out/stage1_nn.npz`) if present,
  plus a loudness gate so a genuine shout always triggers. Retrain on real audio
  (`docs/HARDWARE_PHASES.md`, Phase 1) for real accuracy.

## Troubleshooting

* Phone cannot reach the page: same WiFi? Windows Firewall may block port 8990;
  allow Python through the firewall, or run once as admin.
* Mic or GPS button does nothing: you are on http. Restart the hub with
  `--https` and accept the certificate warning on the phone.
* "openssl" not found for `--https`: install openssl, or use SIMULATE DISTRESS
  and the STEP button, which both work on plain http.
