"""Read-only Pi-to-Render relay check without printing private credentials."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def settings(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"\'')
    return values


def main() -> None:
    path = Path.home() / ".config" / "vannikawachh" / "wifi-alert.env"
    try:
        config = settings(path)
        base = config["VANNI_RELAY_URL"].rstrip("/")
        token = config["VANNI_RELAY_PI_TOKEN"]
        request = Request(base + "/edge/pending",
                          headers={"Authorization": "Bearer " + token})
        with urlopen(request, timeout=12) as response:
            data = json.load(response)
        print("relay_authenticated=yes")
        print("pending_alerts=" + str(len(data.get("events", []))))
    except (KeyError, OSError, ValueError, HTTPError, URLError) as exc:
        # Do not print exception messages: request URLs/headers may contain secrets.
        print("relay_authenticated=no")
        print("failure_type=" + type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
