#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Audit source and allowlisted Release archives; no private data are required."""
from pathlib import Path
import hashlib
import io
import json
import re
import tarfile

ROOT = Path(__file__).resolve().parents[1]
patterns = [re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
            re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),
            re.compile(rb'github_pat_[A-Za-z0-9_]{40,}'),
            re.compile(rb'(?i)mongodb(?:\+srv)?://[^:\s/@]+:[^@\s]+@')]
# A literal real MongoDB credential URL is forbidden. Generic regex source and
# runtime string construction have no matching concrete user/password URL.
for path in ROOT.rglob('*'):
    if not path.is_file() or any(p in path.parts for p in ['.git', '.release', '.test-private', '__pycache__']):
        continue
    if path.name.startswith('.env') or path.suffix in ['.key', '.pem', '.wt', '.deb', '.har', '.unf']:
        raise SystemExit('Unexpected sensitive/binary source file: ' + str(path.relative_to(ROOT)))
    data = path.read_bytes()
    if any(pattern.search(data) for pattern in patterns):
        raise SystemExit('Sensitive literal found in: ' + str(path.relative_to(ROOT)))

release = ROOT / '.release'
for path in release.iterdir():
    if path.name.endswith('.tar.gz'):
        with tarfile.open(path) as archive:
            for member in archive.getmembers():
                name = Path(member.name)
                if name.is_absolute() or '..' in name.parts or not (member.isfile() or member.isdir()):
                    raise SystemExit('Unsafe release member')
                if name.suffix in ['.har', '.unf'] or any(part in ['.env', 'mongo-credentials.json', 'system.properties', 'backups', 'WiredTiger.wt'] for part in name.parts) or member.name.startswith(('var/lib/', 'var/log/', 'etc/netplan/')):
                    raise SystemExit('Private runtime member in public artifact')
                if member.isfile() and not member.name.endswith(('mongod', '.so', '.tar.gz')):
                    if any(pattern.search(archive.extractfile(member).read()) for pattern in patterns):
                        raise SystemExit('Sensitive literal in public archive metadata')
manifest = json.loads((ROOT / 'release.json').read_text())
for component in ['mongodb', 'jni']:
    file = release / manifest[component]['asset']
    with file.open('rb') as stream:
        checksum = hashlib.sha256()
        for block in iter(lambda: stream.read(1048576), b''):
            checksum.update(block)
        assert checksum.hexdigest() == manifest[component]['sha256']
assert (release / manifest['mongodb']['source_asset']).is_file()
if 'webrtc' in manifest:
    entry = manifest['webrtc']
    assert hashlib.sha256((release / entry['asset']).read_bytes()).hexdigest() == entry['sha256']
    assert hashlib.sha256((release / entry['source_asset']).read_bytes()).hexdigest() == entry['source_sha256']
    with tarfile.open(release / entry['asset']) as archive:
        for name, checksum in entry['files'].items():
            assert hashlib.sha256(archive.extractfile('webrtc/' + name).read()).hexdigest() == checksum
        assert archive.getmember('webrtc/licenses/usrsctp-LICENSE.md').isfile()
        for name in ['libubnt_webrtc_jni.so', 'libdatachannel.so.0.23']:
            header = archive.extractfile('webrtc/' + name).read(64)
            assert header[:6] == b'\x7fELF\x02\x01' and int.from_bytes(header[18:20], 'little') == 243
            assert int.from_bytes(header[48:52], 'little') & 6 == 4
    bootstrap = (ROOT / 'install.sh').read_text()
    bundle = re.search(r'^BUNDLE="([^"]+)"', bootstrap, re.M).group(1)
    checksum = re.search(r'^BUNDLE_SHA256="([^"]+)"', bootstrap, re.M).group(1)
    assert hashlib.sha256((release / bundle).read_bytes()).hexdigest() == checksum
    with tarfile.open(release / bundle) as archive:
        assert json.load(archive.extractfile('installer/release.json')) == manifest
        assert archive.getmember('installer/runtime/cloud.py').isfile()
print('Public source/archive audit: no private runtime data, credentials, tokens or keys detected; corresponding source and pinned checksums present.')
