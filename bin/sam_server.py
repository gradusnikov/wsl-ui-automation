#!/usr/bin/env python3
"""Persistent SAM segmentation server on GPU.

Endpoints:
  POST /segment_all    Body: image bytes → JSON list of segments
  POST /segment_point  Body: image bytes, Query: x=N&y=N → smallest segment at point
  GET  /health         → {"status": "ok"}

Start: python3 sam_server.py [--port 18202]
"""

import io
import json
import time
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import numpy as np
from PIL import Image

MODEL = None
PORT = 18202


def load_model():
    global MODEL
    from ultralytics import SAM
    print("Loading MobileSAM model...")
    MODEL = SAM("mobile_sam.pt")
    # Warm up
    dummy = np.zeros((64, 64, 3), dtype=np.uint8)
    MODEL(dummy, device="cuda", verbose=False)
    print("SAM model ready.")


def segment_image(img_bytes):
    """Run SAM on image, return list of segment dicts."""
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    iw, ih = img.size
    results = MODEL(np.array(img), device="cuda", verbose=False)
    masks = results[0].masks
    if masks is None:
        return [], iw, ih

    segments = []
    mask_h, mask_w = masks.data[0].shape
    sx, sy = iw / mask_w, ih / mask_h

    for i, mask in enumerate(masks.data):
        m = mask.cpu().numpy()
        ys, xs = np.where(m > 0.5)
        if len(xs) < 5:
            continue
        # Scale mask coords to image coords
        cx = int(xs.mean() * sx)
        cy = int(ys.mean() * sy)
        x0 = int(xs.min() * sx)
        y0 = int(ys.min() * sy)
        x1 = int(xs.max() * sx)
        y1 = int(ys.max() * sy)
        area = len(xs)
        segments.append({
            "id": i,
            "centroid": [cx, cy],
            "bbox": [x0, y0, x1 - x0, y1 - y0],
            "area": area,
            "mask_index": i,
        })
    return segments, iw, ih


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # quiet

    def do_GET(self):
        if self.path == "/health":
            self._json_response({"status": "ok"})
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        if parsed.path == "/segment_all":
            t0 = time.time()
            segments, iw, ih = segment_image(body)
            segments.sort(key=lambda s: s["area"])
            elapsed = time.time() - t0
            self._json_response({
                "image_size": [iw, ih],
                "count": len(segments),
                "elapsed_ms": round(elapsed * 1000),
                "segments": segments,
            })

        elif parsed.path == "/segment_point":
            px = int(params.get("x", [0])[0])
            py = int(params.get("y", [0])[0])
            t0 = time.time()
            segments, iw, ih = segment_image(body)
            elapsed = time.time() - t0

            # Find all segments containing the point, return smallest
            img = Image.open(io.BytesIO(body)).convert("RGB")
            results = MODEL(np.array(img), device="cuda", verbose=False)
            masks = results[0].masks

            if masks is None:
                self._json_response({"hit": None, "elapsed_ms": round(elapsed * 1000)})
                return

            mask_h, mask_w = masks.data[0].shape
            mx = int(px * mask_w / iw)
            my = int(py * mask_h / ih)
            mx = min(max(mx, 0), mask_w - 1)
            my = min(max(my, 0), mask_h - 1)

            hits = []
            for seg in segments:
                mid = seg["mask_index"]
                m = masks.data[mid].cpu().numpy()
                if m[my, mx] > 0.5:
                    hits.append(seg)

            # Sort by area ascending — smallest is most specific
            hits.sort(key=lambda s: s["area"])
            best = hits[0] if hits else None

            self._json_response({
                "query": [px, py],
                "hit": best,
                "all_hits": len(hits),
                "total_segments": len(segments),
                "elapsed_ms": round(elapsed * 1000),
            })
        else:
            self.send_error(404)

    def _json_response(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    load_model()
    server = HTTPServer(("127.0.0.1", args.port), Handler)
    print(f"SAM server listening on :{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
