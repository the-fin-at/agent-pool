"""Install built artifacts on this machine. Never replaces an existing installation."""
import argparse
import os
import shutil
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--bin-dir", type=Path, default=Path.home() / ".local/bin")
parser.add_argument("--codex-skills", type=Path, default=Path.home() / ".agents/skills")
parser.add_argument("--claude-skills", type=Path, default=Path.home() / ".claude/skills")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
archive = root / "dist/agent-pool.pyz"
if not archive.is_file():
    parser.error("Build first: python scripts/build_zipapp.py")
binary = args.bin_dir / ("agent-pool.pyz" if os.name == "nt" else "agent-pool")
targets = [binary, args.codex_skills / "agent-pool", args.claude_skills / "agent-pool"]
for path in targets:
    if path.exists() or path.is_symlink():
        parser.error(f"Destination already exists; inspect it before updating: {path}")
args.bin_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(archive, binary)
if os.name != "nt":
    binary.chmod(0o755)
print(binary)
for directory in targets[1:]:
    directory.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(root / "skills/agent-pool", directory)
    print(directory)
