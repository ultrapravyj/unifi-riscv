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
    if path.name.startswith('.env') or path.suffix in ['.key', '.pem', '.wt', '.deb']:
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
                if any(part in ['.env', 'mongo-credentials.json', 'system.properties', 'backups', 'WiredTiger.wt'] for part in name.parts) or member.name.startswith(('var/lib/', 'var/log/', 'etc/netplan/')):
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
print('Public source/archive audit: no private runtime data, credentials, tokens or keys detected; corresponding source and pinned checksums present.')
