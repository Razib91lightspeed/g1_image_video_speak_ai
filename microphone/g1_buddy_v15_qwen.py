#!/usr/bin/env python3
"""Opt-in G1 microphone -> Whisper -> Qwen -> Piper -> native G1 speaker.
Runs on DEVBOX; keeps microphone clips in RAM and generated audio in temp/audio.
"""
import base64
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import wave

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('HF_HOME', str(ROOT / 'microphone/models'))
os.environ.setdefault('XDG_CACHE_HOME', str(ROOT / 'temp/cache'))

import numpy as np
from faster_whisper import WhisperModel

SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=6', 'g1-ailab']
MIC_RECORD = '/home/unitree/Desktop/razib/g1_image_video_speak_ai/build/mic_record/g1_record_mic'
MIC_STATUS = '/home/unitree/Desktop/razib/g1_image_video_speak_ai/build/mic_status/g1_mic_status'
SPEAKER = '/home/unitree/Desktop/razib/g1_image_video_speak_ai/build/robot_pcm/g1_play_pcm'
REMOTE_AUDIO = '/home/unitree/Desktop/razib/g1_image_video_speak_ai/temp/audio'
QWEN_URL = 'http://127.0.0.1:18000/v1/chat/completions'
QWEN_MODEL = 'Qwen/Qwen3-VL-4B-Instruct'
PIPER = str(ROOT / '.venv/bin/python')
AUDIO_DIR = ROOT / 'temp/audio'

CAMERA_CODE = r'''
import cv2, sys
cap = cv2.VideoCapture(6, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    raise RuntimeError('RealSense /dev/video6 could not be opened')
frame = None
for _ in range(8):
    ok, candidate = cap.read()
    if ok:
        frame = candidate
cap.release()
if frame is None:
    raise RuntimeError('Could not capture a G1 camera image')
ok, jpg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
if not ok:
    raise RuntimeError('JPEG encoding failed')
sys.stdout.buffer.write(jpg.tobytes())
'''

SYSTEM = (
    'You are Buddy, a friendly, natural conversational assistant speaking through a physical '
    'Unitree G1 robot. Answer conversationally in one or two short sentences unless asked '
    'for detail. You can look through the G1 RGB camera only when an image is supplied '
    'with the current message. Never claim you can see something if no fresh image is '
    'provided. Do not invent colors, distances or objects. You cannot move the robot '
    'from this conversation controller. Speak in plain English without markdown.'
)


def ssh_run(command, *, input_bytes=None, timeout=35):
    return subprocess.run(SSH + [command], input=input_bytes, capture_output=True, timeout=timeout)


def status_mode():
    p = ssh_run(shlex.quote(MIC_STATUS), timeout=12)
    output = (p.stdout + p.stderr).decode(errors='replace')
    match = re.search(r'Response:\s*\{\s*"mode"\s*:\s*(\d+)', output)
    return int(match.group(1)) if p.returncode == 0 and match else None


def listen_once(model):
    p = ssh_run(shlex.quote(MIC_RECORD), timeout=40)
    if p.returncode != 0 or len(p.stdout) != 160000:
        err = p.stderr.decode(errors='replace')[-1000:]
        raise RuntimeError(f'Microphone capture failed ({p.returncode}, {len(p.stdout)} bytes): {err}')
    if status_mode() != 2:
        raise RuntimeError('Microphone mode 2 not verified after recording. Stop testing and inspect state.')
    samples = np.frombuffer(p.stdout, dtype='<i2').astype(np.float32) / 32768.0
    if np.max(np.abs(samples)) < 0.002:
        return ''
    segments, _ = model.transcribe(samples, language='en', beam_size=3,
                                   vad_filter=False, condition_on_previous_text=False)
    return ' '.join(seg.text.strip() for seg in segments).strip()


