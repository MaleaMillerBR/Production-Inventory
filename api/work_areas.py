import json
from http.server import BaseHTTPRequestHandler

from lib.constants import WORK_AREAS


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(WORK_AREAS).encode("utf-8"))
