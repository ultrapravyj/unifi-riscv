#!/usr/bin/env python3
"""Pinned binary-first, resumable installer. No compiler invocation (MIT)."""
import argparse
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import shutil
import socket
import sys
import tempfile
import time
from urllib.parse import quote
import common
from common import ROOT, CONFIG, DATA, DB_DATA, LOG, DB_LOG, MANIFEST, run, output
from logging_config import configure

DEPENDENCIES = ['ca-certificates', 'curl', 'python3', 'python3-pymongo', 'openjdk-25-jre-headless',
                'libsnappy-java', 'libsnappy-jni', 'libsodium23', 'libjna-jni', 'libssl3t64',
                'libcurl4t64', 'libstdc++6', 'libgcc-s1', 'libsystemd0', 'libc-bin', 'tar']

def account(name, home):
    try:
        record = pwd.getpwnam(name)
        if record.pw_uid == 0:
            raise RuntimeError('Service account must not be root')
    except KeyError:
        run(['useradd', '--system', '--home-dir', home, '--shell', '/usr/sbin/nologin', name])

def owned_directory(path, owner, mode=0o750):
    path.mkdir(parents=True, exist_ok=True)
    record = pwd.getpwnam(owner)
    os.chown(path, record.pw_uid, record.pw_gid)
    path.chmod(mode)

def mongo_users():
    """Localhost exception bootstraps the first admin; subsequent runs authenticate."""
    from pymongo import MongoClient
    from pymongo.errors import OperationFailure
    path = CONFIG / 'mongo-credentials.json'
    if path.exists():
        credentials = json.loads(path.read_text())
    else:
        credentials = {'admin_user': 'unifi-riscv-admin', 'admin_password': secrets.token_hex(32),
                       'user': 'unifi', 'password': secrets.token_hex(32)}
        common.atomic_json(path, credentials)
    admin = MongoClient('127.0.0.1', 27017, username=credentials['admin_user'], password=credentials['admin_password'], authSource='admin', serverSelectionTimeoutMS=3000)
    for attempt in range(60):
        try:
            admin.admin.command('usersInfo', credentials['admin_user'])
            break
        except OperationFailure:
            unauthenticated = MongoClient('127.0.0.1', 27017, serverSelectionTimeoutMS=3000)
            try:
                unauthenticated.admin.command('createUser', credentials['admin_user'], pwd=credentials['admin_password'], roles=[{'role': 'root', 'db': 'admin'}])
            except OperationFailure:
                raise RuntimeError('Existing database credentials do not match; refusing to reset users or data.') from None
            finally:
                unauthenticated.close()
            admin.close()
            admin = MongoClient('127.0.0.1', 27017, username=credentials['admin_user'], password=credentials['admin_password'], authSource='admin', serverSelectionTimeoutMS=3000)
        except Exception:
            if attempt == 59:
                raise RuntimeError('Database startup failed; inspect database logs.') from None
            time.sleep(2)
    roles = [{'role': 'dbOwner', 'db': name} for name in ['unifi', 'unifi_stat', 'unifi_audit', 'local']]
    roles.append({'role': 'clusterMonitor', 'db': 'admin'})
    if not admin.admin.command('usersInfo', credentials['user'])['users']:
        admin.admin.command('createUser', credentials['user'], pwd=credentials['password'], roles=roles)
    admin.close()
    return credentials

def units(source):
    for name in ['mongod-riscv.service', 'unifi-riscv.service']:
        shutil.copy2(source / 'systemd' / name, Path('/etc/systemd/system') / name)
    run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'enable', 'mongod-riscv', 'unifi-riscv'])

def app(package, version, jni):
    directory = ROOT / 'app' / ('unifi-' + version)
    if not directory.is_dir():
        temporary = Path(tempfile.mkdtemp(prefix='unifi-', dir=ROOT / 'staging'))
        try:
            run(['dpkg-deb', '-x', package, temporary])
            original = temporary / 'usr/lib/unifi'
            if not (original / 'lib/ace.jar').is_file():
                raise RuntimeError('Official archive lacks ace.jar')
            shutil.move(original, directory)
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
    from manage import validate_jni
    validate_jni(directory)
    for name, target in [('data', DATA), ('logs', LOG), ('run', Path('/run/unifi'))]:
        link = directory / name
        if link.is_symlink():
            if link.resolve() != target:
                raise RuntimeError('Unexpected application symlink')
        elif link.exists():
            raise RuntimeError('Unexpected persistent directory in application binaries')
        else:
            link.symlink_to(target, target_is_directory=True)
    target = directory / 'lib/native/Linux/riscv64'
    target.mkdir(parents=True, exist_ok=True)
    target.chmod(0o755)
    shutil.copy2(jni, target / 'libubnt_sdnotify_jni.so')
    return directory

