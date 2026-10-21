# Bench verification, 2026-10-16

## Completed

- ESP32-S3 revision 0.2 identified on COM12: 8 MB flash, 8 MB embedded PSRAM.
- Full original 8,388,608-byte firmware/NVS backup retained privately at
  `C:\Users\Admin\drone\.cache\esp32-original-2026-10-16.bin`.
  SHA256: `833458b4a533d86785eff4a6db2303f90252401ed9361bbdeba87c78c72f34bf`.
- PlatformIO ESP32-S3 build succeeded. Final bench image uses 48,308 bytes RAM
  and 915,201 bytes program flash; upload tool verified flashed image hashes.
- 23 compiled C++ controller scenarios passed, including successful
  takeoff/outbound/return/land progression, locked startup, expiry, replay,
  battery/GPS/RC loss, timeout, pilot takeover, and continuous approved missions.
- 88 Python tests passed against the existing working copy. 79 Python tests
  passed against the isolated current remote checkout containing the cloud
  changes. Suites: units, relay, ESP contract, Wi-Fi receiver. Counts differ
  because the existing working copy has earlier user changes.
- ESP boots and reports `flight_locked=true`, `commissioned=false`.
- Existing Windows Wi-Fi profile provisioned privately. ESP reports
  `wifi_connected=true` and `clock_synced=true`; 2.4 GHz AP confirmed available.
- Local private operator-key setup form responds at `http://127.0.0.1:8767/`.

## Not verified / remaining

- ESP reports `uart_rx_bytes=0`, `mavlink_rx_packets=0`: no incoming TELEM2 data
  has been observed on GPIO44 at 57,600 baud. This does not identify the cause;
  inspect live Pixhawk serial settings and physical connector/pin orientation.
- Mission Planner holds COM13 open, so the direct read-only Pixhawk USB
  configuration check could not open that port.
- No operator key is provisioned yet; no authenticated cloud claim has run.
- Battery cell count is not provisioned. The known throttle-related battery
  failsafe, battery measurement calibration, GPS/EKF, RC takeover and companion
  loss failsafe still require physical verification.
- The C++ tests simulate policy transitions. No full ArduPilot SITL flight of
  this ESP implementation, physical arm, takeoff, motor test or autonomous
  flight was performed. Compilation and flashing are not flight validation.

No physical flight authorization or commissioning command was sent. Physical
MAVLink traffic was restricted to heartbeat and read-only message/parameter
requests. The installed firmware retains its default flight lock.
