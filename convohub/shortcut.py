"""Creates the desktop shortcuts. Run once: uv run python -m convohub.shortcut

Windows only. On other systems importing this module works, and running it prints how to start ConvoHub there.

- "ConvoHub"           starts it without a console window (or only opens the page if it's already running)
- "ConvoHub - Stop"    stops it (its name follows the interface language; Persian: messages.py shortcut.stop_name)
Both use pythonw from the project's .venv and the ConvoHub icon.
"""

import base64
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import config, i18n
from .i18n import t, tp

ICON = config.ROOT_DIR / "convohub" / "static" / "icon.ico"


def _pythonw() -> Path:
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    if not candidate.exists():
        raise SystemExit(t("shortcut.no_pythonw", exe=exe))
    return candidate


def _ps_quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def stop_names() -> set[str]:
    """The stop shortcut's name in every language (to replace the old one after a language change)."""
    return {t("shortcut.stop_name", lang=lang) for lang in i18n.LANGS}


def create(desktop: Path | None = None) -> list[Path]:
    if sys.platform != "win32":
        raise SystemExit(tp("shortcut.windows_only"))
    pythonw = _pythonw()
    stop_name = t("shortcut.stop_name")
    # (final name, temporary ASCII name, arguments, description)
    items = [("ConvoHub", "convohub-open", "-m convohub", "Open ConvoHub"),
             (stop_name, "convohub-stop", "-m convohub --stop", "Stop ConvoHub")]
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
            raise SystemExit(t("shortcut.failed", error=out.stderr))
        desk = desktop or Path(out.stdout.strip().splitlines()[-1])
        made = []
        for name, temp_name, _, _ in items:
            src = Path(tmp) / f"{temp_name}.lnk"
            if not src.exists():
                raise SystemExit(t("shortcut.failed_one", name=name))
            dest = desk / f"{name}.lnk"
            shutil.copyfile(src, dest)  # copy, not move: the temp folder may be on another drive
            made.append(dest)
        # The stop shortcut made earlier in the other language would stay next to the new one: remove it.
        for old in stop_names() - {stop_name}:
            (desk / f"{old}.lnk").unlink(missing_ok=True)
    return made


if __name__ == "__main__":
    for p in create():
        print(t("shortcut.created", path=p))
