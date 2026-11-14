#!/usr/bin/env python3
"""Experimental continuous social session: one wake greeting then open conversation via Qwen.
DEVBOX only; robot streamer is built separately. No microphone audio saved.
"""
import os
from pathlib import Path
import queue
from collections import deque
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
from g1_buddy_v12_qwen import ask_qwen, needs_camera, status_mode
import g1_buddy_v4 as base
import shlex
import uuid
import wave

SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=6', 'g1-ailab']
STREAM = '/home/unitree/Desktop/razib/g1_image_video_speak_ai/build/mic_stream_v7/g1_mic_stream_v7'
FRAMES_PER_WINDOW = 25  # 25 x 5120 bytes = 4 s at 16 kHz, mono 16-bit



from functools import lru_cache
from piper import PiperVoice, SynthesisConfig

@lru_cache(maxsize=1)
def get_voice():
    model_path = ROOT / "speech/models/en_US-ryan-medium.onnx"
    if not model_path.is_file():
        raise FileNotFoundError(model_path)
    return PiperVoice.load(str(model_path))

def is_wake(text):
    """Accept explicit Buddy address or a short greeting on its own."""
    words = re.findall(r"[a-z]+", text.lower())
    if any(word in ('buddy', 'body') for word in words):
        return True
    if len(words) <= 2 and any(word in ('hey', 'hei', 'hi', 'hello', 'everybody') for word in words):
        return True
    return False


def ignore_speech(text):
    t = text.lower()
    return not text.strip() or any(x in t for x in (
        'wakeup mode', 'wake up mode', 'makeup mode', 'pick up mode',
        'waking up mode', 'you pick up mode'))


def speak(text):
    """Working Piper CLI invocation followed by verified Unitree PCM playback."""
    base.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    name = 'buddy_' + uuid.uuid4().hex[:12]
    wav_path = base.AUDIO_DIR / (name + '.wav')
    pcm_path = base.AUDIO_DIR / (name + '.pcm')
    config = SynthesisConfig(length_scale=1.3)

    with wave.open(str(wav_path), "wb") as wav:
        get_voice().synthesize_wav(
            text,
            wav,
            syn_config=config
        )

    with wave.open(str(wav_path), 'rb') as wav:
        rate = wav.getframerate()
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or rate <= 0:
            raise RuntimeError('Unexpected Piper WAV format')
        pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2').astype(np.float64)
    if not len(pcm):
        raise RuntimeError('Piper produced empty audio')
    count = round(len(pcm) * 16000 / rate)
    resampled = np.interp(np.arange(count) * rate / 16000, np.arange(len(pcm)), pcm)
    converted = np.clip(np.rint(resampled * 0.35), -32768, 32767).astype('<i2')
    if len(converted) / 16000 > 30:
        raise RuntimeError('Speech exceeds the speaker player 30-second limit')
    pcm_path.write_bytes(converted.tobytes())
    remote_path = base.REMOTE_AUDIO + '/' + pcm_path.name
    upload = base.ssh_run(
        'mkdir -p ' + shlex.quote(base.REMOTE_AUDIO) +
        ' && cat > ' + shlex.quote(remote_path),
        input_bytes=pcm_path.read_bytes(), timeout=30)
    if upload.returncode:
        raise RuntimeError('PCM upload failed: ' + upload.stderr.decode(errors='replace'))
    playback = base.ssh_run(
        shlex.quote(base.SPEAKER) + ' ' + shlex.quote(remote_path), timeout=60)
    if playback.returncode:
        raise RuntimeError('G1 playback failed: ' + playback.stderr.decode(errors='replace'))


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

    print("Loading persistent Piper voice...", flush=True)
    get_voice()
    print("Piper ready.", flush=True)

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

    def collect_utterance():
        """Detect speech using microphone RMS and trailing silence."""
        frame_seconds = 5120 / (16000 * 2)
        prebuffer = deque(maxlen=3)
        recorded = []
        active = False
        onset = 0
        silence = 0
        noise_floor = 0.0015

        while not ended.is_set():
            try:
                frame = frames.get(timeout=1)
            except queue.Empty:
                if active:
                    break
                continue

            pcm = np.frombuffer(frame, dtype='<i2')
            samples = pcm.astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(samples * samples)))

            threshold = max(0.0045, noise_floor * 3.0)
            speech = rms > threshold

            if not active:
                prebuffer.append(frame)

                if speech:
                    onset += 1
                else:
                    onset = 0
                    noise_floor = (
                        0.95 * noise_floor +
                        0.05 * min(rms, 0.01)
                    )

                # Require two consecutive speech frames.
                if onset >= 2:
                    active = True
                    recorded = list(prebuffer)
                    silence = 0
            else:
                recorded.append(frame)

                if rms > threshold * 0.65:
                    silence = 0
                else:
                    silence += 1

                # Four silent frames = approximately 640 ms.
                if silence >= 4:
                    break

                # Prevent unbounded recordings.
                if len(recorded) * frame_seconds >= 12:
                    print(
                        "VAD: maximum utterance duration reached",
                        flush=True
                    )
                    break

        if not recorded:
            return None

        # Remove some trailing silence, keeping a little.
        if silence > 2:
            recorded = recorded[:-(silence - 2)]

        audio = np.frombuffer(
            b''.join(recorded),
            dtype='<i2'
        ).astype(np.float32) / 32768.0

        if len(audio) < 3200:
            return None

        return audio

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

    session_active = False
    history = []
    last_vision = False
    print('Ready. Wait for the G1 startup announcement, then say "Hey Buddy".', flush=True)
    print('Listening with speech-end detection. One greeting opens conversation for up to 10 minutes.', flush=True)
    try:
        while not ended.is_set():
            audio = collect_utterance()

            if audio is None:
                continue

            print(
                "SPEECH DETECTED: %.2f seconds" % (len(audio) / 16000),
                flush=True
            )

            t0 = time.monotonic()

            segments, _ = model.transcribe(
                audio,
                language='en',
                beam_size=5,
                vad_filter=False,
                condition_on_previous_text=False
            )

            heard = ' '.join(
                s.text.strip() for s in segments
            ).strip()

            print(
                "WHISPER TIME: %.2f seconds" %
                (time.monotonic() - t0),
                flush=True
            )

            if ignore_speech(heard) or not re.search(r'[a-z]{2,}', heard.lower()):
                continue
            print('HEARD:', heard, flush=True)
            if not session_active:
                if not is_wake(heard):
                    print('Standby: waiting for Hey Buddy', flush=True)
                    continue
                history.clear()
                last_vision = False
                say('Hi! How can I help you?')
                session_active = True
                continue
            q = heard.lower().strip(' .!?')
            if q in ('okay', 'ok', 'yeah', 'yes', 'uh', 'um', 'hmm'):
                print('ACKNOWLEDGEMENT: listening for the next question', flush=True)
                continue
            if 'goodbye buddy' in q or 'bye buddy' in q or q == 'goodbye':
                say('See you later!')
                session_active = False
                history.clear()
                last_vision = False
                continue
            try:
                # Do not buffer old mic audio while network calls or playback occur.
                mute.set()
                clear_frames()
                visual = needs_camera(heard, last_vision)
                print('CAMERA QUESTION:', visual, flush=True)
                qwen_start = time.monotonic()
                answer = ask_qwen(heard, history, visual)
                print(
                    "QWEN TIME: %.2f seconds" %
                    (time.monotonic() - qwen_start),
                    flush=True
                )
                last_vision = visual
                say(answer)
                # Keep conversation open until goodbye or stream safety deadline.
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
