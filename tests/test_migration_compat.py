"""Check metadata-only modification, tamper rejection and version boundaries."""
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'runtime'))
import common
import migration_compat

class MigrationCompatibilityTests(unittest.TestCase):
    def fixture(self, root, version='10.6.106'):
        path = Path(root) / 'ace.jar'
        with zipfile.ZipFile(path,'w') as jar:
            jar.writestr('product.properties','version=' + version + '\nmigratable.versions=9.0.[67-114] 9.0.118\n')
            jar.writestr('Authentication.class',b'opaque unchanged vendor class fixture')
        return path

    def test_only_metadata_changes_and_repeat_is_noop(self):
        with tempfile.TemporaryDirectory() as root:
            jar = self.fixture(root)
            backup = migration_compat.patch_archive(jar,Path(root)/'backups',common.digest(jar))
            with zipfile.ZipFile(jar) as result, zipfile.ZipFile(backup) as before:
                self.assertEqual(result.read('Authentication.class'),before.read('Authentication.class'))
                self.assertEqual(migration_compat.properties(jar)['version'],'10.6.106')
                self.assertIn('9.0.120',migration_compat.properties(jar)['migratable.versions'].split())
            checksum = common.digest(jar)
            self.assertIsNone(migration_compat.patch_archive(jar,Path(root)/'backups'))
            self.assertEqual(common.digest(jar),checksum)

    def test_unknown_archive_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            jar = self.fixture(root)
            checksum = common.digest(jar)
            with self.assertRaises(RuntimeError):
                migration_compat.patch_archive(jar,Path(root)/'backups')
            self.assertEqual(common.digest(jar),checksum)

    def test_other_application_version_is_not_modified(self):
        with tempfile.TemporaryDirectory() as root:
            jar = self.fixture(root,'10.7.0')
            checksum = common.digest(jar)
            self.assertIsNone(migration_compat.patch_archive(jar,Path(root)/'backups',checksum))
            self.assertEqual(common.digest(jar),checksum)
