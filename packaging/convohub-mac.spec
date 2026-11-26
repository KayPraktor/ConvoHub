# PyInstaller spec for macOS (Apple Silicon): builds dist/ConvoHub.app with two programs in Contents/MacOS:
#   ConvoHub      the launcher/server (windowed: no Terminal window), from packaging/run_app.py
#   convohub-mcp  the MCP stdio server for Claude Code and others, from packaging/run_mcp.py
# Kept separate from convohub.spec so the Windows build can't break. Run it through packaging/build_mac.sh, which
# makes the icon first and then signs, checks and packs the app into a DMG.
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).parent
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
ICNS = ROOT / "build" / "ConvoHub.icns"  # made by build_mac.sh (tools/make_icon.py --icns)
if not ICNS.is_file():
    raise SystemExit(f"{ICNS} is missing: run packaging/build_mac.sh (or: uv run python tools/make_icon.py --icns {ICNS})")

datas = [
    (str(ROOT / "convohub" / "static"), "convohub/static"),
    # On macOS the browser extension ships inside the app (sys._MEIPASS/extension); the app copies it to the
    # data folder for Chrome's "Load unpacked". (On Windows the installer puts it next to ConvoHub.exe instead.)
    (str(ROOT / "extension"), "extension"),
    (str(ROOT / "LICENSE"), "."),
]
binaries = []
hiddenimports = collect_submodules("uvicorn") + collect_submodules("convohub")
# The CLIs of mcp/fastmcp aren't used (and exit on import without their optional deps): skip them.
_skip = lambda name: ".cli" not in name and ".tests" not in name and not name.endswith(".__main__")
for pkg in ("fastmcp", "mcp", "send2trash"):
    datas += collect_data_files(pkg)
    binaries += collect_dynamic_libs(pkg)
    hiddenimports += collect_submodules(pkg, filter=_skip)

common = dict(pathex=[str(ROOT)], binaries=binaries, datas=datas, hiddenimports=hiddenimports,
              excludes=["tkinter", "pytest", "IPython", "matplotlib", "numpy"], noarchive=False)

app_a = Analysis([str(ROOT / "packaging" / "run_app.py")], **common)
mcp_a = Analysis([str(ROOT / "packaging" / "run_mcp.py")], **common)

mac = dict(exclude_binaries=True, upx=False, target_arch="arm64", argv_emulation=False,
           codesign_identity=None, entitlements_file=None)  # None = ad-hoc signature (needed on Apple Silicon)
app_exe = EXE(PYZ(app_a.pure), app_a.scripts, [], name="ConvoHub", console=False, **mac)
mcp_exe = EXE(PYZ(mcp_a.pure), mcp_a.scripts, [], name="convohub-mcp", console=True, **mac)

# The first EXE in the COLLECT becomes CFBundleExecutable, so ConvoHub must come first.
coll = COLLECT(app_exe, app_a.binaries, app_a.datas,
               mcp_exe, mcp_a.binaries, mcp_a.datas,
               upx=False, name="ConvoHub")

app = BUNDLE(
    coll,
    name="ConvoHub.app",
    icon=str(ICNS),
    bundle_identifier="io.github.kaypraktor.convohub",
    version=VERSION,
    info_plist={
        "CFBundleName": "ConvoHub",
        "CFBundleDisplayName": "ConvoHub",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSUIElement": True,  # no Dock icon or menu bar: a background server with a browser interface
        # COLLECT takes "console" from its last EXE (convohub-mcp), which would make PyInstaller add
        # LSBackgroundOnly=True; the app is not background-only (it opens the browser), so say so.
        "LSBackgroundOnly": False,
        # Python from python-build-standalone (what uv installs) targets macOS 11 on arm64; 12 leaves headroom.
        "LSMinimumSystemVersion": "12.0",
        "LSArchitecturePriority": ["arm64"],
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "MIT License. https://github.com/KayPraktor/ConvoHub",
    },
)
