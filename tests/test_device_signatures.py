import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Crypto.PublicKey import ECC

import device_signatures
from hub.edge_relay import EdgeRelay


class DeviceSignatureTests(unittest.TestCase):
    def test_signed_request_rejects_changes_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / "device.pem"
            key = ECC.generate(curve="Ed25519")
            private.write_text(key.export_key(format="PEM"), encoding="ascii")
            public = key.public_key().export_key(format="PEM")
            with patch.dict(device_signatures.PUBLIC_KEYS, {"drone": public}):
                headers = device_signatures.sign_headers(
                    private, "POST", "/edge/drone/telemetry", b'{"armed":false}')
                with patch.dict("os.environ", {"VANNI_RELAY_DB": str(Path(directory) / "relay.db")}):
                    relay = EdgeRelay()
                self.assertTrue(relay.authenticate_signed_device(
                    "drone", "POST", "/edge/drone/telemetry", b'{"armed":false}', headers))
                self.assertFalse(relay.authenticate_signed_device(
                    "drone", "POST", "/edge/drone/telemetry", b'{"armed":false}', headers))
                self.assertIsNone(device_signatures.verify_headers(
                    "drone", "POST", "/edge/drone/claim/next", b'{"armed":false}', headers))
                self.assertIsNone(device_signatures.verify_headers(
                    "drone", "POST", "/edge/drone/telemetry", b'{"armed":true}', headers))
                stale = {**headers, "X-Vanni-Timestamp": "1"}
                self.assertIsNone(device_signatures.verify_headers(
                    "drone", "POST", "/edge/drone/telemetry", b'{"armed":false}', stale))


if __name__ == "__main__":
    unittest.main()
