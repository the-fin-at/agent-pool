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
archive = root / "dist/agent-fleet.pyz"
if not archive.is_file():
    parser.error("Build first: python scripts/build_zipapp.py")
names = ["agent-fleet", "agent-pool"]
binaries = [args.bin_dir / (name + ".pyz" if os.name == "nt" else name) for name in names]
skills = [(base / name, root / "skills" / name) for base in [args.codex_skills, args.claude_skills] for name in names]
for path in [*binaries, *(target for target, source in skills)]:
    if path.exists() or path.is_symlink():
        parser.error(f"Destination already exists; inspect it before updating: {path}")
args.bin_dir.mkdir(parents=True, exist_ok=True)
for binary in binaries:
    shutil.copy2(archive, binary)
    if os.name != "nt":
        binary.chmod(0o755)
    print(binary)
for target, source in skills:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    print(target)
