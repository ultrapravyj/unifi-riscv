#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native remote-transport deployment, legacy repair and secret-safe diagnostics."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import common
from common import ROOT, MANIFEST, run, output

FILES = ['libubnt_webrtc_jni.so', 'libdatachannel.so.0.23', 'NativeWebRTCProbe.class']
WEBRTC_ABI = [
    ('version', '(Z)Ljava/lang/String;'), ('activateInternalLogging', '(Z)V'),
    ('getErrorDescription', '(J)Ljava/lang/String;'),
    ('createWebRTC', '(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;I)J'),
    ('startCreateSDPOffer', '(J)J'), ('receiveSDPAnswer', '(JLjava/lang/String;J)J'),
    ('startCreateSDPAnswer', '(JLjava/lang/String;)J'), ('close', '(J)V'),
    ('createDataChannel', '(JLjava/lang/String;)J'), ('closeDataChannel', '(JJ)J'),
    ('sendData', '(JJ[BJJ)J'), ('sendFile', '(JJ[BIILjava/lang/String;JJ[BII)J'),
    ('cancelSendFile', '(JJ)V'), ('tearDownInternal', '()V'),
    ('mdnsResolved', '(JLjava/lang/String;Ljava/lang/String;)V'),
]

def component(base=None):
    entry = MANIFEST['webrtc']
    installed = ROOT / 'components/webrtc'
    if all((installed / name).is_file() and common.digest(installed / name) == entry['files'][name] for name in FILES):
        return installed
    base = base or 'https://github.com/' + MANIFEST['repository'] + '/releases/download/' + MANIFEST['release']
    archive = common.fetch(base.rstrip('/') + '/' + entry['asset'], ROOT / 'cache' / entry['asset'], entry['sha256'])
    (ROOT / 'staging').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='webrtc-', dir=ROOT / 'staging') as directory:
        common.extract(archive, directory)
        staged = Path(directory) / 'webrtc'
        for name in FILES:
            if common.digest(staged / name) != entry['files'][name]:
                raise RuntimeError('Native remote transport checksum mismatch')
        for name in FILES[:2]:
            common.check_binary(staged / name, 'jni')
        installed.mkdir(parents=True, exist_ok=True)
        installed.parent.chmod(0o755)
        installed.chmod(0o755)
        # Replace each component atomically, never truncate a mapped executable.
        for path in staged.rglob('*'):
            relative = path.relative_to(staged)
            target = installed / relative
            if path.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                target.chmod(0o755)
            elif path.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + '.new')
                shutil.copyfile(path, temporary)
                temporary.chmod(0o644)
                os.replace(temporary, target)
    return installed

def deploy(application, base=None):
    from manage import validate_native
    validate_native(application, 'com/ubnt/webrtc/WebRTCManager', WEBRTC_ABI)
    source = component(base)
    target = Path(application) / 'lib/native/Linux/riscv64'
    target.mkdir(parents=True, exist_ok=True)
    target.chmod(0o755)
    for name in FILES[:2]:
        if (target / name).is_file() and common.digest(target / name) == MANIFEST['webrtc']['files'][name]:
            continue
        temporary = target / (name + '.new')
        shutil.copyfile(source / name, temporary)
        temporary.chmod(0o644)
        os.replace(temporary, target / name)
    from migration_compat import apply
    return apply(application)

def probe(application, negative=False):
    source = ROOT / 'components/webrtc'
    library = Path(application) / 'lib/native/Linux/riscv64/libubnt_webrtc_jni.so'
    command = ['/usr/lib/jvm/java-25-openjdk-riscv64/bin/java', '--enable-native-access=ALL-UNNAMED',
               '-cp', str(source) + ':' + str(Path(application) / 'lib/internal/internal-dependencies.jar'),
               'NativeWebRTCProbe', str(library)]
    if negative:
        command.append('reject-fingerprint')
    result = subprocess.run(command, capture_output=True, text=True, timeout=100)
    if result.returncode != 0 or 'PASS:' not in result.stdout:
        raise RuntimeError('Native ICE/DTLS/SCTP self-test failed; no cloud readiness claim is possible')
    return result.stdout.strip()

def native_status(application=None):
    application = Path(application or ROOT / 'app/current').resolve()
    target = application / 'lib/native/Linux/riscv64'
    files = {name: (target / name).is_file() and common.digest(target / name) == MANIFEST['webrtc']['files'][name] for name in FILES[:2]}
    pid = output(['systemctl', 'show', 'unifi-riscv', '-p', 'MainPID', '--value'])
    maps = Path('/proc/' + pid + '/maps').read_text() if pid != '0' else ''
    return {'files_verified': files, 'loaded': {name: any(str(target / name) in line and '(deleted)' not in line for line in maps.splitlines()) for name in FILES[:2]}}

