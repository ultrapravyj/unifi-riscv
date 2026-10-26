#!/bin/bash
# SPDX-License-Identifier: MIT
# Rebuild only the missing native remote-access component; no database changes.
set -euo pipefail
[ "$(uname -m)" = riscv64 ] || { echo 'Build on native riscv64.' >&2; exit 1; }
source_root=$(cd -- "$(dirname -- "$0")/.." && pwd)
work=${1:-/opt/unifi-riscv/build/cloud-native}
application=${2:-/opt/unifi-riscv/app/current}
mkdir -p "$work"
pin=9e6a13abbb6846c003d817d0387b6706466e2b03
if [ ! -d "$work/libdatachannel/.git" ]; then
    git clone --no-checkout https://github.com/paullouisageneau/libdatachannel.git "$work/libdatachannel"
fi
git -C "$work/libdatachannel" checkout --detach "$pin"
[ "$(git -C "$work/libdatachannel" rev-parse HEAD)" = "$pin" ]
git -C "$work/libdatachannel" diff --exit-code
git -C "$work/libdatachannel" submodule update --init deps/plog deps/usrsctp deps/libjuice deps/json
git -C "$work/libdatachannel" submodule status
cmake -S "$work/libdatachannel" -B "$work/build" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$work/prefix" \
    -DCMAKE_INSTALL_LIBDIR=lib -DNO_MEDIA=ON -DNO_WEBSOCKET=ON \
    -DNO_EXAMPLES=ON -DNO_TESTS=ON
cmake --build "$work/build" --target datachannel -j "${BUILD_JOBS:-1}"
cmake --install "$work/build"
out="$work/output"
mkdir -p "$out/source" "$out/licenses"
g++ -std=c++17 -O2 -fPIC -fvisibility=hidden -Wall -Wextra \
    -I/usr/lib/jvm/java-25-openjdk-riscv64/include \
    -I/usr/lib/jvm/java-25-openjdk-riscv64/include/linux \
    -I"$work/prefix/include" -I"$work/libdatachannel/deps/json/include" -shared "$source_root/native/webrtc_jni.cpp" \
    -L"$work/prefix/lib" -Wl,-rpath,'$ORIGIN' -ldatachannel -pthread \
    -o "$out/libubnt_webrtc_jni.so"
cp -L "$work/prefix/lib/libdatachannel.so" "$out/libdatachannel.so.0.23"
cp "$source_root/tests/NativeWebRTCProbe.java" "$out/source/"
javac -cp "$application/lib/internal/internal-dependencies.jar" -d "$out" "$out/source/NativeWebRTCProbe.java"
for mode in normal reject-fingerprint upload-envelope non-upload-envelope; do
    java --enable-native-access=ALL-UNNAMED -cp "$out:$application/lib/internal/internal-dependencies.jar" \
        NativeWebRTCProbe "$out/libubnt_webrtc_jni.so" "$mode"
done
git -C "$work/libdatachannel" archive --format=tar.gz -o "$out/source/libdatachannel-$pin.tar.gz" HEAD
cp "$work/libdatachannel/LICENSE" "$out/licenses/libdatachannel-MPL-2.0.txt"
for dep in plog usrsctp libjuice json; do
    directory="$work/libdatachannel/deps/$dep"
    commit=$(git -C "$directory" rev-parse HEAD)
    git -C "$directory" diff --exit-code
    git -C "$directory" archive --format=tar.gz -o "$out/source/$dep-$commit.tar.gz" HEAD
    for license in LICENSE LICENSE.txt LICENSE.md LICENSE.MIT COPYING; do
        if [ -f "$directory/$license" ]; then
            cp "$directory/$license" "$out/licenses/$dep-$license"
        fi
    done
done
cp "$source_root/native/webrtc_jni.cpp" "$source_root/build/build-webrtc.sh" "$out/source/"
printf '%s\n' 'libdatachannel 0.23.2 (MPL-2.0), libjuice (MPL-2.0), usrsctp (BSD), plog (MIT), nlohmann/json (MIT)' > "$out/BUILD-NOTICE.txt"
sha256sum "$out/"*.so* "$out/NativeWebRTCProbe.class"
echo "Native build, regression tests and corresponding source: $out"
