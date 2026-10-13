#!/usr/bin/env python3
"""Status, authenticated readiness, cold backup, stable update and rollback (MIT)."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
import urllib.request
import common
from common import ROOT, CONFIG, MANIFEST, run, output
from logging_config import configure

API = 'https://fw-update.ubnt.com/api/firmware?filter=eq~~product~~unifi-controller&filter=eq~~channel~~release&sort=-version&limit=100'

def releases():
    with urllib.request.urlopen(API, timeout=60) as response:
        data = json.load(response)
    return [r for r in data['_embedded']['firmware'] if r['platform'] == 'debian' and r['channel'] == 'release']

def update(version=None, reinstall=False, readiness=common.health):
    """readiness is injectable only in integration tests of automatic rollback."""
    state = json.loads((ROOT / 'state.json').read_text())
    available = releases()
    if version:
        release = next((r for r in available if '.'.join(str(r[k]) for k in ['version_major', 'version_minor', 'version_patch']) == version), None)
        if not release:
            raise RuntimeError('Requested version is not in the official stable Debian release list')
    else:
        release = available[0]
    version = '.'.join(str(release[k]) for k in ['version_major', 'version_minor', 'version_patch'])
    if release['version_major'] < 10:
        raise RuntimeError('UniFi Network 10 or newer is required')
    if version == state['unifi_version'] and not reinstall:
        common.database()
        common.health(version=version)
        print('Already at official stable UniFi ' + version)
        return
    if output(['dpkg', '--compare-versions', version, 'ge', state['unifi_version']]) != '':
        raise RuntimeError('Unexpected version comparison output')
    package = common.fetch('https://dl.ui.com/unifi/' + version + '/unifi_sysvinit_all.deb', ROOT / 'cache' / ('unifi-' + version + '.deb'), release['sha256_checksum'])
    from install import package_requirements
    package_requirements(package)
    temporary = Path(tempfile.mkdtemp(prefix='update-', dir=ROOT / 'staging'))
    destination = ROOT / 'app' / ('unifi-' + version + '-' + str(time.time_ns()))
    try:
        run(['dpkg-deb', '-x', package, temporary])
        shutil.move(temporary / 'usr/lib/unifi', destination)
        validate_jni(destination)
        for name, target in [('data', common.DATA), ('logs', common.LOG), ('run', Path('/run/unifi'))]:
            path = destination / name
            if path.exists() or path.is_symlink():
                raise RuntimeError('Unexpected persistent path in official application')
            path.symlink_to(target, target_is_directory=True)
        jni = ROOT / 'components/jni/libubnt_sdnotify_jni.so'
        if common.digest(jni) != MANIFEST['jni']['binary_sha256']:
            raise RuntimeError('Installed notify binary checksum changed')
        native_directory = destination / 'lib/native/Linux/riscv64'
        native_directory.mkdir(parents=True, exist_ok=True)
        native_directory.chmod(0o755)
        shutil.copy2(jni, native_directory / jni.name)
        backup = common.cold_backup()
        common.atomic_json(ROOT / 'backups/latest.json', {'archive': str(backup)})
        try:
            configure(destination)
            common.switch(destination)
            run(['systemctl', 'start', 'mongod-riscv', 'unifi-riscv'])
            common.database()
            readiness(version=version)
            state['unifi_version'] = version
            state['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
            common.atomic_json(ROOT / 'state.json', state)
            print('UniFi ' + version + ' is ready. Cold backup: ' + str(backup))
        except Exception:
            common.restore(backup)
            print('Update failed; previous application, data and configuration restored.', file=sys.stderr)
            raise RuntimeError('Update rolled back; inspect application logs.') from None
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

def validate_jni(application):
    """Check the actual native declaration in Ubiquiti's class, not only text matches."""
    import struct
    import zipfile
    with zipfile.ZipFile(Path(application) / 'lib/internal/internal-dependencies.jar') as archive:
        data = archive.read('com/ubnt/sdnotify/SDNotify.class')
    cursor = 8
    count = struct.unpack_from('>H', data, cursor)[0]
    cursor += 2
    strings = {}
    index = 1
    while index < count:
        tag = data[cursor]
        cursor += 1
        if tag == 1:
            size = struct.unpack_from('>H', data, cursor)[0]
            cursor += 2
            strings[index] = data[cursor:cursor+size].decode('utf-8', errors='replace')
            cursor += size
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
            cursor += 4
        elif tag in (5, 6):
            cursor += 8
            index += 1
        elif tag in (7, 8, 16, 19, 20):
            cursor += 2
        elif tag == 15:
            cursor += 3
        else:
            raise RuntimeError('Unsupported class-file constant-pool tag')
        index += 1
    cursor += 6
    interfaces = struct.unpack_from('>H', data, cursor)[0]
    cursor += 2 + 2 * interfaces
    native = []
    for kind in ['fields', 'methods']:
        count = struct.unpack_from('>H', data, cursor)[0]
        cursor += 2
        for _ in range(count):
            flags, name, descriptor, attributes = struct.unpack_from('>HHHH', data, cursor)
            cursor += 8
            if kind == 'methods' and flags & 0x100:
                native.append((strings[name], strings[descriptor]))
            for _ in range(attributes):
                size = struct.unpack_from('>I', data, cursor + 2)[0]
                cursor += 6 + size
    if native != [('sdnotifyjni', '(ILjava/lang/String;)I')]:
        raise RuntimeError('The next release changed notify JNI ABI; review native support before updating')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['status', 'database-ready', 'backup', 'update', 'rollback'])
    parser.add_argument('--version', help='Official stable release version; default discovers newest stable')
    parser.add_argument('--reinstall', action='store_true', help='Reinstall the same official version using backup/update transaction')
    parser.add_argument('--archive', help='Private cold backup to restore; default last pre-update backup')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError('Run management commands with sudo')
    if args.command == 'database-ready':
        common.database(wait=180)
        print('Authenticated MongoDB ready')
        return
    if args.command == 'status':
        common.database()
        version = common.health(wait=10)
        run(['systemctl', 'show', *common.UNITS, '-p', 'ActiveState', '-p', 'SubState', '-p', 'NRestarts', '-p', 'MainPID'])
        print('Application-ready UniFi ' + version)
        return
    lock = open('/run/lock/unifi-riscv-install.lock', 'w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if args.command == 'backup':
        archive = common.cold_backup()
        run(['systemctl', 'start', 'mongod-riscv', 'unifi-riscv'])
        common.database()
        common.health()
        print('Private cold backup: ' + str(archive))
    elif args.command == 'update':
        update(args.version, args.reinstall)
    elif args.command == 'rollback':
        archive = args.archive or json.loads((ROOT / 'backups/latest.json').read_text())['archive']
        common.restore(archive)
        print('Previous application and private runtime state restored')

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Operation failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
