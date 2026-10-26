"""Shared installation, integrity, readiness and cold-backup primitives (MIT)."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import ssl
import subprocess
import tarfile
import tempfile
import time
import urllib.request

ROOT = Path('/opt/unifi-riscv')
CONFIG = Path('/etc/unifi-riscv')
DATA = Path('/var/lib/unifi')
DB_DATA = Path('/var/lib/unifi-mongodb')
LOG = Path('/var/log/unifi')
DB_LOG = Path('/var/log/unifi-mongodb')
UNITS = ['unifi-riscv.service', 'mongod-riscv.service']
MANIFEST = json.loads((Path(__file__).parent.parent / 'release.json').read_text())
RELEASE = MANIFEST['release']

def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)

def output(args):
    return subprocess.check_output([str(a) for a in args], text=True).strip()

def atomic_json(path, data, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.new')
    with temporary.open('w') as stream:
        os.fchmod(stream.fileno(), mode)
        json.dump(data, stream, indent=2)
        stream.write('\n')
    os.replace(temporary, path)

def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def fetch(url, destination, expected):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and digest(destination) == expected:
        return destination
    temporary = destination.with_suffix(destination.suffix + '.partial')
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=90) as response, temporary.open('wb') as stream:
                shutil.copyfileobj(response, stream)
            if digest(temporary) != expected:
                raise RuntimeError('SHA256 mismatch for ' + destination.name)
            os.replace(temporary, destination)
            return destination
        except Exception:
            temporary.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(3)

def extract(archive, directory):
    """Only regular files/directories in release archives; no traversal or links."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        for member in members:
            path = Path(member.name)
            if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
                raise RuntimeError('Unsafe archive member')
        tar.extractall(directory, members=members, filter='data')
    # Archives may omit directory headers; parents created under umask 077 must
    # remain traversable by non-root service accounts. This tree is binaries only.
    for path, directories, files in os.walk(directory):
        Path(path).chmod(0o755)

def preflight():
    if os.geteuid() != 0:
        raise RuntimeError('Run this installer as root (sudo).')
    if output(['uname', '-m']) != 'riscv64' or output(['dpkg', '--print-architecture']) != 'riscv64':
        raise RuntimeError('Only native riscv64 / Debian riscv64 is supported.')
    os_release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if os_release.get('ID', '').strip('"') != 'debian' or os_release.get('VERSION_ID', '').strip('"') != '13':
        raise RuntimeError('v0.1.0 supports Debian 13 Trixie, including Debian-based Armbian 13.')
    if not Path('/run/systemd/system').is_dir():
        raise RuntimeError('A running systemd system is required.')
    if tuple(int(v) for v in output(['getconf', 'GNU_LIBC_VERSION']).split()[-1].split('.')) < (2, 38):
        raise RuntimeError('glibc >= 2.38 is required.')
    # Linux RISC-V AT_HWCAP letter bits are authoritative for base ISA extensions.
    import ctypes
    libc = ctypes.CDLL(None)
    libc.getauxval.argtypes = [ctypes.c_ulong]
    libc.getauxval.restype = ctypes.c_ulong
    hwcap = libc.getauxval(16)
    if not all(hwcap & (1 << (ord(letter) - ord('a'))) for letter in 'imafdc'):
        raise RuntimeError('RV64GC (I/M/A/F/D/C, LP64D) is required.')
    cpuinfo = Path('/proc/cpuinfo').read_text().lower()
    isa = re.findall(r'^isa\s*:\s*(\S+)', cpuinfo, flags=re.M)
    if isa and not all(('zicsr' in value and 'zifencei' in value) or value.startswith('rv64g') for value in isa):
        raise RuntimeError('Published binaries additionally require Zicsr and Zifencei.')
    if shutil.disk_usage('/opt').free < 3 * 1024**3:
        raise RuntimeError('At least 3 GiB free storage is required for installation/staging.')
    # Zicsr and Zifencei are recorded ELF requirements of the published artifacts.
    # Hardware support is additionally exercised by the native binary smoke check.

def check_binary(path, mode):
    with Path(path).open('rb') as stream:
        header = stream.read(64)
    if header[:6] != b'\x7fELF\x02\x01' or int.from_bytes(header[18:20], 'little') != 243:
        raise RuntimeError('Expected little-endian ELF64 RISC-V binary: ' + str(path))
    if int.from_bytes(header[48:52], 'little') & 6 != 4:
        raise RuntimeError('LP64D double-float ABI is required')
    result = run(['ldd', path], capture_output=True, text=True)
    if 'not found' in result.stdout + result.stderr:
        raise RuntimeError('Missing runtime library for ' + str(path))
    if mode == 'mongo':
        if 'db version v' + MANIFEST['mongodb']['version'] not in output([path, '--version']):
            raise RuntimeError('Unexpected MongoDB binary version')
    else:
        import ctypes
        ctypes.CDLL(str(path))