def package_requirements(package):
    fields = output(['dpkg-deb', '-f', package, 'Package', 'Architecture', 'Version', 'Depends'])
    if 'Package: unifi' not in fields or 'Architecture: all' not in fields or 'openjdk-25-' not in fields:
        raise RuntimeError('Unexpected official UniFi package metadata')
    requirements = re.findall(r'mongodb-org-server\s*\((>=|<<)\s*([^\s)]+)\)', fields)
    if not requirements:
        raise RuntimeError('Cannot verify MongoDB dependency range')
    for comparison, version in requirements:
        run(['dpkg', '--compare-versions', MANIFEST['mongodb']['version'], comparison, version])

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-base-url', help='Release mirror URL; hashes remain pinned (also useful for isolated tests)')
    parser.add_argument('--host', help='Advertised IP/DNS; no network configuration changes')
    parser.add_argument('--check', action='store_true', help='Only compatibility checks; no changes')
    args = parser.parse_args()
    common.preflight()
    if args.check:
        print('Compatible native riscv64 Debian 13 system with systemd and RV64GC.')
        return
    os.umask(0o077)
    import fcntl
    lock = open('/run/lock/unifi-riscv-install.lock', 'w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state_path = ROOT / 'state.json'
    if state_path.exists():
        state = json.loads(state_path.read_text())
        if state.get('schema') != 1:
            raise RuntimeError('Unknown installation state format')
        if args.host and args.host != state['host']:
            raise RuntimeError('Repeated install cannot change existing advertised host')
        if state['phase'] == 'ready':
            run(['systemctl', 'start', 'mongod-riscv'])
            common.database()
            run(['systemctl', 'start', 'unifi-riscv'])
            version = common.health(version=state['unifi_version'])
            print('Existing installation verified; data, settings and credentials preserved.')
            print('UniFi ' + version + ': https://' + state['host'] + ':8443/')
            print('Logs: /var/log/unifi/ and /var/log/unifi-mongodb/')
            return
    else:
        if DATA.exists() or DB_DATA.exists() or (CONFIG / 'mongo-credentials.json').exists() or (ROOT / 'app/current').exists():
            raise RuntimeError('Unmanaged/legacy installation detected. It was not modified; see migration documentation.')
        for port in [8443, 8080, 8880, 8843, 6789, 28082, 27017]:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                try:
                    probe.bind(('0.0.0.0', port))
                except OSError:
                    raise RuntimeError('Required port is already in use: ' + str(port)) from None
        ROOT.mkdir(parents=True, exist_ok=True)
        ROOT.chmod(0o755)
        state = {'schema': 1, 'installer_release': common.RELEASE, 'phase': 'preparing',
                 'host': common.address(args.host), 'unifi_version': MANIFEST['unifi']['version'],
                 'mongodb_version': MANIFEST['mongodb']['version']}
        common.atomic_json(state_path, state)
    for name in ['app', 'staging', 'cache', 'components', 'scripts', 'logs', 'backups']:
        (ROOT / name).mkdir(exist_ok=True)
    for name in ['app', 'components', 'scripts']:
        (ROOT / name).chmod(0o755)
    CONFIG.mkdir(parents=True, exist_ok=True)
    CONFIG.chmod(0o755)
    print('Installing native runtime dependencies...')
    run(['apt-get', 'update', '--error-on=any'])
    run(['apt-get', 'install', '-y', '--no-install-recommends', *DEPENDENCIES], env={**os.environ, 'DEBIAN_FRONTEND': 'noninteractive'})
    java = run(['/usr/lib/jvm/java-25-openjdk-riscv64/bin/java', '-version'], capture_output=True, text=True)
    if not re.search(r'version "25\.', java.stderr):
        raise RuntimeError('Native OpenJDK 25 is required')
    base = args.artifact_base_url or 'https://github.com/' + MANIFEST['repository'] + '/releases/download/' + common.RELEASE
    for component in ['mongodb', 'jni']:
        entry = MANIFEST[component]
        installed = ROOT / ('components/mongodb/bin/mongod' if component == 'mongodb' else 'components/jni/libubnt_sdnotify_jni.so')
        if installed.is_file() and common.digest(installed) == entry['binary_sha256']:
            # Interrupted install can already have a running MongoDB. Do not
            # truncate or replace its mapped executable on a resumable rerun.
            continue
        if installed.exists():
            raise RuntimeError('Existing component checksum differs; refusing to overwrite: ' + component)
        archive = common.fetch(base.rstrip('/') + '/' + entry['asset'], ROOT / 'cache' / entry['asset'], entry['sha256'])
        common.extract(archive, ROOT / 'components')
    mongo = ROOT / 'components/mongodb/bin/mongod'
    jni = ROOT / 'components/jni/libubnt_sdnotify_jni.so'
    common.check_binary(mongo, 'mongo')
    common.check_binary(jni, 'jni')
    if not (ROOT / 'mongodb').exists():
        (ROOT / 'mongodb').symlink_to(ROOT / 'components/mongodb', target_is_directory=True)
    package = common.fetch(MANIFEST['unifi']['url'], ROOT / 'cache' / ('unifi-' + state['unifi_version'] + '.deb'), MANIFEST['unifi']['sha256'])
    package_requirements(package)
    account('unifi', DATA)
    account('unifi-mongo', DB_DATA)
    for path in [DATA, LOG, Path('/var/cache/unifi'), Path('/run/unifi')]:
        owned_directory(path, 'unifi')
    for path in [DB_DATA, DB_LOG]:
        owned_directory(path, 'unifi-mongo')
    source = Path(__file__).parent.parent
    for filename in ['common.py', 'install.py', 'manage.py', 'logging_config.py']:
        shutil.copy2(source / 'runtime' / filename, ROOT / 'scripts' / filename)
    shutil.copy2(source / 'release.json', ROOT / 'release.json')
    shutil.copy2(source / 'runtime/run-unifi.sh', ROOT / 'scripts/run-unifi.sh')
    (ROOT / 'scripts/run-unifi.sh').chmod(0o755)
    if not (CONFIG / 'mongod.conf').exists():
        shutil.copy2(source / 'systemd/mongod.conf', CONFIG / 'mongod.conf')
    units(source)
    run(['systemctl', 'reset-failed', 'mongod-riscv', 'unifi-riscv'])
    run(['systemctl', 'start', 'mongod-riscv'])
    credentials = mongo_users()
    application = app(package, state['unifi_version'], jni)
    if not (DATA / 'system.properties').exists():
        uri = 'mongodb://' + quote(credentials['user'], safe='') + ':' + quote(credentials['password'], safe='') + '@127.0.0.1:27017/'
        properties = ['db.mongo.local=false', 'unifi.db.name=unifi', 'system_ip=' + state['host'],
                      'db.mongo.uri=' + uri + 'unifi?authSource=admin', 'statdb.mongo.uri=' + uri + 'unifi_stat?authSource=admin',
                      'unifi.http.port=8080', 'unifi.https.port=8443', 'unifi.stun.port=3478', 'unifi.discovery.port=10001']
        (DATA / 'system.properties').write_text('\n'.join(properties) + '\n')
        user = pwd.getpwnam('unifi')
        os.chown(DATA / 'system.properties', user.pw_uid, user.pw_gid)
        (DATA / 'system.properties').chmod(0o600)
    configure(application)
    common.switch(application)
    state['phase'] = 'configured'
    common.atomic_json(state_path, state)
    common.database()
    run(['systemctl', 'start', 'unifi-riscv'])
    common.health(version=state['unifi_version'])
    state['phase'] = 'ready'
    common.atomic_json(state_path, state)
    print('Ready: UniFi Network ' + state['unifi_version'])
    print('Open https://' + state['host'] + ':8443/ (initial self-signed certificate).')
    print('Logs: /var/log/unifi/ and /var/log/unifi-mongodb/')
    print('Manage: sudo python3 /opt/unifi-riscv/scripts/manage.py status|backup|update|rollback')

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Installation failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
