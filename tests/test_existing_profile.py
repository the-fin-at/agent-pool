"""Existing native profiles can be attached without copying or mutating credentials."""
import os
import tempfile
import unittest
from pathlib import Path
from agent_pool.store import Store


class ExistingNativeProfileTests(unittest.TestCase):
    def test_existing_native_directory_is_registered_without_copy_or_permission_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);native=root/'native';native.mkdir(mode=0o755)
            (native/'marker').write_text('existing state')
            mode=native.stat().st_mode
            store=Store(root/'pool')
            try:
                store.add_profile('server','codex','codex',auth_home=str(native))
                self.assertEqual(store.authdir('server'),native.resolve())
                self.assertEqual(native.stat().st_mode,mode)
                self.assertEqual((native/'marker').read_text(),'existing state')
                self.assertFalse((store.home/'profiles/server').exists())
                with self.assertRaisesRegex(ValueError,'already registered'):
                    store.add_profile('duplicate','codex','codex',auth_home=str(native))
            finally:store.close()

    def test_missing_attached_directory_is_not_silently_recreated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);native=root/'native';native.mkdir();store=Store(root/'pool')
            try:
                store.add_profile('server','codex','codex',auth_home=str(native))
                native.rmdir()
                with self.assertRaisesRegex(ValueError,'missing|changed'):store.authdir('server')
                self.assertFalse(native.exists())
            finally:store.close()

    @unittest.skipIf(os.name=='nt','POSIX symlink')
    def test_attached_directory_cannot_change_symlink_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);native=root/'native';native.mkdir();other=root/'other';other.mkdir();store=Store(root/'pool')
            try:
                store.add_profile('server','codex','codex',auth_home=str(native))
                native.rmdir();native.symlink_to(other,target_is_directory=True)
                with self.assertRaisesRegex(ValueError,'missing|changed'):store.authdir('server')
            finally:store.close()

    def test_missing_attached_account_does_not_break_the_entire_status_refresh(self):
        from agent_pool.monitor import collect
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);native=root/'native';native.mkdir();store=Store(root/'pool')
            store.add_profile('server','codex','codex',auth_home=str(native));store.close();native.rmdir()
            accounts=collect(root/'pool',include_default=False)
            self.assertEqual(len(accounts),1)
            self.assertIn('missing',accounts[0]['error'])
