import ast
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'runtime'))
import legacy_update_hook as hook

class LegacyUpdaterTests(unittest.TestCase):
    def test_preserves_workflow_and_patches_before_downtime_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'scripts').mkdir()
            path = root/'scripts/update-unifi.py'
            original = "from pathlib import Path\nimport shutil, subprocess\nroot = Path('/opt/unifi-riscv')\nversion = '10.6.106'\ndestination = root / ('app/unifi-' + version)\nshutil.copytree(stage / 'usr/lib/unifi', destination, symlinks=True)\n" + hook.ANCHOR + '\n'
            path.write_text(original)
            self.assertTrue(hook.apply(root))
            updated = path.read_text()
            ast.parse(updated)
            self.assertLess(updated.index('probe_cloud(destination)'),updated.index(hook.ANCHOR))
            self.assertEqual(updated.replace(hook.HOOK + '\n',''),original)
            self.assertFalse(hook.apply(root))
            self.assertEqual(path.read_text(),updated)

    def test_unknown_user_updater_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'scripts').mkdir()
            path = root/'scripts/update-unifi.py'
            original = 'print("custom user updater")\n'
            path.write_text(original)
            with self.assertRaises(RuntimeError): hook.apply(root)
            self.assertEqual(path.read_text(),original)
