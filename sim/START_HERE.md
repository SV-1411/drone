# START HERE -- VanniKawachh hardware simulation

You have two ways to simulate the hardware. Pick based on what matters more:
**one-file auto-build**, or **real spinning DC motors**.

| | Wokwi (folder: `wokwi/`) | Tinkercad (folder: `tinkercad/`) |
|---|---|---|
| Builds from a file? | **YES -- paste one file, circuit appears wired** | No -- you drag parts by hand |
| Real DC motors? | No (rotors = servos + LEDs) | **YES -- 4 spinning DC motors** |
| Chip | ESP32 (your real chip) | Arduino Uno |
| Cost | Free | Free |
| Best when | you want it fast / auto-built | you want real motors on screen |

Both are honest, defensible demos. Neither flies the drone -- the actual flight
(BLDC + ESC + Pixhawk) is proven in **ArduPilot SITL** (`python -m hub.main`),
because no circuit simulator flies a quadcopter. Say that to reviewers.

---

## Option A -- Wokwi (AUTO-BUILDS from a file) -- recommended for speed

Two separate projects (Wokwi runs one board per project).

**Sensor node:**
1. Open https://wokwi.com -> New Project -> ESP32.
2. Click the `diagram.json` tab, delete what's there, and paste ALL of
   `wokwi/vannikawachh-node/diagram.json`. The circuit builds itself.
3. Paste `wokwi/vannikawachh-node/sketch.ino` into the code tab.
4. Press Play. Press the red SCREAM button (or turn the knob up) and watch the
   OLED + LEDs + serial alert packet.

**Drone:**
1. New Project -> ESP32 again.
2. Paste `wokwi/vannikawachh-drone/diagram.json` (auto-builds), then
   `wokwi/vannikawachh-drone/sketch.ino`.
3. Press Play. Press the red ALERT button: 4 rotor servos whirl, camera LED on,
   the kit servo drops, then it returns to idle.

Press **Save** (free account) -> **Share** to get a link for your slides.

## Option B -- Tinkercad (MANUAL build, but REAL DC motors)

Everything you need is in the **`tinkercad/`** folder:
* `tinkercad/README.md` -- parts list, wiring tables, step-by-step, demo script
* `tinkercad/node.ino` -- paste into the Sensor Node Uno
* `tinkercad/drone.ino` -- paste into the Drone Uno (4 DC motors + kit servo)
* `tinkercad/hub_optional.ino` -- optional 3rd board (the Pi hub, Stage-2)

You drag the parts onto the canvas, wire per the tables, paste the sketches.
There is no upload/import in Tinkercad -- that is a Tinkercad limitation.

## What about PCBX?

PCBX is an Arduino-style drag-and-drop simulator, so like Tinkercad it is a
**manual build, not a file upload** (these tools have no circuit-import format).
If your PCBX version DOES have an "import" option, tell me which file type it
accepts and I will generate that. Otherwise use the **Tinkercad** files above --
the parts and wiring are identical, so you build the exact same circuit in PCBX
by following `tinkercad/README.md`.

The only tool here that truly auto-builds from a file is **Wokwi** (its
`diagram.json` IS the circuit).
