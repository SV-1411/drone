# VanniKawachh hub (dashboard + phone test pages). Build a small image that
# runs the web app. Works on any Docker host (AWS EC2, Fly.io, Railway, etc.).
#
#   docker build -t vannikawachh-hub .
#   docker run -p 80:8990 -e PORT=8990 vannikawachh-hub
#
# Behind a domain with HTTPS (needed for phone mic/GPS), put it behind a
# reverse proxy (Caddy/nginx + Let's Encrypt) or a platform that gives HTTPS.
FROM python:3.11-slim

WORKDIR /app
COPY requirements-deploy.txt .
RUN pip install --no-cache-dir -r requirements-deploy.txt

COPY hub/ ./hub/
COPY ml/ ./ml/
COPY trigger_api/ ./trigger_api/
COPY flight_core/ ./flight_core/

ENV PORT=8990
EXPOSE 8990
CMD ["sh", "-c", "uvicorn hub.webapp:app --host 0.0.0.0 --port ${PORT:-8990}"]
