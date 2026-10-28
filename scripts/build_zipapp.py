"""Build a standalone Python zipapp with no pip/runtime dependencies."""
import shutil
import tempfile
import zipapp
from pathlib import Path

root = Path(__file__).resolve().parents[1]
output = root / "dist" / "agent-pool.pyz"
output.parent.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as folder:
    stage = Path(folder)
    shutil.copytree(root / "agent_pool", stage / "agent_pool", ignore=shutil.ignore_patterns("__pycache__"))
    zipapp.create_archive(stage, output, interpreter="/usr/bin/env python3", main="agent_pool.cli:main", compressed=True)
print(output)