def wake_detected(text):
    t = re.sub(r'[^a-z ]+', ' ', text.lower())
    t = ' '.join(t.split())
    # Whisper previously transcribed the intended phrase as "Everybody".
    return ('hey buddy' in t or 'hey body' in t or
            t in ('everybody', 'hey everybody', 'hi buddy', 'hi body') or
            (t.startswith('everybody ') and len(t.split()) <= 10))


def needs_camera(question, last_vision):
    q = question.lower()
    cues = ('what do you see', 'what can you see', 'look at', 'in front of you',
            'what is this', "what's this", 'what is that', 'what color', 'what colour',
            'how many', 'describe the scene', 'on the table', 'in the room',
            'camera', 'backpack', 'chair')
    followup = ('what about it', 'what about that', 'what does it look like',
                'is it', 'does it', 'where is it')
    return any(x in q for x in cues) or (last_vision and any(x in q for x in followup))


def get_camera_jpeg():
    command = 'python3 -c ' + shlex.quote(CAMERA_CODE)
    p = ssh_run(command, timeout=30)
    if p.returncode != 0 or not p.stdout.startswith(b'\xff\xd8'):
        raise RuntimeError('Camera capture failed: ' + p.stderr.decode(errors='replace')[-500:])
    return p.stdout




def ask_qwen(question, history, with_image):
    # Spark's current Qwen API requires exactly:
    # one user message containing one text and one image.

    context = [SYSTEM, "", "Previous conversation:"]

    for message in history[-4:]:
        context.append(
            message["role"].upper() + ": " + message["content"]
        )

    context.extend([
        "",
        "Current user question:",
        question,
        "",
        "Answer naturally, briefly and accurately."
    ])

    if with_image:
        context.append(
            "Use the attached live camera image to answer "
            "the user's visual question. Do not invent objects."
        )
    else:
        context.append(
            "The attached image is a neutral placeholder, not a live camera observation. " "This is a general conversation question. "
            "Answer using your knowledge and conversation context. "
            "Do not describe the attached image unless it is relevant."
        )

    prompt = "\\n".join(context)

    # Always attach exactly one fresh camera image.
    if with_image:
        print("IMAGE SOURCE: Live G1 camera", flush=True)
        jpg = get_camera_jpeg()
    else:
        print("IMAGE SOURCE: Neutral placeholder", flush=True)
        jpg = (ROOT / "temp/neutral_qwen_image.jpg").read_bytes()


    data_uri = (
        "data:image/jpeg;base64,"
        + base64.b64encode(jpg).decode("ascii")
    )

    content = [
        {"type": "text", "text": prompt},
        {
            "type": "image_url",
            "image_url": {"url": data_uri}
        }
    ]

    payload = json.dumps({
        "model": QWEN_MODEL,
        "messages": [
            {"role": "user", "content": content}
        ],
        "temperature": 0.0,
        "max_tokens": 80
    }).encode()

    request = urllib.request.Request(
        QWEN_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=80) as result:
            response = json.load(result)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:600]
        raise RuntimeError(
            f"Qwen HTTP {exc.code}: {detail}"
        ) from exc

    answer = response["choices"][0]["message"]["content"]

    if isinstance(answer, list):
        answer = " ".join(
            part.get("text", "")
            for part in answer
            if isinstance(part, dict)
        )

    answer = str(answer).strip()

    if not answer:
        raise RuntimeError("Qwen returned an empty answer")

    history.extend([
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer}
    ])

    return answer


