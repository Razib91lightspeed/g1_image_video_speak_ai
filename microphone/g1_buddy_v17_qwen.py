
"""Buddy V17: local date answers and existing V15 Qwen backend."""

from datetime import datetime
from zoneinfo import ZoneInfo
import re

from g1_buddy_v15_qwen import (
    ask_qwen as original_ask_qwen,
    needs_camera,
    status_mode,
)


def ask_qwen(question, history, with_image):
    text = question.lower().strip()

    date_request = re.search(
        r"today.s date|current date|what.s the date|"
        r"what day is it|day today|date today",
        text,
    )

    if date_request and not with_image:
        now = datetime.now(ZoneInfo("Europe/Helsinki"))

        answer = (
            "Today is "
            + now.strftime("%A, %d %B %Y")
            + "."
        )

        print("DATE SOURCE: DEVBOX clock", flush=True)
        return answer

    return original_ask_qwen(question, history, with_image)
