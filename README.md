# Unitree G1 — Vision, Image Recognition and Natural Speech AI

A Physical AI experiment connecting a physical Unitree G1 EDU humanoid
robot to the Qwen3-VL vision-language model running on NVIDIA DGX Spark.

The robot captures images through its Intel RealSense D435i RGB camera.
A controller on AILAB DEVBOX sends the images and text prompts to Qwen.
The system also supports generating natural-sounding American English
speech with Piper TTS and playing it through the robot's internal speaker
using Unitree's native audio streaming interface.

The project is being developed toward a conversational humanoid assistant
that responds to "Hey Buddy", understands spoken questions, recognizes
visible objects, and answers through its built-in speaker.

## 1. Current development status

Last updated: November 3, 2026.

| Component | Status |
|---|---|
| DEVBOX to G1 passwordless SSH | Verified |
| DEVBOX to Spark passwordless SSH | Verified |
| RealSense RGB camera capture | Verified |
| Qwen3-VL API connectivity | Verified |
| Camera image recognition using Qwen | Verified |
| G1 built-in TTS | Verified |
| Piper American male voice generation | Verified |
| Native G1 PCM audio playback | Verified |
| Slower, natural Piper speech | Verified by listening |
| Automatic audio cleanup | Cron installed and active on DEVBOX |
| Automatic vision-to-speech pipeline | Not yet integrated |
| Depth-based distance measurements | Not yet implemented |
| G1 microphone audio capture | Not yet verified |
| "Hey Buddy" wake-word detection | Not yet implemented |
| Speech-to-text and voice conversation | Not yet implemented |

### Verified image recognition

The physical G1 captured a 640 × 480 RGB image and sent it to Qwen3-VL.

Prompt:

    What can you see in front of you?

Actual model response:

    A chair with a backpack on it.

The description was confirmed to match the camera scene.

### Verified natural voice

The robot successfully played speech generated using:

- Piper TTS
- American English voice: en_US-ryan-medium
- Length scale: 1.3
- Sentence silence: 0.4 seconds
- Unitree native PCM audio streaming

The slower speech was audibly verified and accepted for the experiment.

## 2. System architecture

    User / MacBook
          |
          | Text prompt or SSH
          v
    AILAB DEVBOX
    10.11.0.30
          |
          +---- SSH ----> Physical Unitree G1
          |               10.11.1.2
          |               |
          |               +-- RealSense RGB camera
          |               +-- RealSense depth interfaces
          |               +-- Internal speaker
          |
          +---- SSH tunnel ----> NVIDIA DGX Spark
          |                       10.11.0.50
          |                       |
          |                       +-- Qwen3-VL-4B-Instruct
          |                       +-- Qwen API
          |
          +---- Piper TTS
                  |
                  +-- Generated WAV
                  +-- 16 kHz mono PCM
                  |
                  v
              G1 native audio playback

The camera-to-Qwen path and the Piper-to-speaker path have been tested
independently. The complete automatic pipeline is a development target.

## 3. Hardware

### Physical robot

Robot: Unitree G1 EDU

SSH:

    unitree@10.11.1.2

Operating architecture:

    aarch64

Network interfaces:

    eth0  = 192.168.123.164
    wlan0 = 10.11.1.2

The robot uses its internal Ethernet interface for local Unitree SDK
communication and Wi-Fi for SSH access from DEVBOX.

### Cameras

Detected camera hardware:

    USB HDR Camera
    Intel RealSense D435i

Confirmed device mapping:

    /dev/video0-1 : USB HDR camera
    /dev/video2-5 : RealSense depth-related interfaces
    /dev/video6-7 : RealSense RGB-related interfaces

Verified RGB capture:

    Device: /dev/video6
    Resolution: 640 x 480
    Channels: 3
    Capture method: OpenCV / V4L2

The RGB stream is working. Aligned depth capture and object-distance
measurement have not yet been implemented.

### NVIDIA DGX Spark

Host:

    rhasan@10.11.0.50

Hostname:

    ailab-spark-01

Model:

    Qwen/Qwen3-VL-4B-Instruct

Existing Docker container:

    g1-qwen-api

Qwen API on Spark:

    http://127.0.0.1:8000

The model and its existing Docker configuration are maintained separately
under the Spark ai_models project.

Do not copy model weights into this repository.

### AILAB DEVBOX

Host:

    rhasan@10.11.0.30

Network interface:

    enp2s0f0

DEVBOX is responsible for orchestration, prompt submission, image
transfer, Piper TTS, and SSH communication.

## 4. Repository location

Main project directory on DEVBOX:

    /home/rhasan/Desktop/razib/g1_image_video_speak_ai

