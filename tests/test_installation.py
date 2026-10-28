"""The distributable installer installs onboarding and refuses destructive replacement."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from scripts.build_zipapp import build_archive


class InstallationTests(unittest.TestCase):
    def test_fresh_install_includes_setup_skill_and_repeat_preserves_customizations(self):
        source=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);repo=root/'repo';(repo/'scripts').mkdir(parents=True)
            shutil.copy2(source/'scripts/install_local.py',repo/'scripts/install_local.py')
            shutil.copytree(source/'skills',repo/'skills')
            build_archive(repo/'dist/agent-fleet.pyz')
            codex=root/'codex-skills';claude=root/'claude-skills';bin_dir=root/'bin'
            argv=[sys.executable,str(repo/'scripts/install_local.py'),'--bin-dir',str(bin_dir),'--codex-skills',str(codex),'--claude-skills',str(claude)]
            done=subprocess.run(argv,capture_output=True,text=True,timeout=10)
            self.assertEqual(done.returncode,0,done.stderr)
            for base in [codex,claude]:
                self.assertTrue((base/'setup-agents-fleet/SKILL.md').is_file())
                self.assertTrue((base/'setup-agents-fleet/references/install.md').is_file())
            binary=bin_dir/('agent-fleet.pyz' if os.name=='nt' else 'agent-fleet')
            version=subprocess.run([sys.executable,str(binary),'--version'],capture_output=True,text=True,timeout=10)
            self.assertEqual(version.returncode,0,version.stderr)
            before=binary.read_bytes();custom=codex/'agent-fleet/SKILL.md'
            custom.write_text(custom.read_text()+'\n# Private customization\n')
            second=subprocess.run(argv,capture_output=True,text=True,timeout=10)
            self.assertNotEqual(second.returncode,0)
            self.assertEqual(binary.read_bytes(),before)
            self.assertIn('# Private customization',custom.read_text())
