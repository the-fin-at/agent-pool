"""Build a standalone Python zipapp with no pip/runtime dependencies."""
import shutil
import tempfile
import zipapp
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_archive(output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        stage = Path(folder)
        shutil.copytree(ROOT / 'agent_pool', stage / 'agent_pool', ignore=shutil.ignore_patterns('__pycache__'))
        (stage / '__main__.py').write_text('from agent_pool.cli import main\nraise SystemExit(main())\n')
        zipapp.create_archive(stage, output, interpreter='/usr/bin/env python3', compressed=True)
    return output


if __name__ == '__main__':
    output = build_archive(ROOT / 'dist/agent-fleet.pyz')
    shutil.copy2(output, output.with_name('agent-pool.pyz'))
    print(output)
