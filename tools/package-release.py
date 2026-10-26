"""Generate allowlisted, reproducible release artifacts and pinned public metadata."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tarfile

parser = argparse.ArgumentParser()
parser.add_argument('--repository', required=True)
parser.add_argument('--input-dir', help='Original v0.1.0 MongoDB/notify binary inputs')
parser.add_argument('--cloud-input-dir', help='Native WebRTC build output; reuses existing verified MongoDB/notify artifacts')
parser.add_argument('--version', default='v0.2.0', help='New cloud-capable installer release')
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
inputs = Path(args.input_dir).resolve() if args.input_dir else None
release = repo / '.release'
release.mkdir(exist_ok=True)
licenses = repo / 'licenses'
licenses.mkdir(exist_ok=True)
if not args.cloud_input_dir:
    if inputs is None:
        parser.error('--input-dir or --cloud-input-dir is required')
    for old, new in [('LICENSE-Community.txt', 'MongoDB-SSPL-1.0.txt'), ('MPL-2', 'MongoDB-MPL-2.0.txt'), ('THIRD-PARTY-NOTICES', 'MongoDB-THIRD-PARTY-NOTICES.txt')]:
        shutil.copyfile(inputs / old, licenses / new)
    (repo / 'patches').mkdir(exist_ok=True)
    for p in (inputs / 'patches').glob('00[1-5]-*.patch'):
        shutil.copyfile(p, repo / 'patches' / p.name)
    shutil.copyfile(inputs / 'mongo-python-requirements.txt', repo / 'build/python-requirements.txt')
    assert hashlib.sha256((inputs / 'mongo-r7.0.43.tar.gz').read_bytes()).hexdigest() == '00dd40bcd385103a5d98e342656e7444cdfadf34464c308206b804d9f5f47c75'

def hash_file(p):
    with Path(p).open('rb') as f:
        h = hashlib.sha256()
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
        return h.hexdigest()

def pack(name, files):
    destination = release / name
    with destination.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0) as gz, tarfile.open(fileobj=gz, mode='w|') as tar:
        for target, path, executable in sorted(files):
            data = Path(path).read_bytes()
            info = tarfile.TarInfo(target)
            info.size = len(data)
            info.mode = 0o755 if executable else 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = 'root'
            info.mtime = 0
            tar.addfile(info, io.BytesIO(data))
    return hash_file(destination)

if args.cloud_input_dir:
    cloud = Path(args.cloud_input_dir).resolve()
    manifest = json.loads((repo / 'release.json').read_text())
    # Database and notify artifacts are reused byte-for-byte, including corresponding source.
    for name in ['mongodb', 'jni']:
        entry = manifest[name]
        if hash_file(release / entry['asset']) != entry['sha256']:
            raise SystemExit('Existing verified component is missing or changed: ' + name)
    assert (release / manifest['mongodb']['source_asset']).is_file()
    version = args.version
    if not re.fullmatch(r'v\d+\.\d+\.\d+(?:-rc\.\d+)?', version):
        raise SystemExit('Invalid release version')
    manifest.update(release=version, repository=args.repository)
    manifest['unifi']['ace_jar_sha256'] = 'c35e782ba8b32c451e64357a1b3589adda6edba4e24585e533b8c755346f5fdc'
    manifest['unifi']['migration_metadata_extension'] = ['9.0.120']
    files = ['libubnt_webrtc_jni.so', 'libdatachannel.so.0.23', 'NativeWebRTCProbe.class']
    cloud_name = 'unifi-webrtc-debian13-riscv64-' + version + '.tar.gz'
    source_name = 'unifi-webrtc-corresponding-source-' + version + '.tar.gz'
    public_files = [('webrtc/' + name, cloud / name, False) for name in files]
    public_files += [('webrtc/licenses/' + p.name, p, False) for p in (cloud / 'licenses').iterdir() if p.is_file()]
    public_files += [('webrtc/BUILD-NOTICE.txt', cloud / 'BUILD-NOTICE.txt', False)]
    public_files += [('webrtc/source/' + p.name, p, False) for p in [repo / 'native/webrtc_jni.cpp', repo / 'tests/NativeWebRTCProbe.java']]
    public_files.append(('webrtc/LICENSE', repo / 'LICENSE', False))
    manifest['webrtc'] = {
        'asset': cloud_name, 'sha256': pack(cloud_name, public_files),
        'files': {name: hash_file(cloud / name) for name in files},
        'libdatachannel_version': '0.23.2',
        'source_commits': {'libdatachannel': '9e6a13abbb6846c003d817d0387b6706466e2b03',
                           'libjuice': 'b509b6c1f90e4a1d4753e6bde62ffbeb4d10c6bb',
                           'plog': '94899e0b926ac1b0f4750bfbd495167b4a6ae9ef',
                           'usrsctp': 'fec583d54493f879d2ae44a743423bf8a04371ab',
                           'json': '55f93686c01528224f448c19128836e7df245f72'},
        'validated_unifi': '10.6.106', 'source_asset': source_name,
        'https_endpoints': ['sso.ui.com', 'unifi.ui.com', 'account.ui.com'],
        'mqtt_endpoint': 'a1ewuiz2p7wdvw-ats.iot.us-west-2.amazonaws.com',
        'stun_endpoint': 'stun:stun.cloudflare.com:3478',
        'turn_endpoint': 'turn:turn.cloudflare.com:3478',
    }
    source_files = [('corresponding-source/upstream/' + p.name, p, False) for p in (cloud / 'source').glob('*.tar.gz')]
    source_files += [('corresponding-source/licenses/' + p.name, p, False) for p in (cloud / 'licenses').iterdir() if p.is_file()]
    source_files += [('corresponding-source/' + str(p.relative_to(repo)).replace('\\', '/'), p, p.suffix == '.sh') for p in [repo / 'native/webrtc_jni.cpp', repo / 'tests/NativeWebRTCProbe.java', repo / 'build/build-webrtc.sh', repo / 'LICENSE']]
    manifest['webrtc']['source_sha256'] = pack(source_name, source_files)
    (repo / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
    bundle_name = 'unifi-riscv-installer-' + version + '.tar.gz'
    bundle_files = [('installer/' + str(p.relative_to(repo)).replace('\\', '/'), p, p.suffix == '.sh') for folder in ['runtime', 'systemd', 'licenses'] for p in (repo / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    bundle_files += [('installer/' + p.name, p, False) for p in [repo / 'release.json', repo / 'LICENSE', repo / 'THIRD-PARTY.md']]
    bundle_hash = pack(bundle_name, bundle_files)
    bootstrap = (repo / 'install.sh').read_text()
    for key, value in {'REPOSITORY': args.repository, 'RELEASE': version, 'BUNDLE': bundle_name, 'BUNDLE_SHA256': bundle_hash}.items():
        bootstrap = re.sub(r'^' + key + r'="[^"]+"', key + '="' + value + '"', bootstrap, flags=re.M)
    (repo / 'install.sh').write_text(bootstrap, encoding='utf-8', newline='\n')
    shutil.copyfile(repo / 'install.sh', release / 'install.sh')
    shutil.copyfile(repo / 'release.json', release / 'BUILD-INFO.json')
    names = [manifest['mongodb']['asset'], manifest['mongodb']['source_asset'], manifest['jni']['asset'], cloud_name, source_name, bundle_name, 'install.sh', 'BUILD-INFO.json']
    (release / 'SHA256SUMS').write_text(''.join(hash_file(release / name) + '  ' + name + '\n' for name in sorted(names)), encoding='utf-8', newline='\n')
    print('Prepared ' + version + '; MongoDB/notify artifacts reused; cloud binary/source and installer pinned.')
    raise SystemExit(0)

mongo_name = 'mongodb-7.0.43-debian13-riscv64.tar.gz'
jni_name = 'unifi-sdnotify-jni-debian13-riscv64-v0.1.0.tar.gz'
mongo_hash = pack(mongo_name, [('mongodb/bin/mongod', inputs / 'mongod', True)] + [('mongodb/licenses/' + p.name, p, False) for p in licenses.iterdir() if p.is_file()] + [('mongodb/BUILD-NOTICE.md', repo / 'build/BUILD-NOTICE.md', False)])
jni_hash = pack(jni_name, [('jni/libubnt_sdnotify_jni.so', inputs / 'libubnt_sdnotify_jni.so', True), ('jni/source/ubnt_sdnotify_jni.c', repo / 'native/ubnt_sdnotify_jni.c', False), ('jni/LICENSE', repo / 'LICENSE', False)])
manifest = {
    'schema': 1, 'release': 'v0.1.0', 'repository': args.repository,
    'platform': {'os': 'Debian 13 Trixie', 'architecture': 'riscv64', 'endianness': 'little', 'abi': 'LP64D',
                 'isa_elf': 'rv64i2p1_m2p0_a2p1_f2p2_d2p2_c2p0_zicsr2p0_zifencei2p0_zmmul1p0_zaamo1p0_zalrsc1p0',
                 'isa_summary': 'RV64GC + Zicsr/Zifencei; Zmmul/Zaamo/Zalrsc are the M/A component subextensions',
                 'glibc_min': '2.38', 'glibcxx_min': '3.4.32', 'cxxabi_min': '1.3.15'},
    'unifi': {'version': '10.6.106', 'package_version': '10.6.106-36011-1', 'java_major': 25,
              'url': 'https://dl.ui.com/unifi/10.6.106/unifi_sysvinit_all.deb',
              'sha256': 'e93b70e73b9983c5e4d0a8ccc2d5d19b86db05e78f9a8c1850caf89ac069b240'},
    'mongodb': {'version': '7.0.43', 'asset': mongo_name, 'sha256': mongo_hash, 'binary_sha256': hash_file(inputs / 'mongod'),
                'build_id': 'ad9023cca36137ebe8a5513dbd442a28ca12523b', 'javascript_engine': 'none',
                'needed': ['libcurl.so.4', 'libresolv.so.2', 'libcrypto.so.3', 'libssl.so.3', 'libstdc++.so.6', 'libm.so.6', 'libgcc_s.so.1', 'libc.so.6', 'ld-linux-riscv64-lp64d.so.1'],
                'symbol_versions': {'GLIBC': '2.38', 'GLIBCXX': '3.4.32', 'CXXABI': '1.3.15', 'OPENSSL': '3.0.0', 'CURL_OPENSSL': '4'},
                'source_asset': 'mongodb-7.0.43-riscv64-corresponding-source.tar.gz', 'source_commit': '75b4e8457392dfd3ee501669e8a1835f4c08b654'},
    'jni': {'asset': jni_name, 'sha256': jni_hash, 'binary_sha256': hash_file(inputs / 'libubnt_sdnotify_jni.so'),
            'build_id': '4d367ca6934b4c23fa0999dd42b02343740c12a9', 'needed': ['libsystemd.so.0'], 'symbol_versions': {'LIBSYSTEMD': '209'}},
}
(repo / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
source_files = [('corresponding-source/upstream/mongo-r7.0.43.tar.gz', inputs / 'mongo-r7.0.43.tar.gz', False)]
for folder in ['patches', 'build', 'native', 'licenses']:
    source_files += [('corresponding-source/' + str(p.relative_to(repo)).replace('\\', '/'), p, p.suffix == '.sh') for p in (repo / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
source_files += [('corresponding-source/THIRD-PARTY.md', repo / 'THIRD-PARTY.md', False), ('corresponding-source/release.json', repo / 'release.json', False)]
pack(manifest['mongodb']['source_asset'], source_files)
bundle_files = [('installer/' + str(p.relative_to(repo)).replace('\\', '/'), p, p.suffix == '.sh') for folder in ['runtime', 'systemd', 'licenses'] for p in (repo / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
bundle_files += [('installer/' + p.name, p, False) for p in [repo / 'release.json', repo / 'LICENSE', repo / 'THIRD-PARTY.md']]
bundle_hash = pack('unifi-riscv-installer-v0.1.0.tar.gz', bundle_files)
bootstrap = (repo / 'install.sh').read_text()
bootstrap = re.sub(r'^REPOSITORY="[^"]+"', 'REPOSITORY="' + args.repository + '"', bootstrap, flags=re.M)
bootstrap = re.sub(r'^BUNDLE_SHA256="[^"]+"', 'BUNDLE_SHA256="' + bundle_hash + '"', bootstrap, flags=re.M)
(repo / 'install.sh').write_text(bootstrap, encoding='utf-8', newline='\n')
shutil.copyfile(repo / 'install.sh', release / 'install.sh')
shutil.copyfile(repo / 'release.json', release / 'BUILD-INFO.json')
assets = sorted(p for p in release.iterdir() if p.is_file() and p.name not in ['SHA256SUMS', 'PUBLICATION.json'])
(release / 'SHA256SUMS').write_text(''.join(hash_file(p) + '  ' + p.name + '\n' for p in assets), encoding='utf-8', newline='\n')
print('Release artifacts generated without runtime data:')
for p in assets:
    print(p.name + ': ' + str(p.stat().st_size) + ' bytes, sha256=' + hash_file(p))
