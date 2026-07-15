# Deploy the hub online (always on, laptop can be off)

This puts the VanniKawachh hub on the internet with a permanent web address and
real HTTPS, so phones can use it from anywhere (even mobile data) and the mic /
GPS work with no certificate warning. What runs in the cloud is the dashboard,
the phone test pages, and the detection (the committed NumPy Stage-1 model plus
the energy Stage-2 fallback; no heavy ML libraries needed).

Note on scope: this cloud instance is for the demo and phone testing. The real
field system runs the hub on the Raspberry Pi next to the LoRa gateway, because
the gateway is physically wired to it.

---

## Option A: Render (easiest, free, real HTTPS)

The repo already has `render.yaml`, so this is a few clicks.

1. Push is done. Go to https://render.com and sign in with GitHub.
2. Click **New +** then **Blueprint**.
3. Pick the `SV-1411/drone` repository. Render reads `render.yaml` and proposes
   a web service named `vannikawachh-hub`. Click **Apply**.
4. Wait for the first build (a couple of minutes). Render gives you a URL like
   `https://vannikawachh-hub.onrender.com`.
5. On your phones open:
   * `https://<your-url>/node`         sensing node
   * `https://<your-url>/drone-phone`  drone unit
   * `https://<your-url>/`             dashboard

That is it. It stays online. On the free plan the service sleeps after a while
with no traffic and takes about 30 seconds to wake on the next visit; upgrade
the plan if you want it always warm.

To change the default incident location, edit `TEST_LAT` / `TEST_LON` in the
service's Environment settings (or in `render.yaml`).

## Option B: Your AWS EC2 (you already have one) with Docker

The repo has a `Dockerfile`. On the EC2 box:

```
git clone https://github.com/SV-1411/drone.git
cd drone
docker build -t vannikawachh-hub .
docker run -d --restart unless-stopped -p 8990:8990 vannikawachh-hub
```

It now serves on `http://<ec2-ip>:8990/`. Open port 8990 in the EC2 security
group. For HTTPS (needed for phone mic/GPS), front it with Caddy, which gets a
free certificate automatically if you point a domain at the box:

```
# /etc/caddy/Caddyfile
hub.yourdomain.com {
    reverse_proxy localhost:8990
}
```
Then open `https://hub.yourdomain.com/node` on the phones.

## Option C: Any Docker platform (Fly.io, Railway, etc.)

Same `Dockerfile`. Point the platform at the repo, expose the port it gives you
(the app reads `$PORT`), and it provides HTTPS. Start command if asked:
`uvicorn hub.webapp:app --host 0.0.0.0 --port $PORT`.

## What deploys and what does not

* Deploys: dashboard, `/node`, `/drone-phone`, `/phone-alert`, the sim drone,
  the phone drone, the NumPy Stage-1 model, the energy Stage-2 verifier.
* Does not deploy: the LoRa gateway and real drone dispatch (those are physical
  and stay on the Pi). The cloud instance uses the built-in simulated drone, so
  the full phone demo works with nothing but a browser.
