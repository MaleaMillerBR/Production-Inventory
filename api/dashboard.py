import json
from urllib.parse import parse_qs, urlparse

from http.server import BaseHTTPRequestHandler

from lib.dashboard import build_dashboard_rows
from lib.odoo_client import OdooClient
from lib.constants import WORK_AREAS


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            work_area = qs.get("work_area")
            if work_area is None:
                selected = WORK_AREAS
            else:
                selected = [w for w in work_area if w]

            client = OdooClient()
            rows = build_dashboard_rows(client, selected)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(rows).encode("utf-8"))
        except ValueError as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"detail": str(e)}).encode("utf-8"))
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"detail": str(e)}).encode("utf-8"))
