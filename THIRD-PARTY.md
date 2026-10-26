# Redistribution and corresponding source

This is an unofficial, experimental installer. Ubiquiti has not endorsed it.

## UniFi Network

UniFi application binaries are **not redistributed in this repository or its
Release assets**. The installer downloads the unmodified official Debian package
directly from `dl.ui.com` and verifies Ubiquiti's published SHA256. Ubiquiti's
software license/EULA applies; it is presented in the application's setup UI.
See https://www.ui.com/legal/ and the license files in the official package.
Downloading with this installer does not replace the user's license obligations.

## MongoDB 7.0.43

The modified MongoDB executable is conveyed under **SSPL-1.0**. Redistribution is
permitted under its source-conveyance conditions, including section 6(d). Each
binary release is accompanied **in the same GitHub Release** by the complete
machine-readable corresponding source archive: the official upstream source,
the five applied modifications, build scripts, pinned inputs and build notices.
It is available at no additional charge. The source archive must remain available
for as long as the associated executable is offered.

`licenses/MongoDB-SSPL-1.0.txt`, `licenses/MongoDB-THIRD-PARTY-NOTICES.txt` and
`licenses/MongoDB-MPL-2.0.txt` preserve upstream notices. The upstream source
archive also contains the full licenses and notices for statically included
third-party components. MongoDB modifications dated **2026-10-13** remain under
SSPL-1.0; they are not relicensed as MIT by the installer license.

SSPL is not an OSI-approved open-source license. Its section 13 has additional
source obligations when MongoDB functionality is offered to third parties as a
service. This project publishes a downloadable installer, not a hosted database
service; operators of hosted services must assess that section for their use.

## Notify JNI and platform runtime

The independently written `native/ubnt_sdnotify_jni.c` is MIT-licensed and is
published with its native shared library and build instructions. It forwards
the inspected Java JNI signature to the real system `sd_notify()` function; it
does not copy Ubiquiti's precompiled library or its implementation.

The JNI library dynamically links `libsystemd.so.0` from Debian. MongoDB
dynamically links Debian's libc, libgcc, libstdc++, libcurl and OpenSSL. These
platform libraries, Java, Snappy JNI, SQLite and libsodium are installed from
the user's Debian repositories or provided in the official UniFi package,
not copied into our native binary archives. Their respective licenses apply.
The RISC-V cross compiler is an unmodified general-purpose GCC toolchain with
its own license/runtime exception; it is a build prerequisite, not a shipped
runtime component. See the exact artifact dependency and ISA manifest.

## Native WebRTC transport

`native/webrtc_jni.cpp` and `tests/NativeWebRTCProbe.java` are independently
written MIT-licensed interoperability code. They use the actual vendor Java
method declarations without copying Ubiquiti's native implementation.

The native WebRTC archive includes libdatachannel **0.23.2** (MPL-2.0), with
libjuice (MPL-2.0), usrsctp (BSD-3-Clause) and plog (MIT) statically incorporated
into that shared library. The adapter also incorporates **nlohmann/json (MIT)**
for bounded backup-envelope parsing. Their notices accompany the binary. The same Release
provides a separate **WebRTC corresponding-source archive** containing each
exact upstream source revision, complete notices, adapter/probe source and the
build script. These components are not relicensed by the project's MIT license.
System OpenSSL, zlib, zstd, libc and C++ runtime libraries are dynamically linked
and installed from Debian rather than redistributed in the WebRTC archive.

## Public material boundaries

Release assets contain executables, corresponding source, notices and build
metadata only. They contain no application databases, user settings, keys,
credentials, network profiles, Wi-Fi data or private cold backups. A cold backup
created by `manage.py backup` is private runtime data and is never a Release asset.