def address(explicit=None):
    if explicit:
        host = explicit
    elif os.environ.get('SSH_CONNECTION'):
        host = os.environ['SSH_CONNECTION'].split()[2]
    else:
        candidates = output(['hostname', '-I']).split()
        host = next((v for v in candidates if ':' not in v and not v.startswith('127.')), None)
        if not host:
            raise RuntimeError('Cannot determine advertised host; pass --host IP_OR_DNS.')
    if not re.fullmatch(r'[A-Za-z0-9_.:-]+', host):
        raise RuntimeError('Invalid host/IP value')
    return host

def health(wait=600, version=None):
    deadline = time.monotonic() + wait
    while True:
        try:
            with urllib.request.urlopen('https://127.0.0.1:8443/status', context=ssl._create_unverified_context(), timeout=10) as response:
                status = json.load(response)
            if status.get('meta', {}).get('up') is True and (version is None or status['meta'].get('server_version') == version):
                for unit in UNITS:
                    if output(['systemctl', 'is-active', unit]) != 'active':
                        raise RuntimeError('Service is not active')
                return status['meta']['server_version']
        except Exception:
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError('Controller not ready; inspect /var/log/unifi and journalctl -u unifi-riscv.')
        time.sleep(5)

def database(wait=120):
    from pymongo import MongoClient
    credentials = json.loads((CONFIG / 'mongo-credentials.json').read_text())
    deadline = time.monotonic() + wait
    while True:
        try:
            client = MongoClient('127.0.0.1', 27017, username=credentials['user'], password=credentials['password'], authSource='admin', serverSelectionTimeoutMS=3000)
            client.admin.command('ping')
            client.close()
            return
        except Exception:
            if time.monotonic() >= deadline:
                raise RuntimeError('Authenticated database readiness failed') from None
            time.sleep(2)

def cold_backup():
    """Capture whole private runtime state; never ship this archive in a release."""
    directory = ROOT / 'backups'
    directory.mkdir(mode=0o700, exist_ok=True)
    directory.chmod(0o700)
    destination = directory / (time.strftime('backup-%Y%m%dT%H%M%S-') + str(time.time_ns()) + '.tar.gz')
    previous = (ROOT / 'app/current').resolve()
    run(['systemctl', 'stop', *UNITS])
    try:
        run(['tar', '-czf', destination, '-C', '/', 'var/lib/unifi', 'var/lib/unifi-mongodb', 'etc/unifi-riscv', 'opt/unifi-riscv/state.json'])
        destination.chmod(0o600)
        atomic_json(destination.with_suffix('.json'), {'sha256': digest(destination), 'previous_app': str(previous), 'archive': destination.name})
    except Exception:
        destination.unlink(missing_ok=True)
        run(['systemctl', 'start', 'mongod-riscv', 'unifi-riscv'])
        raise
    return destination

def restore(archive):
    """Validate and stage a cold backup before changing any current data."""
    archive = Path(archive).resolve()
    metadata = json.loads(archive.with_suffix('.json').read_text())
    if digest(archive) != metadata['sha256']:
        raise RuntimeError('Backup checksum mismatch')
    previous = Path(metadata['previous_app'])
    if not previous.is_relative_to(ROOT / 'app') or not (previous / 'lib/ace.jar').exists():
        raise RuntimeError('Previous application binaries are not retained')
    temporary = Path(tempfile.mkdtemp(prefix='restore-', dir=ROOT / 'staging'))
    try:
        # Private backups contain application symlinks; use tar's data filter,
        # and validate every destination lies below these known directory roots.
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                if not member.name.startswith(('var/lib/unifi/', 'var/lib/unifi-mongodb/', 'etc/unifi-riscv/', 'opt/unifi-riscv/state.json')) and member.name not in ['var/lib/unifi', 'var/lib/unifi-mongodb', 'etc/unifi-riscv']:
                    raise RuntimeError('Unexpected backup content')
            tar.extractall(temporary, filter='data')
        if not (temporary / 'var/lib/unifi/system.properties').is_file():
            raise RuntimeError('Backup lacks application configuration')
        import pwd
        for path, user in [('var/lib/unifi', 'unifi'), ('var/lib/unifi-mongodb', 'unifi-mongo')]:
            record = pwd.getpwnam(user)
            for directory, subdirectories, files in os.walk(temporary / path):
                os.chown(directory, record.pw_uid, record.pw_gid)
                for name in files + subdirectories:
                    os.chown(Path(directory) / name, record.pw_uid, record.pw_gid, follow_symlinks=False)
        (temporary / 'etc/unifi-riscv/mongo-credentials.json').chmod(0o600)
        run(['systemctl', 'stop', *UNITS])
        displaced = ROOT / 'backups' / ('displaced-' + str(time.time_ns()))
        displaced.mkdir(mode=0o700)
        for current in [DATA, DB_DATA, CONFIG]:
            shutil.move(current, displaced / current.name)
            shutil.move(str(temporary / str(current).lstrip('/')), current)
        shutil.copy2(temporary / 'opt/unifi-riscv/state.json', ROOT / 'state.json')
        switch(previous)
        run(['systemctl', 'start', 'mongod-riscv', 'unifi-riscv'])
        database()
        health()
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

def switch(application):
    link = ROOT / 'app/current.next'
    link.unlink(missing_ok=True)
    link.symlink_to(application, target_is_directory=True)
    os.replace(link, ROOT / 'app/current')
