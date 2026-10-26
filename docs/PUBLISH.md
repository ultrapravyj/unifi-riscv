# Publish the fully prepared release

Publication uses the user's authenticated **GitHub CLI (`gh`)** account. A browser
login alone is not `gh` authorization. Never paste a token into repository files.

```sh
gh auth login --hostname github.com --git-protocol https --web
python tools/publish.py --cloud-input-dir PATH_TO_WEBRTC_BUILD_OUTPUT --version v0.2.0
```

For portable Windows tools, pass `--gh PATH_TO_GH_EXE --git PATH_TO_GIT_EXE`.

For v0.2.0, the input is `build/build-webrtc.sh`'s public `output/` directory.
Existing verified MongoDB/notify artifacts and the MongoDB corresponding source
remain in `.release/` and are reused byte-for-byte. Publish only after the release's
browser, restore and reboot acceptance checks; use `--version v0.2.0-rc.1` if the
end-to-end verification is pending. The helper derives assets from `SHA256SUMS`.

For the original v0.1.0 build mode, `--input-dir` contains only `mongod`, `libubnt_sdnotify_jni.so`, the original
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
6. Uses the matching repository, pushes main and the versioned annotated tag.
7. Creates the requested release with prepared native/source assets; `-rc.N`
   versions are published as prereleases.
8. Prints the real repository, Release and one-command installation URLs.

It refuses to overwrite a pre-existing same-name unrelated repository or an
existing versioned Release. Inspect errors and retry deliberately; it does not
force-push, skip hooks or replace existing Release assets.

The v0.1.0 publication was completed under `ultrapravyj`:

- Repository: https://github.com/ultrapravyj/unifi-riscv
- Pre-release: https://github.com/ultrapravyj/unifi-riscv/releases/tag/v0.1.0

All published asset checksums were checked; anonymous public downloads were
verified from the Orange Pi. The local mirror option remains useful for isolated
testing, but the default URLs now point to the real published Release.
Running this v0.1.0 publisher again refuses to overwrite the existing Release;
prepare a new version for subsequent component releases.
