#!/usr/bin/env bash

ROOT="/home/rhasan/Desktop/razib/g1_image_video_speak_ai"
LOCAL_AUDIO="$ROOT/temp/audio"
REMOTE_AUDIO="/home/unitree/Desktop/razib/g1_image_video_speak_ai/temp/audio"

# Delete generated audio once it is at least 300 minutes old.
if [ -d "$LOCAL_AUDIO" ]; then
    find "$LOCAL_AUDIO" -type f \
        \( -name '*.wav' -o -name '*.mp3' -o -name '*.pcm' -o -name '*.ogg' \) \
        -mmin +299 -delete
fi

# Clean the corresponding generated audio on the physical G1.
ssh -o BatchMode=yes -o ConnectTimeout=5 g1-ailab \
    "if [ -d '$REMOTE_AUDIO' ]; then
        find '$REMOTE_AUDIO' -type f \
          \( -name '*.wav' -o -name '*.mp3' -o -name '*.pcm' -o -name '*.ogg' \) \
          -mmin +299 -delete
    fi"
