"""Creates the desktop shortcuts. Run once: uv run python -m convohub.shortcut

- "ConvoHub"           starts it without a console window (or only opens the page if it's already running)
- "ConvoHub - خاموش"   stops it
Both use pythonw from the project's .venv and the ConvoHub icon.
"""

import base64
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import config

ICON = config.ROOT_DIR / "convohub" / "static" / "icon.ico"


def _pythonw() -> Path:
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    if not candidate.exists():
        raise SystemExit(f"pythonw.exe پیدا نشد کنار {exe}. اول `uv sync` رو اجرا کن.")
    return candidate


def _ps_quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def create(desktop: Path | None = None) -> list[Path]:
    if sys.platform != "win32":
        raise SystemExit("این شورتکات فقط برای ویندوزه.")
    pythonw = _pythonw()
    # (final name, temporary ASCII name, arguments, description)
    items = [("ConvoHub", "convohub-open", "-m convohub", "Open ConvoHub"),
             ("ConvoHub - خاموش", "convohub-stop", "-m convohub --stop", "Stop ConvoHub")]
    # WScript.Shell can't save a .lnk whose path has non-ANSI characters (the Persian name, or a Desktop
    # under a Persian user name), so shortcuts are saved in a temp folder with ASCII names and then
    # moved and renamed from Python.
    with tempfile.TemporaryDirectory() as tmp:
        lines = ["$ws = New-Object -ComObject WScript.Shell"]
        for _, temp_name, args, desc in items:
            lines += [
                f"$s = $ws.CreateShortcut({_ps_quote(Path(tmp) / (temp_name + '.lnk'))})",
                f"$s.TargetPath = {_ps_quote(pythonw)}",
                f"$s.Arguments = {_ps_quote(args)}",
                f"$s.WorkingDirectory = {_ps_quote(config.ROOT_DIR)}",
                f"$s.IconLocation = {_ps_quote(str(ICON) + ',0')}",
                f"$s.Description = {_ps_quote(desc)}",
                "$s.Save()",
            ]
        lines.append("Write-Output ([Environment]::GetFolderPath('Desktop'))")
        script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8\n" + "\n".join(lines)
        # -EncodedCommand (UTF-16LE, base64) keeps any non-ASCII path in the script intact.
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                             capture_output=True, text=True, encoding="utf-8")
        if out.returncode != 0:
            raise SystemExit(f"ساختن شورتکات نشد:\n{out.stderr}")
        desk = desktop or Path(out.stdout.strip().splitlines()[-1])
        made = []
        for name, temp_name, _, _ in items:
            src = Path(tmp) / f"{temp_name}.lnk"
            if not src.exists():
                raise SystemExit(f"ساختن شورتکات «{name}» نشد.")
            dest = desk / f"{name}.lnk"
            shutil.copyfile(src, dest)  # copy, not move: the temp folder may be on another drive
            made.append(dest)
    return made


if __name__ == "__main__":
    for p in create():
        print("ساخته شد:", p)