GitHub repository:

https://github.com/Razib91lightspeed/g1_image_video_speak_ai

All new development for this experiment should remain inside this
project directory on DEVBOX.

The existing g1_experiment and g1_physical_ai projects must remain
unchanged.

The robot-side deployment directory is:

    /home/unitree/Desktop/razib/g1_image_video_speak_ai

## 5. Project files

Important files created during development:

    camera/g1_see.py
        Captures a G1 camera image through SSH and sends it to Qwen.

    speech/g1_speak.cpp
        DEVBOX copy of the original Unitree speech program.

    speech/robot/g1_speak.cpp
        Robot-side speech program using Unitree AudioClient.

    speech/robot/CMakeLists.txt
        ARM64 speech build configuration.

    speech/robot_pcm/g1_play_pcm.cpp
        Native PCM audio player for the G1 speaker.

    speech/robot_pcm/CMakeLists.txt
        ARM64 build configuration for native PCM playback.

    scripts/cleanup_audio.sh
        Deletes expired generated audio files from DEVBOX and G1.

    speech/models/
        Local Piper voice models, excluded from Git.

    temp/images/
        Temporary captured camera images.

    temp/audio/
        Temporary generated WAV and PCM files.

    .venv/
        Project-local Python environment, excluded from Git.

    build/
        Local compiled executables, excluded from Git.

Directory contents may expand as the microphone and conversation
controllers are developed.

## 6. Prerequisites

The current setup requires:

- DEVBOX running Linux
- Python 3
- OpenCV on the physical G1
- Passwordless SSH to G1 and Spark
- Running Qwen API container on Spark
- Piper TTS installed in the project environment
- Piper en_US-ryan-medium voice model
- Unitree SDK2 on the physical G1
- Native PCM player compiled for ARM64

The Python environment on DEVBOX was created using:

    python3 -m venv .venv

Piper was installed using:

    .venv/bin/python -m pip install piper-tts

The voice was downloaded using:

    .venv/bin/python -m piper.download_voices \
      --data-dir speech/models \
      en_US-ryan-medium

The downloaded model is retained locally and is not tracked by Git.

## 7. Start the system

### Step 1 — Power on the G1

Power on the physical Unitree G1.

Keep it stationary and in a stable configuration while testing
camera recognition and speech.

Verify that it is connected to the AILAB Wi-Fi network.

### Step 2 — Connect to DEVBOX

Log in to DEVBOX:

    ssh rhasan@10.11.0.30

Enter the project directory:

    cd /home/rhasan/Desktop/razib/g1_image_video_speak_ai

### Step 3 — Test the robot connection

    ssh g1-ailab 'hostname; whoami'

Expected identity:

    ubuntu
    unitree

If the SSH alias is missing, configure it to use the G1's IP address
and the previously installed SSH key.

Do not commit SSH private keys.

### Step 4 — Test Spark connectivity

    ssh spark-ailab 'hostname; whoami'

Expected:

    ailab-spark-01
    rhasan

If the spark-ailab alias is unavailable, use the configured
SSH key and rhasan@10.11.0.50 directly.

### Step 5 — Check the Qwen API tunnel

DEVBOX uses this local forwarding configuration:

    DEVBOX 127.0.0.1:18000
                 |
                 v
    Spark  127.0.0.1:8000

Check whether the tunnel is already available:

    curl http://127.0.0.1:18000/v1/models

If it is unavailable and port 18000 is free, create the tunnel:

    ssh -f -N \
      -i ~/.ssh/id_ed25519_spark \
      -o IdentitiesOnly=yes \
      -o BatchMode=yes \
      -o ExitOnForwardFailure=yes \
      -L 127.0.0.1:18000:127.0.0.1:8000 \
      rhasan@10.11.0.50

Verify:

    curl http://127.0.0.1:18000/v1/models

Expected model identifier:

    Qwen/Qwen3-VL-4B-Instruct

Do not create a second tunnel if the first is already running.

## 8. Run G1 camera recognition

From the repository root on DEVBOX:

    PYTHONDONTWRITEBYTECODE=1 python3 -B camera/g1_see.py

The program asks:

    Ask G1 what it sees [press Enter for default]:

Press Enter or enter a question, for example:

    What objects can you see in front of you?

The script:

1. Connects to the physical G1 using SSH.
2. Captures one RGB frame using OpenCV on /dev/video6.
3. Receives the JPEG image on DEVBOX.
4. Stores a temporary copy in temp/images/.
5. Sends the image and text prompt to Qwen on Spark.
6. Prints Qwen's generated answer.

The current program prints its response; it does not yet
automatically invoke the Piper speech player.

