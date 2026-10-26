"""Keep the original project's updater while adding pre-activation cloud support."""
import ast
import os
from pathlib import Path
import shutil
import time

MARKER = '# unifi-riscv native cloud pre-activation hook'
ANCHOR = "subprocess.run(['systemctl', 'stop', 'unifi-riscv', 'mongod-riscv'], check=True)"
HOOK = MARKER + '''
import sys
sys.path.insert(0, str(root / 'scripts'))
from cloud import deploy as deploy_cloud, probe as probe_cloud
deploy_cloud(destination)
probe_cloud(destination)
'''

def apply(root=Path('/opt/unifi-riscv')):
    root = Path(root)
    path = root / 'scripts/update-unifi.py'
    if not path.is_file():
        return False
    text = path.read_text()
    if MARKER in text:
        return False
    required = ["root = Path('/opt/unifi-riscv')", "destination = root / ('app/unifi-' + version)",
                "shutil.copytree(stage / 'usr/lib/unifi', destination, symlinks=True)"]
    if text.count(ANCHOR) != 1 or not all(value in text for value in required):
        raise RuntimeError('Unknown legacy updater layout; original updater was not modified')
    updated = text.replace(ANCHOR, HOOK + '\n' + ANCHOR)
    ast.parse(updated)
    backups = root / 'backups/legacy-updater'
    backups.mkdir(parents=True, exist_ok=True)
    backups.chmod(0o700)
    backup = backups / ('update-unifi-' + str(time.time_ns()) + '.py')
    shutil.copyfile(path, backup)
    backup.chmod(0o600)
    temporary = path.with_suffix('.py.cloud-new')
    temporary.write_text(updated)
    temporary.chmod(path.stat().st_mode & 0o777)
    os.replace(temporary,path)
    return True
