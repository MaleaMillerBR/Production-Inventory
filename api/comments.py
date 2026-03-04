import json
from urllib.parse import parse_qs, urlparse

from http.server import BaseHTTPRequestHandler

from lib.comments_db import get_comments_list, save_comment, init_comments_table, _get_comment_conn


def _parse_query(path: str):
    parsed = urlparse(path)
    return parse_qs(parsed.query)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = _parse_query(self.path)
            work_areas = qs.get("work_area") or []
            work_areas = [w for w in work_areas if w]

            conn = _get_comment_conn()
            try:
                init_comments_table(conn)
            finally:
                conn.close()

            comments = get_comments_list(work_areas if work_areas else None)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(comments).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"detail": str(e)}).encode("utf-8"))

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8") if content_length else "{}"
            data = json.loads(body)
            internal_reference = data.get("internal_reference", "")
            work_area = data.get("work_area", "")
            comment = data.get("comment", "")

            conn = _get_comment_conn()
            try:
                init_comments_table(conn)
            finally:
                conn.close()

            save_comment(internal_reference, work_area, comment)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"detail": str(e)}).encode("utf-8"))
