"""Fire-and-forget macOS notification banner."""

import json
import re
import subprocess

CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def applescript_string(text: str) -> str:
    # json.dumps escapes " and \ the way AppleScript expects; control characters (which JSON would
    # turn into \uXXXX, unknown to AppleScript) are replaced first. Page titles are untrusted.
    return json.dumps(CONTROL_CHARS.sub(" ", text)[:200], ensure_ascii=False)


def notify(title: str, message: str) -> None:
    script = f"display notification {applescript_string(message)} with title {applescript_string(title)}"
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass  # notifications are a convenience; never fail a job over one
