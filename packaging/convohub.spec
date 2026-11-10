# PyInstaller spec: builds dist/ConvoHub/ with ConvoHub.exe (windowed) and convohub-mcp.exe (console, for MCP
# stdio) sharing one _internal folder. Run from the project root: uv run --group build pyinstaller packaging/convohub.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).parent
ICON = str(ROOT / "convohub" / "static" / "icon.ico")

datas = [(str(ROOT / "convohub" / "static"), "convohub/static")]
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

app_exe = EXE(PYZ(app_a.pure), app_a.scripts, [], exclude_binaries=True, name="ConvoHub",
              console=False, icon=ICON, upx=False)
mcp_exe = EXE(PYZ(mcp_a.pure), mcp_a.scripts, [], exclude_binaries=True, name="convohub-mcp",
              console=True, icon=ICON, upx=False)

coll = COLLECT(app_exe, app_a.binaries, app_a.datas,
               mcp_exe, mcp_a.binaries, mcp_a.datas,
               upx=False, name="ConvoHub")
