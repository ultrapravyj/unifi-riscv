#!/bin/bash
# Optional source build. Ordinary installation never invokes this script.
set -euo pipefail
repo=$(realpath "$(dirname "$0")/..")
work=${1:?Pass a new, empty absolute build directory}
test "$(uname -m)" = riscv64
test ! -e "$work"
export DEBIAN_FRONTEND=noninteractive
apt-get update --error-on=any
apt-get install -y build-essential patch python3-venv python3-dev libssl-dev libcurl4-openssl-dev libyaml-dev liblzma-dev libzstd-dev libsnappy-dev zlib1g-dev libicu-dev libsasl2-dev pkg-config libsystemd-dev openjdk-25-jdk-headless
mkdir -p "$work/source" "$work/out"
curl -fL --retry 3 https://codeload.github.com/mongodb/mongo/tar.gz/refs/tags/r7.0.43 -o "$work/mongo-r7.0.43.tar.gz"
printf '%s  %s\n' 00dd40bcd385103a5d98e342656e7444cdfadf34464c308206b804d9f5f47c75 "$work/mongo-r7.0.43.tar.gz" | sha256sum -c -
tar -xzf "$work/mongo-r7.0.43.tar.gz" -C "$work/source"
cd "$work/source/mongo-r7.0.43"
for p in "$repo"/patches/00[1-5]-*.patch; do patch -p1 < "$p"; done
python3 -m venv "$work/venv"
"$work/venv/bin/pip" install -r "$repo/build/python-requirements.txt"
export PATH="$work/venv/bin:$PATH"
scons -j1 --opt=on --dbg=off --disable-warnings-as-errors --js-engine=none --allocator=system --linker=bfd --separate-debug=off --link-model=static --build-dir="$work/out" MONGO_VERSION=7.0.43 PREFIX=/opt/unifi-riscv/mongodb install-mongod 2>&1 | tee "$work/build.log"
gcc -shared -fPIC -O2 -Wl,-z,relro,-z,now \
    -I/usr/lib/jvm/java-25-openjdk-riscv64/include \
    -I/usr/lib/jvm/java-25-openjdk-riscv64/include/linux \
    "$repo/native/ubnt_sdnotify_jni.c" -lsystemd -o "$work/libubnt_sdnotify_jni.so"
echo "Database: $work/out/install/opt/unifi-riscv/mongodb/bin/mongod"
echo "JNI: $work/libubnt_sdnotify_jni.so"
