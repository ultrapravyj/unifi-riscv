"""Meaningful non-root checks for release integrity and extraction boundaries."""
import hashlib
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
import common

class IntegrityTests(unittest.TestCase):
    def test_verified_cache_does_not_contact_network(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'component'
            file.write_bytes(b'verified release object')
            with patch('urllib.request.urlopen', side_effect=AssertionError('network called')):
                self.assertEqual(common.fetch('https://invalid.example/', file, common.digest(file)), file)

    def test_corrupt_download_never_becomes_installed_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'component'
            with patch('urllib.request.urlopen', side_effect=lambda *a, **k: io.BytesIO(b'tampered')), patch('time.sleep'):
                with self.assertRaises(RuntimeError):
                    common.fetch('https://invalid.example/', file, hashlib.sha256(b'original').hexdigest())
            self.assertFalse(file.exists())
            self.assertFalse(file.with_suffix('.partial').exists())

    def test_archive_traversal_and_symlink_are_rejected(self):
        for name, symlink in [('../escape', False), ('/absolute', False), ('file', True)]:
            with self.subTest(name=name, symlink=symlink), tempfile.TemporaryDirectory() as directory:
                archive = Path(directory) / 'bad.tar'
                with tarfile.open(archive, 'w') as tar:
                    member = tarfile.TarInfo(name)
                    if symlink:
                        member.type = tarfile.SYMTYPE
                        member.linkname = '/etc/shadow'
                    tar.addfile(member)
                with self.assertRaises(RuntimeError):
                    common.extract(archive, Path(directory) / 'out')

    def test_unexpected_architecture_binary_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'not-riscv'
            path.write_bytes(b'\x7fELF\x02\x01' + b'\0' * 58)
            with self.assertRaises(RuntimeError):
                common.check_binary(path, 'mongo')

    def test_implicit_archive_directories_remain_service_traversable(self):
        import os
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'component.tar'
            with tarfile.open(archive, 'w') as tar:
                member = tarfile.TarInfo('component/bin/tool')
                member.mode = 0o755
                member.size = 1
                tar.addfile(member, io.BytesIO(b'x'))
            previous = os.umask(0o077)
            try:
                common.extract(archive, Path(directory) / 'out')
            finally:
                os.umask(previous)
            self.assertEqual((Path(directory) / 'out/component/bin').stat().st_mode & 0o777, 0o755)

    def test_atomic_credentials_file_is_private(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'private.json'
            common.atomic_json(path, {'example': 'synthetic test data'})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

if __name__ == '__main__':
    unittest.main()
