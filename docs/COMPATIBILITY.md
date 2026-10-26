# Native binary compatibility

## WebRTC transport — v0.2.0

Both `libubnt_webrtc_jni.so` and `libdatachannel.so.0.23` are native ELF64
little-endian **RISC-V / LP64D** libraries built on the same Debian 13 board.
They are deployed together in `lib/native/Linux/riscv64/`; the adapter uses an
`$ORIGIN` runtime search path for its pinned companion library. Dynamic platform
dependencies include OpenSSL 3, libc/libstdc++/libgcc, libm, zlib and zstd.
Ordinary installation does not compile C++ or Java. The shipped probe class was
compiled with the tested native Java 25 JDK and executes against the actual
official UniFi Java classes. See [cloud transport validation](CLOUD-ACCESS.md).

## MongoDB and notify JNI — preserved v0.1.0 artifacts

This table is derived from `file`, `readelf -A/-l/-d/--version-info` on the actual
published executables, not only the board model or the architecture of the Java package.

| Property | MongoDB | Notify JNI |
|---|---|---|
| ELF | ELF64 little-endian RISC-V PIE | ELF64 little-endian RISC-V shared object |
| ABI | LP64D, RVC, double-float | LP64D, RVC, double-float |
| Stack alignment | 16 bytes | 16 bytes |
| Build ID | `ad9023cca36137ebe8a5513dbd442a28ca12523b` | `4d367ca6934b4c23fa0999dd42b02343740c12a9` |
| ELF interpreter | `/lib/ld-linux-riscv64-lp64d.so.1` | Loaded by native JVM |
| Highest GLIBC requirement | `GLIBC_2.38` | Through system libsystemd |
| C++ runtime | `GLIBCXX_3.4.32`, `CXXABI_1.3.15` | No direct libstdc++ dependency |
| Other symbol versions | `OPENSSL_3.0.0`, `CURL_OPENSSL_4` | `LIBSYSTEMD_209` |

Both `.riscv.attributes` sections record:

```text
rv64i2p1_m2p0_a2p1_f2p2_d2p2_c2p0_zicsr2p0_zifencei2p0_zmmul1p0_zaamo1p0_zalrsc1p0
```

Summary: **RV64GC + Zicsr/Zifencei**. Zmmul is the multiplication subset of M;
Zaamo and Zalrsc are the component subsets of A. They are recorded explicitly
by this binutils/toolchain, not a requirement for a vector-capable board.
No V/vector, SpacemiT-specific, T-Head-specific or x86/ARM instructions are required
by these ELF attributes. Versions reflect the producer's ISA declarations;
base-extension versions are not independently measured by the installer's CPU check.

MongoDB directly needs:

```text
libcurl.so.4 libresolv.so.2 libcrypto.so.3 libssl.so.3 libstdc++.so.6
libm.so.6 libgcc_s.so.1 libc.so.6 ld-linux-riscv64-lp64d.so.1
```

Notify JNI directly needs `libsystemd.so.0`. Debian resolves those libraries'
transitive dependencies. The manifest lists the direct dependencies and version floors.
OpenSSL-flavoured libcurl is important because the executable requests `CURL_OPENSSL_4`.

**Supported policy is narrower than the theoretical ABI floor:** Debian 13 Trixie
riscv64 with systemd and native OpenJDK 25. A different Linux distribution with
similar symbol versions is not tested or supported by v0.1.0. In particular,
Debian 12/Ubuntu/musl systems are rejected rather than assigned compatibility by guess.

Original hardware: Orange Pi RV2, eight logical RISC-V CPUs, approximately 1.8 GiB
usable RAM, Armbian Community Debian 13.7 and kernel 6.18.55-current-spacemit.
It ran native UniFi/MongoDB/notify/JNA/Snappy/SQLite/libsodium successfully.
Other RV64GC boards are unverified hardware candidates.

The installer checks native architecture, Debian version, systemd, libc floor,
base-ISA HWCAP, exposed Zicsr/Zifencei CPU declarations, archive integrity,
ELF machine/endianness/LP64D, dynamic library resolution, and real binary execution.
Java and vendor JNI requirements also depend on the official package and Debian's
native runtime build, not solely on our two shipped ELF files.
