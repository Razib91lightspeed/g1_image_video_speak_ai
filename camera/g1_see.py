#!/usr/bin/env python3
"""Capture a G1 RGB image and ask Qwen to describe it."""

import base64
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = ROOT / "temp" / "images"

MODEL = "Qwen/Qwen3-VL-4B-Instruct"
API_URL = "http://127.0.0.1:18000/v1/chat/completions"

REMOTE_CAPTURE = r'''
import cv2
import sys
import time

camera = cv2.VideoCapture(6, cv2.CAP_V4L2)

if not camera.isOpened():
    sys.exit("ERROR: Cannot open G1 RGB camera")

try:
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    frame = None

    for attempt in range(15):
        ok, candidate = camera.read()
        if ok and candidate is not None and candidate.size > 0:
            frame = candidate
            break
        time.sleep(0.1)

    if frame is None:
        sys.exit("ERROR: No camera frame received")

    ok, jpeg = cv2.imencode(
        ".jpg",
        frame,
        [cv2.IMWRITE_JPEG_QUALITY, 85]
    )

    if not ok:
        sys.exit("ERROR: JPEG encoding failed")

    sys.stdout.buffer.write(jpeg.tobytes())
    sys.stdout.buffer.flush()

finally:
    camera.release()
'''

def capture_image():
    print("\n[1/3] Capturing image from physical G1...", flush=True)

    result = subprocess.run(
        ["ssh", "-T", "g1-ailab", "python3 -B -"],
        input=REMOTE_CAPTURE.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=35,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Camera capture failed:\n"
            + result.stderr.decode("utf-8", errors="replace")
        )

    jpeg = result.stdout

    if not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
        raise RuntimeError("Invalid JPEG received from G1")

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    image_path = IMAGE_DIR / "latest_g1.jpg"
    image_path.write_bytes(jpeg)

    print(f"Image captured: {len(jpeg)} bytes")
    print(f"Saved at: {image_path}")

    return jpeg


def ask_qwen(jpeg, question):
    print("\n[2/3] Sending image to Qwen on NVIDIA Spark...", flush=True)

    encoded = base64.b64encode(jpeg).decode("ascii")

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "You are the vision assistant of a "
                            "Unitree G1 humanoid robot. "
                            "Answer based only on the camera image. "
                            "Do not invent objects or distances. "
                            "Keep the answer short and natural. "
                            "Question: " + question
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/jpeg;base64," + encoded
                        },
                    },
                ],
            }
        ],
        "max_tokens": 180,
        "temperature": 0.0,
    }

    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.load(response)

    except urllib.error.HTTPError as exc:
        error = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Qwen API HTTP {exc.code}:\n{error[:3000]}"
        ) from exc

    print("\n[3/3] Qwen response received.", flush=True)

    choices = result.get("choices", [])

    if not choices:
        raise RuntimeError(
            "Unexpected API response:\n"
            + json.dumps(result, indent=2)[:3000]
        )

    answer = choices[0].get("message", {}).get("content", "")

    if isinstance(answer, list):
        answer = " ".join(
            part.get("text", "")
            for part in answer
            if isinstance(part, dict)
        )

    print("\n========== G1 SEES ==========\n")
    print(answer)
    print("\n=============================")


def main():
    print("================================")
    print("UNITREE G1 - QWEN VISUAL TEST")
    print("================================")

    question = input(
        "\nAsk G1 what it sees [press Enter for default]: "
    ).strip()

    if not question:
        question = "What can you see in front of you?"

    jpeg = capture_image()
    ask_qwen(jpeg, question)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
