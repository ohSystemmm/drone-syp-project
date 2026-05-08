import os
import datetime
import logging
import argparse
from logging.handlers import RotatingFileHandler

def setup_logging():
    logs_dir = os.path.join("GOOSE", "logs") if os.path.exists("GOOSE") else "logs"
    os.makedirs(logs_dir, exist_ok=True)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(logs_dir, f"goose_debug_{ts}.log")

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    fmt = logging.Formatter("%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = RotatingFileHandler(log_path, maxBytes=8 * 1024 * 1024, backupCount=4, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    logging.getLogger(__name__).info("Debug logging initialized: %s", log_path)
    return log_path

def parse_args():
    parser = argparse.ArgumentParser(description='Tello Drone Control with YOLO')
    parser.add_argument('--model', type=str, choices=['onnx', 'pt', 'auto'], default='auto',
                        help='Force model type: onnx or pt')
    parser.add_argument('--ip', type=str, default=None, help='Tello IP address (defaults to registry)')
    parser.add_argument('--port', type=int, default=8889, help='Tello UDP port')
    parser.add_argument('--kivy', action='store_true', help='Run with Kivy UI')
    return parser.parse_args()