### Qwen API details

Endpoint:

    http://127.0.0.1:18000/v1/chat/completions

Model:

    Qwen/Qwen3-VL-4B-Instruct

The current API requires deterministic decoding:

    temperature = 0.0

A previous request using temperature 0.1 was rejected with:

    Only deterministic decoding is supported

The working camera script uses temperature 0.0.

## 9. Generate natural American male speech

The project uses Piper TTS locally on DEVBOX.

Voice:

    en_US-ryan-medium

The accepted voice settings are:

    length_scale = 1.3
    sentence_silence = 0.4

Generate a new speech sample:

    .venv/bin/python -m piper \
      --data-dir speech/models \
      -m en_US-ryan-medium \
      --length-scale 1.3 \
      --sentence-silence 0.4 \
      -f temp/audio/g1_voice_slow.wav \
      -- "Hey there. I'm G1, your visual assistant. I can see a chair, with a backpack resting on it."

This generates WAV audio without requiring a paid API.

The WAV output must be converted into 16 kHz, 16-bit,
mono PCM before it is passed to the current G1 native player.

## 10. Convert WAV audio to PCM

Run this on DEVBOX from the project root:

    .venv/bin/python - <<'PY'
    from pathlib import Path
    import wave
    import numpy as np

    source = Path("temp/audio/g1_voice_slow.wav")
    target = Path("temp/audio/g1_voice_slow_16k.pcm")

    with wave.open(str(source), "rb") as wav:
        rate = wav.getframerate()
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        raw = wav.readframes(wav.getnframes())

    if channels != 1 or width != 2:
        raise SystemExit("Expected 16-bit mono WAV")

    samples = np.frombuffer(raw, dtype="<i2").astype(np.float64)

    if len(samples) == 0:
        raise SystemExit("No audio samples found")

    duration = len(samples) / rate
    count = round(duration * 16000)

    resampled = np.interp(
        np.arange(count) * rate / 16000,
        np.arange(len(samples)),
        samples
    )

    pcm = np.clip(
        np.rint(resampled * 0.35),
        -32768,
        32767
    ).astype("<i2")

    target.write_bytes(pcm.tobytes())

    print("PCM conversion complete")
    print("Duration:", round(duration, 2), "seconds")
    print("Saved:", target)
    PY

This uses simple linear resampling for the current prototype.
The amplitude is reduced for the speaker test.

## 11. Play natural speech through the G1 speaker

First, transfer the generated PCM file to the robot.

From DEVBOX:

    scp temp/audio/g1_voice_slow_16k.pcm \
      g1-ailab:/home/unitree/Desktop/razib/g1_image_video_speak_ai/temp/audio/

Then play it using the ARM64 executable on the G1:

    ssh g1-ailab \
      '/home/unitree/Desktop/razib/g1_image_video_speak_ai/build/robot_pcm/g1_play_pcm /home/unitree/Desktop/razib/g1_image_video_speak_ai/temp/audio/g1_voice_slow_16k.pcm'

The player uses Unitree AudioClient::PlayStream().

The current prototype expects:

    16,000 Hz
    16-bit signed PCM
    Mono audio
    Raw PCM file

The current C++ player limits the input to 30 seconds.

The robot's native audio path successfully played the Piper
voice during physical testing.

The slower speech settings were confirmed to sound natural.

## 12. Unitree built-in TTS fallback

The older speech executable remains available as a fallback.

Robot-side executable:

    /home/unitree/Desktop/razib/g1_image_video_speak_ai/build/speech/g1_speak

Example:

    ssh g1-ailab \
      '/home/unitree/Desktop/razib/g1_image_video_speak_ai/build/speech/g1_speak "Hello. I am G1."'

The program uses:

    AudioClient::TtsMaker()

This method has been verified to work but produces the robot's
original synthetic-sounding voice.

For natural voice experiments, use Piper and PlayStream instead.

## 13. Temporary audio retention

Generated audio files are stored only temporarily.

DEVBOX directory:

    temp/audio/

G1 directory:

    /home/unitree/Desktop/razib/g1_image_video_speak_ai/temp/audio/

The cleanup script is:

    scripts/cleanup_audio.sh

It removes generated files with these extensions:

    .wav
    .mp3
    .pcm
    .ogg

Files become eligible for deletion after approximately five hours.

The cleanup job is scheduled through DEVBOX cron and runs every
five minutes while DEVBOX and cron are running.

Check the schedule:

    crontab -l | grep cleanup_audio

Check the cron service:

    systemctl is-active cron

The cleanup script attempts to remove expired files from DEVBOX
and the robot through SSH.

