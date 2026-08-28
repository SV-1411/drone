"""Download ASVP-ESD from Zenodo with resume support and progress."""
import os
import sys
import time
import urllib.request

URL = "https://zenodo.org/records/4782712/files/ASVP_ESD.zip?download=1"
ARCHIVE = os.path.join(os.path.dirname(__file__), "..", ".cache", "audio-datasets", "ASVP_ESD.zip")

def download():
    os.makedirs(os.path.dirname(ARCHIVE), exist_ok=True)

    for attempt in range(10):
        existing = os.path.getsize(ARCHIVE) if os.path.exists(ARCHIVE) else 0
        mode = "ab" if existing > 0 else "wb"
        print(f"[attempt {attempt+1}] {'Resuming' if existing else 'Starting'} from {existing/1024/1024:.0f} MB", flush=True)

        try:
            req = urllib.request.Request(URL)
            if existing > 0:
                req.add_header("Range", f"bytes={existing}-")

            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                if resp.status == 206:
                    total += existing
                elif resp.status == 200:
                    existing = 0
                    mode = "wb"
                    total = int(resp.headers.get("Content-Length", 0))

                print(f"Total: {total/1024/1024:.0f} MB", flush=True)
                start = time.time()
                downloaded = existing

                with open(ARCHIVE, mode) as f:
                    while True:
                        chunk = resp.read(131072)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        elapsed = time.time() - start
                        if elapsed > 0 and int(elapsed) % 30 < 1:
                            speed = (downloaded - existing) / elapsed
                            eta = (total - downloaded) / speed / 60 if speed > 0 else 0
                            print(f"{downloaded/1024/1024:.0f}/{total/1024/1024:.0f} MB  {speed/1024/1024:.1f} MB/s  ETA {eta:.0f}m", flush=True)

                if downloaded >= total * 0.99:
                    print(f"COMPLETE: {downloaded/1024/1024:.0f} MB", flush=True)
                    return True
                else:
                    print(f"Incomplete: {downloaded}/{total}, retrying...", flush=True)

        except Exception as e:
            print(f"Error: {e}, retrying in 5s...", flush=True)
            time.sleep(5)

    print("FAILED after 10 attempts", flush=True)
    return False

if __name__ == "__main__":
    ok = download()
    sys.exit(0 if ok else 1)
