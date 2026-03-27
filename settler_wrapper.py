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

# Start health check in background
threading.Thread(target=start_health, daemon=True).start()

# Run the actual settler
exec(open("batch_settler.py").read())
