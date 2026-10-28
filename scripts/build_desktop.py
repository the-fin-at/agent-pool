"""Build portable desktop archive and a native app on the current OS."""
import argparse
import shutil
import subprocess
import sys
import tempfile
import zipapp
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--portable-only", action="store_true", help="Build .pyzw; no PyInstaller needed")
args = parser.parse_args()
output = root / "dist"
output.mkdir(exist_ok=True)
portable = output / "Agent Pool.pyzw"
with tempfile.TemporaryDirectory() as folder:
    stage = Path(folder)
    shutil.copytree(root / "agent_pool", stage / "agent_pool", ignore=shutil.ignore_patterns("__pycache__"))
    zipapp.create_archive(stage, portable, interpreter="/usr/bin/env python3", main="agent_pool.desktop:main", compressed=True)
print(portable, flush=True)
if args.portable_only:
    raise SystemExit(0)
try:
    import PyInstaller
except ImportError:
    parser.error("Install the build dependency first: python -m pip install -r requirements-desktop-build.txt")
platform = "macos" if sys.platform == "darwin" else "windows" if sys.platform == "win32" else "linux"
with tempfile.TemporaryDirectory(prefix="agent-pool-desktop-build-") as work:
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--windowed", "--onedir",
               "--name", "Agent Pool", "--paths", str(root),
               "--distpath", str(output / platform), "--workpath", str(Path(work) / "work"),
               "--specpath", str(Path(work) / "spec"), "--log-level", "WARN"]
    if sys.platform == "darwin":
        command += ["--osx-bundle-identifier", "local.agentpool.desktop"]
    command.append(str(root / "scripts/desktop_entry.py"))
    subprocess.run(command, cwd=root, check=True)
app = output / platform / ("Agent Pool.app" if sys.platform == "darwin" else "Agent Pool")
if sys.platform == "darwin":
    archive = output / "Agent-Pool-macOS.zip"
    subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(archive)], check=True)
else:
    shutil.make_archive(str(output / ("Agent-Pool-" + platform)), "zip", app.parent, app.name)
print("Native app:", app)
