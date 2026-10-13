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
parser.add_argument('--input-dir', required=True, help='Allowlisted binary/source input directory; never an application data directory')
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
inputs = Path(args.input_dir).resolve()
release = repo / '.release'
release.mkdir(exist_ok=True)
licenses = repo / 'licenses'
licenses.mkdir(exist_ok=True)
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
