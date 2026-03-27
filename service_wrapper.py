import threading
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
    def log_message(self, format, *args):
        pass

def start_health():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(("", port), HealthHandler).serve_forever()

threading.Thread(target=start_health, daemon=True).start()

target = os.environ.get("SERVICE_SCRIPT", "batch_settler.py")
exec(open(target).read())
