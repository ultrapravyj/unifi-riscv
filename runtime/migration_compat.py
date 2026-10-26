"""Validated, version-pinned migration-metadata correction; no Java/auth changes."""
from pathlib import Path
import os
import shutil
import time
import zipfile
import common

SOURCE_VERSION = '9.0.120'
TARGET_VERSION = '10.6.106'
ACE_SHA256 = 'c35e782ba8b32c451e64357a1b3589adda6edba4e24585e533b8c755346f5fdc'

def properties(archive):
    with zipfile.ZipFile(archive) as jar:
        text = jar.read('product.properties').decode('utf-8')
    return dict(line.split('=',1) for line in text.splitlines() if '=' in line and not line.startswith('#'))

def needs_patch(application):
    data = properties(Path(application) / 'lib/ace.jar')
    return data.get('version') == TARGET_VERSION and SOURCE_VERSION not in data.get('migratable.versions','').split()

def patch_archive(archive, backup_directory, expected=ACE_SHA256):
    archive = Path(archive)
    data = properties(archive)
    if data.get('version') != TARGET_VERSION or SOURCE_VERSION in data.get('migratable.versions','').split():
        return None
    if common.digest(archive) != expected:
        raise RuntimeError('Unknown ace.jar content; refusing migration-metadata modification')
    backup_directory = Path(backup_directory)
    backup_directory.mkdir(parents=True, exist_ok=True)
    backup_directory.chmod(0o700)
    backup = backup_directory / ('ace-before-migration-compat-' + str(time.time_ns()) + '.jar')
    shutil.copyfile(archive, backup)
    backup.chmod(0o600)
    temporary = archive.with_name(archive.name + '.compat-new')
    try:
        with zipfile.ZipFile(archive) as before, zipfile.ZipFile(temporary,'w') as after:
            for member in before.infolist():
                content = before.read(member.filename)
                if member.filename == 'product.properties':
                    lines = content.decode('utf-8').splitlines()
                    found = False
                    for i,line in enumerate(lines):
                        if line.startswith('migratable.versions='):
                            lines[i] = line + ' ' + SOURCE_VERSION
                            found = True
                    if not found:
                        raise RuntimeError('Migration resource format changed')
                    content = ('\n'.join(lines) + '\n').encode('utf-8')
                after.writestr(member,content)
        with zipfile.ZipFile(backup) as before, zipfile.ZipFile(temporary) as after:
            if before.namelist() != after.namelist() or any(before.read(name) != after.read(name) for name in before.namelist() if name != 'product.properties'):
                raise RuntimeError('Unexpected change outside migration metadata')
        temporary.chmod(0o644)
        os.replace(temporary,archive)
        return backup
    finally:
        temporary.unlink(missing_ok=True)

def apply(application):
    return patch_archive(Path(application) / 'lib/ace.jar', common.ROOT / 'backups/migration-metadata')