def speak(text):
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    name = 'buddy_' + uuid.uuid4().hex[:12]
    wav_path = AUDIO_DIR / (name + '.wav')
    pcm_path = AUDIO_DIR / (name + '.pcm')
    subprocess.run([PIPER, '-m', 'en_US-ryan-medium',
                    '--data-dir', str(ROOT / 'speech/models'),
                    '--length-scale', '1.3', '--sentence-silence', '0.4',
                    '-f', str(wav_path), '--', text], check=True, timeout=90)
    with wave.open(str(wav_path), 'rb') as audio:
        rate = audio.getframerate()
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
            raise RuntimeError('Unexpected Piper audio format')
        pcm = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').astype(np.float64)
    if not len(pcm):
        raise RuntimeError('Piper produced empty audio')
    dest_len = round(len(pcm) * 16000 / rate)
    converted = np.interp(np.arange(dest_len) * rate / 16000,
                          np.arange(len(pcm)), pcm)
    converted = np.clip(np.rint(converted * 0.35), -32768, 32767).astype('<i2')
    pcm_path.write_bytes(converted.tobytes())
    if len(converted) / 16000 > 30:
        raise RuntimeError('Speech exceeds the native player 30-second limit')
    remote_path = REMOTE_AUDIO + '/' + pcm_path.name
    upload = ssh_run('mkdir -p ' + shlex.quote(REMOTE_AUDIO) + ' && cat > ' +
                     shlex.quote(remote_path), input_bytes=pcm_path.read_bytes(), timeout=30)
    if upload.returncode != 0:
        raise RuntimeError('PCM transfer failed: ' + upload.stderr.decode(errors='replace'))
    p = ssh_run(shlex.quote(SPEAKER) + ' ' + shlex.quote(remote_path), timeout=60)
    if p.returncode != 0:
        raise RuntimeError('Speaker playback failed: ' + p.stderr.decode(errors='replace'))
    # Audio is retained in temp/audio for the existing five-hour cleanup job.


def main():
    (ROOT / 'microphone/models').mkdir(parents=True, exist_ok=True)
    (ROOT / 'temp/cache').mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    current = status_mode()
    if current != 2:
        raise RuntimeError(f'Microphone must initially be mode 2; got {current!r}')
    print('Loading local Whisper base.en...', flush=True)
    model = WhisperModel('base.en', device='cpu', compute_type='int8',
                         download_root=str(ROOT / 'microphone/models'))
    print('Buddy ready. G1 listens in five-second windows. Ctrl+C to exit.', flush=True)
    session_until = 0.0
    history = []
    last_vision = False
    while True:
        print('\nListening for wake word...' if time.monotonic() >= session_until
              else '\nListening for your next question...', flush=True)
        heard = listen_once(model)
        if heard:
            print('Heard:', heard, flush=True)
        active = time.monotonic() < session_until
        if not active:
            if not wake_detected(heard):
                continue
            history = []
            last_vision = False
            print('Buddy: Hi! How can I help you?', flush=True)
            speak('Hi! How can I help you?')
            session_until = time.monotonic() + 30
            continue
        if not heard:
            continue
        q = heard.lower().strip(' .!?')
        if 'goodbye buddy' in q or 'bye buddy' in q or q == 'goodbye':
            speak('See you later!')
            session_until = 0
            continue
        try:
            vision = needs_camera(heard, last_vision)
            answer = ask_qwen(heard, history, vision)
            last_vision = vision
            print('Buddy:', answer, flush=True)
            speak(answer)
            session_until = time.monotonic() + 30
        except Exception as exc:
            print('Question failed:', exc, file=sys.stderr, flush=True)
            session_until = time.monotonic() + 30


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nStopped by user. Confirm microphone mode 2.', flush=True)
    except Exception as exc:
        print('STOP:', exc, file=sys.stderr, flush=True)
        sys.exit(1)


# Buddy V12 personality and conversation policy.
# Extended policy remains in configs/buddy_identity_policy_v1.txt.
# Keep this operational prompt short for the current Qwen API.

SYSTEM = (
    "You are Buddy, a friendly Unitree G1 robot. "
    "Your main programmer and research partner is Razib. "
    "You are his cooperative, humorous friend. "
    "You receive text recognized by Whisper, not raw microphone audio. "
    "Answer the current question directly and briefly. "
    "Never invent sensor readings or claim physical actions. "
    "Use plain English. Physical actions require safety approval."
)