def check():
    """Report technical checks, never turn them into a claimed browser login."""
    report = {'native': native_status(), 'dashboard': 'requires browser verification',
              'time_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    from migration_compat import properties, SOURCE_VERSION
    migration = properties(ROOT / 'app/current/lib/ace.jar')
    report['backup_9_0_120_listed'] = SOURCE_VERSION in migration.get('migratable.versions','').split()
    report['route'] = json.loads(output(['ip', '-j', 'route', 'get', '1.1.1.1']))
    report['ipv6_default'] = output(['ip', '-6', 'route', 'show', 'default'])
    report['ntp_synchronized'] = output(['timedatectl', 'show', '-p', 'NTPSynchronized', '--value'])
    report['https'] = []
    for host in MANIFEST['webrtc']['https_endpoints']:
        record = {'host': host, 'port': 443}
        try:
            with socket.create_connection((host, 443), timeout=10) as raw:
                with ssl.create_default_context().wrap_socket(raw, server_hostname=host) as tls:
                    record.update(tls_verified=True, source=tls.getsockname()[0])
        except (OSError, ssl.SSLError) as error:
            record['error'] = type(error).__name__
        report['https'].append(record)
    # Only a projected registration record is read; no account/token values are emitted.
    from pymongo import MongoClient
    credentials = json.loads((common.CONFIG / 'mongo-credentials.json').read_text())
    with MongoClient('127.0.0.1', 27017, username=credentials['user'], password=credentials['password'], authSource='admin', serverSelectionTimeoutMS=5000) as client:
        registration = client.unifi.setting.find_one({'key': 'super_cloudaccess'},
            {'enabled': 1, 'x_certificate_pem': 1, 'x_private_key': 1}) or {}
        client.admin.command('ping')
        granted = {(r['role'], r['db']) for r in client.admin.command('connectionStatus')['authInfo']['authenticatedUserRoles']}
        from database_permissions import RESTORE_DATABASES, FSYNC_ROLE
        report['restore_database_permissions'] = {db: ('dbOwner', db) in granted for db in RESTORE_DATABASES}
        report['migration_fsync_permission'] = (FSYNC_ROLE, 'admin') in granted
    report['database_ping'] = True
    report['registration'] = {'enabled': registration.get('enabled') is True,
                              'certificate_present': bool(registration.get('x_certificate_pem')),
                              'key_present': bool(registration.get('x_private_key'))}
    host = MANIFEST['webrtc']['mqtt_endpoint']
    mqtt = {'host': host, 'port': 8883}
    if all(report['registration'].values()):
        try:
            context = ssl.create_default_context()
            with tempfile.TemporaryDirectory(prefix='unifi-cloud-tls-', dir='/run') as directory:
                cert, key = Path(directory) / 'cert.pem', Path(directory) / 'key.pem'
                for path, value in [(cert, registration['x_certificate_pem']), (key, registration['x_private_key'])]:
                    with path.open('w') as stream:
                        os.fchmod(stream.fileno(), 0o600)
                        stream.write(value)
                context.load_cert_chain(str(cert), str(key))
            with socket.create_connection((host, 8883), timeout=10) as raw:
                with context.wrap_socket(raw, server_hostname=host) as tls:
                    mqtt.update(tls_verified=True, client_certificate_used=True, source=tls.getsockname()[0])
        except (OSError, ssl.SSLError, ValueError, TypeError) as error:
            mqtt['error'] = type(error).__name__
    else:
        mqtt['status'] = 'awaiting user enrollment'
    report['mqtt'] = mqtt
    # Prefer actual recent session endpoints. Never print full native/JVM logs.
    journal = subprocess.run(['journalctl', '-u', 'unifi-riscv', '--since', '-30 minutes', '--no-pager', '-o', 'cat'], capture_output=True, text=True, timeout=30).stdout
    discovered = re.findall(r'riscv-webrtc: STUN endpoint=(stun:[A-Za-z0-9.:-]+)', journal)
    endpoint = discovered[-1] if discovered else MANIFEST['webrtc']['stun_endpoint']
    parsed = urllib.parse.urlsplit(endpoint.replace('stun:', 'stun://', 1))
    stun = {'host': parsed.hostname, 'port': parsed.port or 3478, 'protocol': 'UDP',
            'source_of_endpoint': 'recent session' if discovered else 'release validation'}
    try:
        tid = os.urandom(12)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.settimeout(8)
            udp.connect((stun['host'], stun['port']))
            udp.send(struct.pack('!HHI', 1, 0, 0x2112a442) + tid)
            data = udp.recv(4096)
            kind, length, cookie = struct.unpack('!HHI', data[:8])
            stun['binding_response_valid'] = kind == 0x101 and cookie == 0x2112a442 and data[8:20] == tid and len(data) >= length + 20
            stun['source'] = udp.getsockname()[0]
    except (OSError, ValueError, struct.error) as error:
        stun['error'] = type(error).__name__
    report['stun'] = stun
    report['recent_transport_events'] = {
        'ice_complete': journal.count('riscv-webrtc: ICE gathering complete;'),
        'relay_allocated': journal.count('ICE gathering complete; relay=yes'),
        'connected': journal.count('riscv-webrtc: transport state=2'),
        'failed_or_peer_disappeared': journal.count('riscv-webrtc: transport state=4')}
    report['note'] = 'A peer disappearing after its browser closes can produce a later ICE failure. STUN success alone does not verify TURN or remote pages.'
    print(json.dumps(report, indent=2))
    native_ok = all(report['native']['files_verified'].values()) and all(report['native']['loaded'].values())
    return native_ok and all(report['restore_database_permissions'].values()) and report['migration_fsync_permission'] and all(v.get('tls_verified', False) for v in report['https']) and 'error' not in mqtt and stun.get('binding_response_valid', False)

def repair(base=None):
    """Works with this project's legacy layout as well as schema-1 installations."""
    application = (ROOT / 'app/current').resolve(strict=True)
    if not (common.DATA / 'system.properties').is_file() or not (common.CONFIG / 'mongo-credentials.json').is_file():
        raise RuntimeError('Existing project configuration was not found; use the installer for a clean host')
    component(base)
    from database_permissions import ensure_restore_permissions
    added = ensure_restore_permissions()
    if added:
        print('Added scoped UniFi restore-database roles: ' + ', '.join(added))
    from manage import validate_native
    validate_native(application, 'com/ubnt/webrtc/WebRTCManager', WEBRTC_ABI)
    target = application / 'lib/native/Linux/riscv64'
    from migration_compat import needs_patch
    changed = needs_patch(application) or any(not (target / name).is_file() or common.digest(target / name) != MANIFEST['webrtc']['files'][name] for name in FILES[:2])
    if changed:
        backup = ROOT / 'backups' / ('cloud-native-' + str(time.time_ns()))
        backup.mkdir(parents=True, mode=0o700)
        present = []
        for name in FILES[:2]:
            if (target / name).exists():
                shutil.copy2(target / name, backup / name)
                present.append(name)
        run(['systemctl', 'stop', 'unifi-riscv'])
        jar_backup = None
        try:
            jar_backup = deploy(application, base)
            probe(application)
            run(['systemctl', 'start', 'unifi-riscv'])
            common.health()
        except Exception:
            run(['systemctl', 'stop', 'unifi-riscv'])
            if jar_backup:
                jar = application / 'lib/ace.jar'
                shutil.copyfile(jar_backup, jar.with_suffix('.jar.restore'))
                jar.with_suffix('.jar.restore').chmod(0o644)
                os.replace(jar.with_suffix('.jar.restore'), jar)
            for name in FILES[:2]:
                if name in present:
                    shutil.copy2(backup / name, target / (name + '.restore'))
                    os.replace(target / (name + '.restore'), target / name)
                else:
                    (target / name).unlink(missing_ok=True)
            run(['systemctl', 'start', 'unifi-riscv'])
            raise RuntimeError('Repair failed; previous native components and migration metadata restored') from None
    else:
        probe(application)
        if not all(native_status(application)['loaded'].values()):
            run(['systemctl', 'restart', 'unifi-riscv'])
            common.health()
    # Add network readiness without replacing the legacy service or its DB readiness hook.
    dropin = Path('/etc/systemd/system/unifi-riscv.service.d')
    dropin.mkdir(exist_ok=True)
    (dropin / 'cloud-network.conf').write_text('[Unit]\nWants=network-online.target\nAfter=network-online.target\n')
    (dropin / 'restore-restart.conf').write_text('[Service]\nRestart=always\n')
    run(['systemctl', 'daemon-reload'])
    source = Path(__file__).resolve().parent.parent
    script_source = Path(__file__).resolve().parent
    for name in ['common.py', 'cloud.py', 'manage.py', 'install.py', 'logging_config.py', 'database_permissions.py', 'migration_compat.py', 'legacy_update_hook.py']:
        destination = ROOT / 'scripts' / name
        if (script_source / name).resolve() != destination.resolve():
            shutil.copyfile(script_source / name, destination)
            destination.chmod(0o644)
    if (source / 'release.json').resolve() != (ROOT / 'release.json').resolve():
        shutil.copyfile(source / 'release.json', ROOT / 'release.json')
        (ROOT / 'release.json').chmod(0o644)
    common.database()
    common.health()
    from legacy_update_hook import apply as update_legacy_workflow
    update_legacy_workflow()
    state_path = ROOT / 'state.json'
    if state_path.is_file():
        state = json.loads(state_path.read_text())
        if state.get('schema') != 1:
            raise RuntimeError('Unknown installer state schema')
        state['installer_release'] = MANIFEST['release']
        common.atomic_json(state_path, state)
    print('Native remote transport repaired; MongoDB data and UniFi settings preserved.')
    print('Run cloud.py check, then verify dashboard and Networks through Site Manager in your browser.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'repair', 'probe'])
    parser.add_argument('--artifact-base-url')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError('Run with sudo')
    if args.command == 'check':
        return 0 if check() else 1
    if args.command == 'probe':
        print(probe(ROOT / 'app/current'))
        print(probe(ROOT / 'app/current', negative=True))
        return 0
    import fcntl
    with open('/run/lock/unifi-riscv-install.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        repair(args.artifact_base_url)
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        # No exception text: TLS/database exceptions can include private runtime state.
        print('Cloud operation failed (' + type(error).__name__ + '); inspect protected device diagnostics.', file=sys.stderr)
        sys.exit(1)
