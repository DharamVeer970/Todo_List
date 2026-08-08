"""To-Do backend: JSON API + serves the Frontend folder. Stdlib only.

Run:  python app.py        ->  http://127.0.0.1:8000/

Phone access (same wifi):
    set TODO_HOST=0.0.0.0
    set TODO_PASSWORD=something          # required off localhost
    set TODO_CERT=cert.pem               # optional, serves HTTPS instead
    python app.py                        # prints the address to open

API:
  GET    /api/tasks         -> [task, ...]
  POST   /api/tasks         {title, priority?, due?, repeat?}   -> task
  PATCH  /api/tasks/<id>    {title?|priority?|due?|done?|repeat?} -> task
  PATCH  /api/tasks/order   {ids: [...]}                        -> {reordered: n}
  DELETE /api/tasks/<id>                                        -> {deleted: id}
  DELETE /api/tasks/done                                        -> {deleted: n}
"""
import base64
import hmac
import json
import os
import socket
import ssl
import traceback
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

import db
import mailer

FRONTEND = Path(__file__).resolve().parent.parent / "Frontend"
HOST = os.environ.get("TODO_HOST", "127.0.0.1")
PORT = int(os.environ.get("TODO_PORT") or 8000)
PASSWORD = os.environ.get("TODO_PASSWORD", "")
CERT = os.environ.get("TODO_CERT")  # PEM certificate; enables HTTPS when set
KEY = os.environ.get("TODO_KEY")  # private key, if it lives in a separate file
MAX_BODY = 64_000


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(FRONTEND), **kw)

    # --- helpers ------------------------------------------------------
    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _payload(self):
        size = int(self.headers.get("Content-Length") or 0)
        if size > MAX_BODY:
            raise ValueError("payload too large")
        return json.loads(self.rfile.read(size) or b"{}")

    def _id(self):
        tail = urlparse(self.path).path.rsplit("/", 1)[-1]
        if not tail.isdigit():
            raise ValueError("bad task id")
        return int(tail)

    def _api(self, fn):
        """Run a handler, turning bad input into 400 and misses into 404."""
        try:
            self._json(fn())
        except ValueError as e:
            self._json({"error": str(e)}, 400)
        except KeyError:
            self._json({"error": "task not found"}, 404)
        except Exception:
            # Always answer. Letting this propagate drops the connection with
            # no reply, so the browser sees a dead fetch and the UI just
            # freezes with no clue why.
            traceback.print_exc()
            self._json({"error": "server error - check the terminal"}, 500)

    def _guard(self):
        """Basic auth, only when TODO_PASSWORD is set."""
        if not PASSWORD:
            return True
        header = self.headers.get("Authorization", "")
        if header.startswith("Basic "):
            try:
                given = base64.b64decode(header[6:]).decode().partition(":")[2]
            except Exception:
                given = ""
            if hmac.compare_digest(given, PASSWORD):
                return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="To-Do"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    # --- routes -------------------------------------------------------
    def do_GET(self):
        if not self._guard():
            return
        if urlparse(self.path).path == "/api/tasks":
            return self._api(db.all_tasks)
        super().do_GET()  # everything else is a file from Frontend/

    def do_POST(self):
        if not self._guard():
            return
        self._api(lambda: db.add(self._payload()))

    def do_PATCH(self):
        if not self._guard():
            return
        if urlparse(self.path).path == "/api/tasks/order":
            return self._api(lambda: db.reorder(self._payload()))
        self._api(lambda: db.update(self._id(), self._payload()))

    def do_DELETE(self):
        if not self._guard():
            return
        if urlparse(self.path).path == "/api/tasks/done":
            return self._api(db.clear_done)
        self._api(lambda: db.delete(self._id()))


def lan_addresses():
    """Every non-loopback IPv4 this machine answers on, for phone access."""
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        return []
    return sorted({i[4][0] for i in infos if not i[4][0].startswith("127.")})


def url(host):
    scheme = "https" if CERT else "http"
    return f"{scheme}://{host}:{PORT}/"


def serve(server):
    """Serve, wrapped in TLS when a certificate is configured.

    Without TODO_CERT this is plain HTTP, which is the point: it binds to
    localhost by default, where a self-signed certificate buys nothing but
    browser warnings. Set TODO_CERT/TODO_KEY when exposing it beyond your own
    machine, so the Basic auth password is not sent in clear text.
    """
    if CERT:
        for label, path in (("TODO_CERT", CERT), ("TODO_KEY", KEY)):
            if path and not Path(path).is_file():
                raise SystemExit(f"{label} is not a file: {path}")
        # create_default_context applies the hardened cipher list and options;
        # a bare SSLContext() would not. CLIENT_AUTH is the server-side purpose.
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(CERT, KEY or CERT)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()  # NOSONAR - S5332: TLS above; plain HTTP is localhost-only by default


def main():
    db.init()
    mailer.start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"To-Do running at   {url('127.0.0.1')}   (Ctrl+C to stop)", flush=True)
    if HOST not in ("127.0.0.1", "localhost"):
        for ip in lan_addresses():
            print(f"On your phone:     {url(ip)}", flush=True)
        if not PASSWORD:
            print("!! open to your whole network with no password - set TODO_PASSWORD", flush=True)
    if not os.environ.get("TODO_NO_BROWSER"):
        webbrowser.open(url("127.0.0.1"))
    try:
        serve(server)
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
