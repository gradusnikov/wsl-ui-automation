#!/usr/bin/env python3
"""Persistent EasyOCR server. Loads model once, serves over HTTP."""
import sys
import os
import json
import signal
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import numpy as np
import cv2
import easyocr

HOST = "127.0.0.1"
PORT = 18200
PID_FILE = "/tmp/ocr_server.pid"

reader = None


def load_model():
    global reader
    langs = os.environ.get("OCR_LANGS", "pl,en").split(",")
    print(f"Loading EasyOCR with languages: {langs}...", flush=True)
    reader = easyocr.Reader(langs, gpu=True, verbose=False)
    # Warmup
    dummy = np.zeros((64, 64, 3), dtype=np.uint8)
    reader.readtext(dummy)
    print("OCR model ready.", flush=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/ocr":
            length = int(self.headers["Content-Length"])
            body = self.rfile.read(length)

            arr = np.frombuffer(body, dtype=np.uint8)
            image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if image is None:
                self.send_error(400, "Could not decode image")
                return

            results = reader.readtext(image)

            regions = []
            for bbox, text, conf in results:
                xs = [int(p[0]) for p in bbox]
                ys = [int(p[1]) for p in bbox]
                x1, y1 = min(xs), min(ys)
                x2, y2 = max(xs), max(ys)
                regions.append({
                    "text": text,
                    "confidence": round(float(conf), 3),
                    "bbox": [x1, y1, x2 - x1, y2 - y1],
                    "center": [(x1 + x2) // 2, (y1 + y2) // 2],
                })

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(regions).encode())

        elif parsed.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_error(404)

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_error(404)


def cleanup(signum=None, frame=None):
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    sys.exit(0)


def main():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    load_model()
    server = HTTPServer((HOST, PORT), Handler)
    print(f"OCR server listening on {HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    finally:
        cleanup()


if __name__ == "__main__":
    main()
