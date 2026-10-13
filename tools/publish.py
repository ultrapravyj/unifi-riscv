#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Publish audited code/assets using the user's authenticated GitHub CLI account."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

def execute(args, check=True, capture=False, env=None):
    return subprocess.run(args, cwd=ROOT, check=check, capture_output=capture, text=True, encoding='utf-8', env=env)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', required=True)
    parser.add_argument('--gh', default='gh')
    parser.add_argument('--git', default='git')
    args = parser.parse_args()
    # gh repo operations invoke git themselves; portable tools need no global PATH edit.
    os.environ['PATH'] = str(Path(args.git).resolve().parent) + os.pathsep + str(Path(args.gh).resolve().parent) + os.pathsep + os.environ.get('PATH', '')
    os.environ['GIT_TERMINAL_PROMPT'] = '0'
    os.environ['GCM_INTERACTIVE'] = 'Never'
    user = execute([args.gh, 'api', 'user'], capture=True)
    account = json.loads(user.stdout)
    login = account['login']
    repository = login + '/unifi-riscv'
    # GitHub account authorization must precede substituting public URLs.
    for relative in ['README.md', 'docs/INSTALL-RU.md']:
        path = ROOT / relative
        text = path.read_text(encoding='utf-8').replace('YOUR_GITHUB_USERNAME', login)
        if relative == 'README.md' and 'The publication helper substitutes' in text:
            start = text.index('The publication helper substitutes')
            end = text.index('The bootstrap is version-pinned.')
            text = text[:start] + text[end:]
        elif relative != 'README.md' and 'При публикации служебный скрипт' in text:
            start = text.index('При публикации служебный скрипт')
            end = text.index('По желанию укажите адрес')
            text = text[:start] + text[end:]
        path.write_text(text, encoding='utf-8', newline='\n')
    execute([sys.executable, str(ROOT / 'tools/package-release.py'), '--input-dir', args.input_dir, '--repository', repository])
    execute([sys.executable, str(ROOT / 'tools/audit-public.py')])
    execute([args.git, 'status', '--short'])
    execute([args.git, 'diff', '--check'])
    execute([args.git, 'diff', '--stat'])
    execute([args.git, 'log', '--oneline', '-10'], check=False)
    # Never stage generated binaries, private data, credentials or ignored paths.
    execute([args.git, 'add', '.github', '.gitattributes', '.gitignore', 'LICENSE', 'README.md',
             'THIRD-PARTY.md', 'install.sh', 'release.json', 'runtime', 'systemd', 'native', 'patches',
             'build', 'docs', 'tests', 'tools'])
    execute([args.git, 'diff', '--cached', '--check'])
    execute([args.git, 'diff', '--cached', '--stat'])
    environment = dict(os.environ)
    environment.update({'GIT_AUTHOR_NAME': account.get('name') or login,
                        'GIT_AUTHOR_EMAIL': str(account['id']) + '+' + login + '@users.noreply.github.com',
                        'GIT_COMMITTER_NAME': account.get('name') or login,
                        'GIT_COMMITTER_EMAIL': str(account['id']) + '+' + login + '@users.noreply.github.com'})
    changes = execute([args.git, 'diff', '--cached', '--quiet'], check=False)
    if changes.returncode == 1:
        execute([args.git, 'commit', '-m', 'Add experimental binary-first UniFi installer for riscv64'], env=environment)
    exists = execute([args.gh, 'repo', 'view', repository, '--json', 'name'], check=False, capture=True)
    if exists.returncode != 0:
        execute([args.gh, 'repo', 'create', repository, '--public', '--description',
                 'Unofficial experimental binary-first UniFi Network installer for native riscv64 Debian 13',
                 '--source', str(ROOT), '--remote', 'origin'])
    else:
        # Do not overwrite a same-name repository belonging to user work.
        remote = execute([args.git, 'remote', 'get-url', 'origin'], check=False, capture=True)
        if remote.returncode != 0 or repository not in remote.stdout:
            raise RuntimeError('Repository already exists but this checkout has no matching origin; inspect before publishing.')
    # gh's credential helper is passed per invocation, never persisted to git config.
    helper = '!"' + args.gh.replace('\\', '/') + '" auth git-credential'
    execute([args.git, '-c', 'credential.https://github.com.helper=', '-c', 'credential.https://github.com.helper=' + helper, 'push', '-u', 'origin', 'main'], env=environment)
    tag = execute([args.git, 'rev-parse', '--verify', 'refs/tags/v0.1.0'], check=False, capture=True)
    if tag.returncode != 0:
        execute([args.git, 'tag', '-a', 'v0.1.0', '-m', 'Experimental riscv64 installer v0.1.0'], env=environment)
    execute([args.git, '-c', 'credential.https://github.com.helper=', '-c', 'credential.https://github.com.helper=' + helper, 'push', 'origin', 'v0.1.0'], env=environment)
    existing_release = execute([args.gh, 'release', 'view', 'v0.1.0', '--repo', repository], check=False, capture=True)
    if existing_release.returncode == 0:
        raise RuntimeError('Release v0.1.0 already exists; no assets were overwritten.')
    names = ['BUILD-INFO.json', 'install.sh', 'SHA256SUMS',
             'mongodb-7.0.43-debian13-riscv64.tar.gz',
             'mongodb-7.0.43-riscv64-corresponding-source.tar.gz',
             'unifi-riscv-installer-v0.1.0.tar.gz',
             'unifi-sdnotify-jni-debian13-riscv64-v0.1.0.tar.gz']
    assets = [str(ROOT / '.release' / name) for name in names]
    if not all(Path(path).is_file() for path in assets):
        raise RuntimeError('A required release asset is missing')
    execute([args.gh, 'release', 'create', 'v0.1.0', *assets, '--repo', repository,
             '--prerelease', '--verify-tag', '--title', 'v0.1.0 — experimental native riscv64 installer',
             '--notes-file', str(ROOT / 'docs/RELEASE-NOTES.md')])
    print('Repository: https://github.com/' + repository)
    print('Pre-release: https://github.com/' + repository + '/releases/tag/v0.1.0')
    print('Install: curl -fsSL https://github.com/' + repository + '/releases/download/v0.1.0/install.sh | sudo bash')

if __name__ == '__main__':
    main()
