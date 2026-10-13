# Publish the fully prepared release

Publication uses the user's authenticated **GitHub CLI (`gh`)** account. A browser
login alone is not `gh` authorization. Never paste a token into repository files.

```sh
gh auth login --hostname github.com --git-protocol https --web
python tools/publish.py --input-dir PATH_TO_ALLOWLISTED_RELEASE_INPUTS
```

For portable Windows tools, pass `--gh PATH_TO_GH_EXE --git PATH_TO_GIT_EXE`.

The input directory contains only `mongod`, `libubnt_sdnotify_jni.so`, the original
`mongo-r7.0.43.tar.gz`, `mongo-python-requirements.txt`, upstream license/notice files
and the five applied patches in its `patches/` subdirectory. It is **not** an app
data directory or backup directory. On the original development workstation these
allowlisted inputs were cached outside the public repository in:

```text
%LOCALAPPDATA%\Temp\opencode\unifi-release-inputs
```

The publication helper:

1. Obtains the authorized GitHub account via `gh api user`.
2. Substitutes that account in the README/install URLs and manifest.
3. Repackages deterministic native/source/installer assets and checksum pins.
4. Audits public files and archives, inspects git status/diff/log, and stages only
   intended source/documentation files. Release binaries stay in ignored `.release/`.
5. Commits with the account's public name and GitHub noreply address without
   changing global git configuration.
6. Creates public `ACCOUNT/unifi-riscv`, pushes main and annotated `v0.1.0`.
7. Creates **v0.1.0 as a Pre-release** with the prepared assets and source archive.
8. Prints the real repository, Release and one-command installation URLs.

It refuses to overwrite a pre-existing same-name unrelated repository or an
existing v0.1.0 Release. Inspect errors and retry deliberately; it does not
force-push, skip hooks or replace existing Release assets.

The prepared pre-publication installer supports the exact local assets through
`--artifact-base-url`; its default public URL remains UNPUBLISHED until the
authenticated publisher assigns the real account. There is no claim that an
unpublished GitHub repository/Release already exists.
