#!/usr/bin/env python3
"""Experimental continuous G1 mic -> local Whisper -> verified v4 Qwen -> Piper.
DEVBOX only; robot streamer is built separately. No microphone audio saved.
"""
import os
from pathlib import Path
import queue
import re
import shlex
import subprocess
import sys
import threading
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('HF_HOME', str(ROOT / 'microphone/models'))
os.environ.setdefault('XDG_CACHE_HOME', str(ROOT / 'temp/cache'))
from faster_whisper import WhisperModel
from g1_buddy_v4 import ask_qwen, needs_camera, speak, status_mode

SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=6', 'g1-ailab']
STREAM = '/home/unitree/Desktop/razib/g1_image_video_speak_ai/build/mic_stream/g1_mic_stream'
FRAMES_PER_WINDOW = 25  # 25 x 5120 bytes = 4 s at 16 kHz, mono 16-bit


def is_wake(text):
    t = re.sub(r'[^a-z ]', ' ', text.lower())
    t = ' '.join(t.split())
    return any(x in t for x in ('hey buddy', 'hi buddy', 'hey body', 'hi body', 'everybody'))


def ignore_speech(text):
    t = text.lower()
    return not text.strip() or any(x in t for x in (
        'wakeup mode', 'wake up mode', 'makeup mode', 'pick up mode',
        'waking up mode', 'you pick up mode'))


def stop_stream():
    # Sends SIGINT to the unique experimental executable, allowing its mode-2 cleanup.
    subprocess.run(SSH + ['pkill -INT -x g1_mic_stream || true'],
                   capture_output=True, timeout=12)


def main():
    mode = status_mode()
    if mode != 2:
        raise RuntimeError(f'STOP: microphone mode must be 2, got {mode}.')
    print('Loading Whisper base.en...', flush=True)
    model = WhisperModel('base.en', device='cpu', compute_type='int8',
                         download_root=str(ROOT / 'microphone/models'))

    stream = subprocess.Popen(SSH + [shlex.quote(STREAM)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              bufsize=0)
    frames = queue.Queue(maxsize=40)
    mute = threading.Event()
    started = time.monotonic()
    ended = threading.Event()

    def reader():
        try:
            while True:
                frame = stream.stdout.read(5120)
                if len(frame) != 5120:
                    break
                # Ignore startup announcement, and everything during robot speech/Qwen.
                if mute.is_set() or time.monotonic() - started < 4:
                    continue
                if frames.full():
                    try:
                        frames.get_nowait()
                    except queue.Empty:
                        pass
                frames.put_nowait(frame)
        except (OSError, queue.Full):
            pass
        finally:
            ended.set()

    def errors():
        for line in iter(stream.stderr.readline, b''):
            print('[G1 microphone]', line.decode(errors='replace').rstrip(), flush=True)

    threading.Thread(target=reader, daemon=True).start()
    threading.Thread(target=errors, daemon=True).start()

    def clear_frames():
        while True:
            try:
                frames.get_nowait()
            except queue.Empty:
                break

    def say(text):
        mute.set()
        clear_frames()
        try:
            print('BUDDY:', text, flush=True)
            speak(text)
        finally:
            time.sleep(1.0)  # avoid recognizing the tail of the speaker playback
            clear_frames()
            mute.clear()

    active_until = 0.0
    history = []
    last_vision = False
    print('Ready. Wait for the G1 startup announcement, then say "Hey Buddy".', flush=True)
    print('Listening in four-second windows. Session ends automatically after 180 seconds.', flush=True)
    try:
        while not ended.is_set():
            collected = []
            for _ in range(FRAMES_PER_WINDOW):
                try:
                    collected.append(frames.get(timeout=2))
                except queue.Empty:
                    break
            if len(collected) != FRAMES_PER_WINDOW:
                if ended.is_set():
                    break
                continue
            audio = np.frombuffer(b''.join(collected), dtype='<i2').astype(np.float32) / 32768
            if float(np.sqrt(np.mean(audio * audio))) < 0.003:
                continue
            segments, _ = model.transcribe(audio, language='en', beam_size=5,
                                           vad_filter=False,
                                           condition_on_previous_text=False)
            heard = ' '.join(s.text.strip() for s in segments).strip()
            if ignore_speech(heard):
                continue
            print('HEARD:', heard, flush=True)
            if time.monotonic() >= active_until:
                if not is_wake(heard):
                    print('Standby: waiting for Hey Buddy', flush=True)
                    continue
                history.clear()
                last_vision = False
                say('Hi! How can I help you?')
                active_until = time.monotonic() + 60
                continue
            q = heard.lower().strip(' .!?')
            if 'goodbye buddy' in q or 'bye buddy' in q or q == 'goodbye':
                say('See you later!')
                active_until = 0
                continue
            try:
                # Do not buffer old mic audio while network calls or playback occur.
                mute.set()
                clear_frames()
                visual = needs_camera(heard, last_vision)
                print('CAMERA QUESTION:', visual, flush=True)
                answer = ask_qwen(heard, history, visual)
                last_vision = visual
                say(answer)
                active_until = time.monotonic() + 60
            except Exception as exc:
                print('QUESTION ERROR:', exc, file=sys.stderr, flush=True)
                time.sleep(1)
            finally:
                clear_frames()
                mute.clear()
    except KeyboardInterrupt:
        print('\nStopping Buddy...', flush=True)
    finally:
        mute.set()
        try:
            stop_stream()
        except Exception as exc:
            print('Could not request remote stop:', exc, file=sys.stderr)
        try:
            stream.wait(timeout=20)
        except subprocess.TimeoutExpired:
            print('Stream did not exit within 20 seconds. Inspect microphone status.', file=sys.stderr)
            stream.terminate()
        mode = status_mode()
        print('FINAL MICROPHONE MODE:', mode, flush=True)
        if mode != 2:
            print('WARNING: mode 2 not confirmed. Do not restart before investigating.', file=sys.stderr)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('STOP:', exc, file=sys.stderr)
        sys.exit(1)
