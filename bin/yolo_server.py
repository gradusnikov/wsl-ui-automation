#!/usr/bin/env python3
"""Persistent YOLO-World + YOLOv8 server for object detection."""
import sys
import os
import json
import signal
import numpy as np
import cv2
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HOST = "127.0.0.1"
PORT = 18201
PID_FILE = "/tmp/yolo_server.pid"

world_model = None
coco_model = None


def load_models():
    global world_model, coco_model
    from ultralytics import YOLOWorld, YOLO

    print("Loading YOLO-World...", flush=True)
    world_model = YOLOWorld("yolov8s-world.pt")
    world_model.to("cuda")

    print("Loading YOLOv8s (COCO)...", flush=True)
    coco_model = YOLO("yolov8s.pt")
    coco_model.to("cuda")

    # Warmup both
    dummy = np.zeros((64, 64, 3), dtype=np.uint8)
    world_model.set_classes(["object"])
    world_model.predict(dummy, verbose=False)
    coco_model.predict(dummy, verbose=False)
    print("Models ready.", flush=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/detect":
            self.send_error(404)
            return

        params = parse_qs(parsed.query)
        classes = params.get("classes", [None])[0]
        conf = float(params.get("conf", ["0.15"])[0])
        mode = params.get("mode", ["auto"])[0]  # auto, world, coco

        length = int(self.headers["Content-Length"])
        body = self.rfile.read(length)

        arr = np.frombuffer(body, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            self.send_error(400, "Could not decode image")
            return

        detections = []

        if mode == "coco" or (mode == "auto" and classes is None):
            # Use standard COCO model
            results = coco_model.predict(image, verbose=False, conf=conf)
            for r in results:
                for box in r.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    detections.append({
                        "class": r.names[int(box.cls)],
                        "confidence": round(box.conf.item(), 3),
                        "bbox": [int(x1), int(y1), int(x2 - x1), int(y2 - y1)],
                        "center": [int((x1 + x2) / 2), int((y1 + y2) / 2)],
                    })

        if mode == "world" or (mode == "auto" and classes is not None):
            # Use YOLO-World with custom classes
            class_list = [c.strip() for c in classes.split(",")] if classes else ["object"]
            world_model.set_classes(class_list)
            results = world_model.predict(image, verbose=False, conf=conf)
            for r in results:
                for box in r.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    detections.append({
                        "class": r.names[int(box.cls)],
                        "confidence": round(box.conf.item(), 3),
                        "bbox": [int(x1), int(y1), int(x2 - x1), int(y2 - y1)],
                        "center": [int((x1 + x2) / 2), int((y1 + y2) / 2)],
                    })

        detections.sort(key=lambda d: d["confidence"], reverse=True)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(detections).encode())

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

    load_models()
    server = HTTPServer((HOST, PORT), Handler)
    print(f"YOLO server listening on {HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    finally:
        cleanup()


if __name__ == "__main__":
    main()
