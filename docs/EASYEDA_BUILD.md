# EasyEDA build sheet -- VanniKawachh sensing-node PCB

You only design ONE custom board: the **sensing node**. The hub is a Raspberry
Pi (finished computer) and the drone is a Pixhawk + ESCs (off-the-shelf), so
neither needs a PCB. This sheet builds the node as a **carrier board**: the
ESP32-S3 DevKit and the sensor/radio modules plug into headers -- the simplest,
lowest-risk board to fab for a first prototype.

Import note: don't expect a one-click import. Build it by placing these exact
library parts and wiring the netlist below -- ~20 minutes, and it is correct by
construction.

## 1. Parts to place (search these terms in EasyEDA's library)

| Qty | Search in EasyEDA "Libraries" | Designator | Role |
|---|---|---|---|
| 1 | `ESP32-S3-DevKitC` (or 2x `Header-Female 1x22 2.54`) | U1 | main MCU (plugs in) |
| 1 | `Header-Female 1x6 2.54` | J_MIC | INMP441 mic module |
| 1 | `Header-Female 1x8 2.54` | J_LORA | SX1278 (Ra-02) module |
| 1 | `Header-Female 1x5 2.54` | J_GPS | NEO-6M GPS module |
| 1 | `Header-Female 1x3 2.54` | J_PIR | HC-SR501 PIR |
| 1 | `Photoresistor` (or `Header 1x2` for an LDR module) | LDR1 | light sensor |
| 1 | `Resistor 10k 0805` | R1 | LDR divider |
| 1 | `Resistor 220 0805` | R2 | status LED |
| 1 | `LED 0805` | D1 | status LED |
| 1 | `Header-Female 1x6 2.54` (TP4056) | J_CHG | TP4056 charger module |
| 1 | `Header-Female 1x4 2.54` (MT3608) | J_BOOST | 5 V boost module |
| 1 | `Screw Terminal 2P 5.08` | J_BAT | 18650 battery in |
| 2 | `Capacitor 100nF 0805` | C1,C2 | decoupling (mic, LoRa) |

If you prefer a fully integrated board later, swap U1 for the
`ESP32-S3-WROOM-1` module symbol and add the USB + AMS1117-3.3 + auto-reset
circuit -- but the DevKit-on-headers version above is what to fab first.

## 2. Netlist (wire these -- pin -> pin)

Power rails:
* **+3V3**: ESP32 `3V3` -> J_MIC.VDD, J_LORA.VCC, J_GPS.VCC(if 3V3), LDR1 top, C1, C2, TP4056 OUT+
* **+5V**: J_BOOST.OUT -> ESP32 `VIN/5V`, J_PIR.VCC, J_GPS.VCC(if 5V)
* **GND** (one net): ESP32 `GND`, all module GNDs, R1 bottom, C1, C2, D1 cathode side of R2, J_BAT-, TP4056 GND, J_BOOST GND

Signals (ESP32-S3 GPIO -> module pin):
| Net | ESP32 pin | goes to |
|---|---|---|
| I2S_SCK | GPIO4 | J_MIC.SCK |
| I2S_WS | GPIO5 | J_MIC.WS |
| I2S_SD | GPIO6 | J_MIC.SD |
| MIC_LR | GND | J_MIC.L/R |
| SPI_SCK | GPIO12 | J_LORA.SCK |
| SPI_MISO | GPIO13 | J_LORA.MISO |
| SPI_MOSI | GPIO11 | J_LORA.MOSI |
| LORA_CS | GPIO10 | J_LORA.NSS |
| LORA_RST | GPIO9 | J_LORA.RST |
| LORA_DIO0 | GPIO8 | J_LORA.DIO0 |
| GPS_RX | GPIO18 | J_GPS.TX |
| GPS_TX | GPIO17 | J_GPS.RX |
| PIR_OUT | GPIO15 | J_PIR.OUT |
| LDR_ADC | GPIO1 | LDR1 / R1 junction (LDR1 top->3V3, R1->GND) |
| LED | GPIO2 | R2 -> D1 anode; D1 cathode -> GND |

Power path: J_BAT -> TP4056 (charge/protect) -> +3V3 rail (via ESP32 or an
LDO on the DevKit) and -> J_BOOST -> +5V rail. Decouple the mic and LoRa with
C1/C2 (100 nF from VCC to GND, close to each header).

## 3. Steps in EasyEDA

1. **File -> New -> Project -> New Schematic.**
2. Place every part from the table (Libraries panel -> search -> click to drop).
3. Wire the netlist. Tip: use **net labels** (the "Netlabel" tool) named `+3V3`,
   `+5V`, `GND`, `I2S_SCK`, etc. -- label a pin instead of drawing long wires,
   and same-named labels connect automatically. Much faster and cleaner.
4. **Design -> Convert Schematic to PCB.**
5. Arrange the parts, set board outline (~60 x 40 mm), route (or Auto Router).
6. **Fabrication -> One-click Order (JLCPCB)** for the board cost -- this is the
   real fab number for your budget (typically ~$2 for 5 boards + shipping).

## 4. What this proves for the pitch

A real, manufacturable **schematic + PCB** of the exact sensing-node hardware,
with a fab quote. Combined with the live demos (Wokwi node -> dashboard, SITL
flight), the committee sees: it works (sim) AND it's a real board you can order
(this). That is the full case for the seed money.
