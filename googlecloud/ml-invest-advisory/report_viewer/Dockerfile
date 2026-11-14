# Report Viewer (beta) container image. Standard-library Python only, so there is nothing to pip install.
#
# The image contains NO secrets: the Google OAuth client JSON is mounted at run time, never copied in. Sign-in is
# required to see any report, and each visitor's own Google account must be able to read the bucket.
#
# ---- Launch with Docker: local testing on port 8081, or on a server ------------------------------------------
#
# 1. One-time: in the Google Cloud console (APIs & Services > Credentials > your "Web application" OAuth client),
#    add this authorized redirect URI. Port 8081 differs from the 8080 you may have authorized for `python3
#    report_viewer.py`, and Google can take a few minutes to apply the change:
#        http://localhost:8081/auth/callback
#
# 2. Build (from the report_viewer/ folder):
#        docker build -t us-central1-docker.pkg.dev/todo-ae9c2/googlecloud-fr/report-viewer:beta .
#
# 3. Run, mounting the OAuth client JSON from the Docker host's file system (on the server that runs the container,
#    or on this machine). The file stays on the host and is bind-mounted read-only into the container at
#    /run/secrets/client_secret.json, where OAUTH_CLIENT_FILE (below) points; it is never copied into the image.
#
#    One-time setup on the Docker host. The container runs as the unprivileged user "viewer" (uid 10001), so give
#    that uid ownership of the file and nobody else any access (on the server, copy the downloaded file there
#    first, e.g. `scp client_secret_<id>.json server:/tmp/`; then delete the copy):
#
#        sudo install -d -m 700 -o 10001 -g 10001 /etc/report-viewer
#        sudo install -m 400 -o 10001 -g 10001 /tmp/client_secret_<id>.json /etc/report-viewer/client_secret.json
#
#    Run (the path before the colon is the file on the host):
#
#        docker run -d --name report-viewer --restart unless-stopped \
#          --read-only --cap-drop ALL --security-opt no-new-privileges \
#          -p 127.0.0.1:8081:8081 \
#          -v /etc/report-viewer/client_secret.json:/run/secrets/client_secret.json:ro \
#          us-central1-docker.pkg.dev/todo-ae9c2/googlecloud-fr/report-viewer:beta
#
#    -p 127.0.0.1:8081:8081 keeps the port reachable from the host only; a TLS reverse proxy on the host (Caddy,
#    nginx) forwards https://<your domain> to it. The proxy must pass the original Host header (or set
#    X-Forwarded-Host) and set X-Forwarded-Proto: https; sign-in then works at whatever address the browser used.
#    Authorize https://<your domain>/auth/callback on the OAuth client for each address. Google sign-in over plain
#    http only works at localhost (see README.md). With -d the container runs
#    in the background: `docker logs -f report-viewer`, `docker stop report-viewer`. Without -d (add --rm) it runs
#    in the foreground; stop it with Ctrl+C.
#
#    On this machine, mount the file from wherever it is readable by your user, and add `--user "$(id -u):$(id -g)"`
#    so the container reads it with your uid instead of 10001, e.g.
#    -v "/path/to/client_secret.json:/run/secrets/client_secret.json:ro". (A FUSE folder such as Encfs can't be
#    mounted by Docker's root daemon; copy the file to a normal folder you own first.)
#
# 4. Open http://localhost:8081 (or your https:// address) and click "Sign in with Google".
#
# Optional settings, as extra `-e NAME=value` flags on docker run: GCS_BUCKET, GCS_PREFIX, PUBLIC_BASE_URL (see
# report_viewer.py). PUBLIC_BASE_URL is unset by default; set it only to pin sign-in to that one address.
# Run the unit tests inside the image with:
#        docker run --rm --entrypoint python us-central1-docker.pkg.dev/todo-ae9c2/googlecloud-fr/report-viewer:beta -m unittest test_report_viewer.py
# ----------------------------------------------------------------------------------------------------------------

FROM python:3.12-slim

# Unbuffered output, so the startup lines and the access log show up in `docker logs` immediately.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Run as an unprivileged user.
RUN useradd --system --uid 10001 --no-create-home viewer

WORKDIR /app
COPY --chown=viewer report_viewer.py google_sign_in.py cloud_storage.py report_catalog.py test_report_viewer.py ./
COPY --chown=viewer static ./static

# Container defaults (override with docker run -e):
#   HOST=0.0.0.0  accept connections through the published port; restrict who can reach it with -p 127.0.0.1:...
#   PORT=8081     exactly this port (otherwise the server tries 80, then 8080)
#   OAUTH_CLIENT_FILE  where the OAuth client JSON is mounted
ENV HOST=0.0.0.0 \
    PORT=8081 \
    OAUTH_CLIENT_FILE=/run/secrets/client_secret.json

USER viewer
EXPOSE 8081

CMD ["python", "report_viewer.py"]