If DEVBOX is offline or G1 is unreachable, removal may be delayed.

Piper model weights and source files are not deleted by this job.

## 14. Troubleshooting

### Qwen API cannot be reached

Check:

    curl http://127.0.0.1:18000/v1/models

Verify that g1-qwen-api is running on Spark:

    ssh spark-ailab \
      'docker ps --filter name=g1-qwen-api'

Restore the SSH tunnel if required.

### Qwen rejects the request

The current API requires:

    temperature = 0.0

The model must be identified as:

    Qwen/Qwen3-VL-4B-Instruct

### Camera service error 3102

The original Unitree camera program encountered error 3102.

The working prototype instead captures images directly using:

    cv2.VideoCapture(6, cv2.CAP_V4L2)

Avoid modifying the robot's existing camera services
without first diagnosing their configuration.

### Unitree audio error 3104

Running the original speech client directly on DEVBOX produced
error 3104.

The working native audio client runs locally on the G1 using:

    ChannelFactory::Instance()->Init(0, "eth0")

DEVBOX invokes the robot-side executable through SSH.

### ARM64 SDK compilation failure

The unitree_sdk2_g1 audio header lacked a required Call()
overload for PlayStream.

The working robot speech build uses:

    /home/unitree/Desktop/razib/unitree_sdk2_official

Do not modify the existing SDK headers.

### Piper audio plays silently with paplay

PulseAudio playback completed without an error but produced
no audible sound through the robot's internal speaker.

The tested solution is the Unitree native PlayStream interface.

### Piper speech sounds too fast

Use:

    --length-scale 1.3
    --sentence-silence 0.4

These settings were tested and accepted.

## 15. Microphone investigation

The robot's official G1 Audio SDK example references:

    Topic: rt/audio_msg
    Multicast group: 239.168.123.161
    Port: 5555

However, an operational microphone capture pipeline has not
yet been verified.

The robot's PulseAudio sources currently expose an output
monitor, not a confirmed physical microphone input.

Microphone transport, audio format, and capture availability
must be verified before implementing wake-word detection.

## 16. Planned development

### Phase 1 — Completed components

- Physical G1 RGB image capture
- Image transfer through DEVBOX
- Qwen3-VL visual inference on Spark
- Free Piper American male speech generation
- PCM playback through the internal G1 speaker
- Audio retention cleanup

### Phase 2 — Automatic visual speech

Connect Qwen's actual response to Piper TTS automatically.

Target interaction:

    User: What do you see?

    G1 captures a fresh camera image.

    Qwen describes the visible objects.

    Piper generates natural speech.

    G1 speaks the description.

This integrated controller is not yet implemented.

### Phase 3 — Microphone and speech recognition

- Identify the G1's microphone stream
- Capture live microphone audio
- Verify audio sample format
- Implement speech-to-text
- Test spoken questions

### Phase 4 — Wake-word conversation

Wake phrase:

    Hey Buddy

Planned behavior:

1. Wait for the wake phrase.
2. Activate a conversation session.
3. Transcribe the user's question.
4. Send text and optional camera frames to Qwen.
5. Generate a response.
6. Speak using the approved Piper voice.
7. Listen for follow-up questions.
8. Return to standby after inactivity.

Wake-word detection, microphone input, and conversation
sessions remain future development work.

### Phase 5 — Depth-aware scene understanding

- Capture depth measurements from RealSense D435i
- Align RGB and depth information
- Associate measured distances with visible objects
- Answer spatial questions using actual sensor measurements

Distance estimates should not be invented by the language model.

## 17. Safety and development rules

- Keep the G1 stationary during camera and voice testing.
- Preserve all verified working configurations.
- Do not modify existing locomotion or navigation projects.
- Keep all new DEVBOX project files inside this repository.
- Keep generated audio and images inside temp/.
- Do not commit API keys, SSH private keys, or credentials.
- Do not commit generated audio or model weights.
- Keep all NVIDIA Spark work inside its existing ai_models root.
- Do not overwrite verified G1 audio or camera SDK files.
- Test new capabilities independently before integrating them.

## 18. References

Unitree SDK2:
https://github.com/unitreerobotics/unitree_sdk2

Qwen3-VL:
https://github.com/QwenLM/Qwen3-VL

Piper TTS:
https://github.com/OHF-Voice/piper1-gpl

OpenAI speech API:
https://platform.openai.com/docs/guides/text-to-speech

OpenAI TTS was evaluated but the test API account had no
remaining credits. The working voice implementation uses
local Piper TTS instead.

---

Project status: Working visual recognition and native natural
speech playback. Automatic spoken visual assistance and
wake-word conversation are the next implementation stages.
