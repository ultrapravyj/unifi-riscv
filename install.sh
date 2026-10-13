#!/bin/bash
# SPDX-License-Identifier: MIT
# Pinned bootstrap: runtime bundle and native assets are checksum-verified.
set -euo pipefail
REPOSITORY="ultrapravyj/unifi-riscv"
RELEASE="v0.1.0"
BUNDLE="unifi-riscv-installer-v0.1.0.tar.gz"
BUNDLE_SHA256="4e1ccd0a9ee468cfcad0b847ebcde64d28b04db5c3c19c25256108a3fff96bbb"
BASE="https://github.com/${REPOSITORY}/releases/download/${RELEASE}"

if [ "$(id -u)" -ne 0 ]; then
    echo 'Run as root: curl -fsSL <pinned install.sh URL> | sudo bash' >&2
    exit 1
fi
if [ "$(uname -m)" != riscv64 ]; then
    echo 'Native riscv64 is required; architecture emulation is not supported.' >&2
    exit 1
fi
. /etc/os-release
if [ "${ID:-}" != debian ] || [ "${VERSION_ID:-}" != 13 ]; then
    echo 'This release supports Debian 13 Trixie / Debian-based Armbian 13.' >&2
    exit 1
fi
if [ ! -d /run/systemd/system ]; then
    echo 'A running systemd system is required.' >&2
    exit 1
fi
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
    if [ "${args[i]}" = --artifact-base-url ]; then
        BASE="${args[i+1]:?Missing artifact base URL}"
    fi
done
export DEBIAN_FRONTEND=noninteractive
if ! command -v curl >/dev/null || ! command -v python3 >/dev/null; then
    apt-get update --error-on=any
    apt-get install -y --no-install-recommends curl ca-certificates python3
fi
work=$(mktemp -d /var/tmp/unifi-riscv-install.XXXXXX)
trap 'rm -rf "$work"' EXIT
curl -fL --retry 3 --connect-timeout 30 --max-time 300 "${BASE%/}/${BUNDLE}" -o "$work/$BUNDLE"
printf '%s  %s\n' "$BUNDLE_SHA256" "$work/$BUNDLE" | sha256sum -c -
python3 - "$work/$BUNDLE" "$work" <<'PY'
import pathlib, sys, tarfile
with tarfile.open(sys.argv[1]) as archive:
    for member in archive.getmembers():
        name = pathlib.Path(member.name)
        if name.is_absolute() or '..' in name.parts or not (member.isfile() or member.isdir()):
            raise SystemExit('Unsafe installer archive')
    archive.extractall(sys.argv[2], filter='data')
PY
python3 "$work/installer/runtime/install.py" "${args[@]}"
