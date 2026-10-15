"""Run external tools (ffmpeg, RIFE, Real-ESRGAN, claude) with timeouts and progress polling."""

import shutil
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

from ..config import BIN_DIR
from ..steps.step_types import StepFailure

REALESRGAN_BIN = BIN_DIR / "realesrgan" / "realesrgan-ncnn-vulkan"
REALESRGAN_MODELS = BIN_DIR / "realesrgan" / "models"
RIFE_BIN = BIN_DIR / "rife" / "rife-ncnn-vulkan"
RIFE_MODELS_DIR = BIN_DIR / "rife"


def require_tool(name_or_path: str | Path) -> str:
    path = Path(name_or_path)
    if path.is_absolute():
        if not path.exists():
            raise StepFailure(f"Thiếu công cụ {path.name}. Chạy lại scripts/setup.sh.")
        return str(path)
    found = shutil.which(str(name_or_path))
    if not found:
        raise StepFailure(f"Không tìm thấy lệnh '{name_or_path}' trong PATH.")
    return found


def run_tool(
    args: list[str],
    *,
    timeout: float | None = None,
    cwd: Path | None = None,
    poll: Callable[[], None] | None = None,
    on_line: Callable[[str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    stdin_text: str | None = None,
    label: str = "",
) -> str:
    """Run a command; return stdout. Raise StepFailure with the stderr tail on error.

    `poll` runs every second while the process is alive (e.g. to count output frames).
    `on_line` receives each stdout line as it arrives (e.g. ffmpeg -progress).
    """
    proc = subprocess.Popen(
        args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
        stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
    )
    stdout_lines: list[str] = []
    stderr_tail: list[str] = []

    def drain_stdout() -> None:
        for line in proc.stdout:
            stdout_lines.append(line)
            if on_line:
                try:
                    on_line(line.rstrip("\n"))
                except Exception:
                    pass  # a progress parse error must never stop draining the pipe

    def drain_stderr() -> None:
        for line in proc.stderr:
            stderr_tail.append(line)
            del stderr_tail[:-40]

    def feed_stdin() -> None:
        # Written from its own thread so a chatty child can never deadlock us on full pipes.
        try:
            proc.stdin.write(stdin_text)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    readers = [threading.Thread(target=drain_stdout, daemon=True), threading.Thread(target=drain_stderr, daemon=True)]
    if stdin_text is not None:
        readers.append(threading.Thread(target=feed_stdin, daemon=True))
    for reader in readers:
        reader.start()
    waited = 0.0
    while True:
        try:
            proc.wait(timeout=1)
            break
        except subprocess.TimeoutExpired:
            waited += 1
            if should_stop and should_stop():
                proc.kill()
                proc.wait()
                raise StepFailure("Job đã bị huỷ.")
            if poll:
                try:
                    poll()
                except Exception:
                    pass
            if timeout is not None and waited >= timeout:
                proc.kill()
                proc.wait()
                raise StepFailure(f"{label or Path(args[0]).name} quá thời gian {int(timeout)}s.")
    for reader in readers:
        reader.join(timeout=5)
    if proc.returncode != 0:
        tail = "".join(stderr_tail[-8:]).strip()
        raise StepFailure(f"{label or Path(args[0]).name} lỗi (mã {proc.returncode}): {tail[-600:]}")
    return "".join(stdout_lines)
