# Optional builds and provenance

Normal installation downloads verified **ready native binaries**. This procedure
is for changing/rebuilding those binaries and corresponding-source compliance.

## Exact original inputs

- MongoDB `r7.0.43`, commit `75b4e8457392dfd3ee501669e8a1835f4c08b654`.
- Source archive SHA256:
  `00dd40bcd385103a5d98e342656e7444cdfadf34464c308206b804d9f5f47c75`.
- Five patches in `patches/`, applied in numeric order; see `build/BUILD-NOTICE.md`.
- Native Debian riscv64 GCC/G++ 14.2.0-19, binutils 2.44-3, Python 3.13.
- SCons 4.9.1 and `build/python-requirements.txt`.
- Flags: optimized O2, PIE, system allocator, `--js-engine=none`, no debug symbols.
- Original code-generation assistant: xPack RISC-V Embedded GCC 14.2.0-3
  Windows x64 archive, SHA256
  `9bb15efdeca256532c4a83ce6462c7dc1f9cfebe1f1f43d581b2ad7d077209b6`.

The modified executable reports `gitVersion=nogitversion` because the official
archive build did not contain `.git`. Provenance is established by source commit,
source hash, patches, build recipe, resulting binary checksum and ELF build ID.

## Native rebuild

Extract the corresponding-source Release asset. It includes the complete upstream
source archive, patch set, build tools/notices and licenses. The repository contains
the same supplemental files. On Debian 13 riscv64, as root:

```sh
bash build/rebuild-native.sh /opt/mongodb-new-source-build
```

Use an empty directory. The script installs a source-build toolchain, verifies the
upstream source archive, applies patches, creates a virtual environment, compiles
MongoDB and builds JNI. It does not touch a running controller or its database data.
It invokes SCons directly because the upstream wrapper pins dependency versions
unsuitable for Debian's Python 3.13.

On a small board, use a resilient `tmux`/systemd job, ample free storage and swap,
and one compiler job. The original 2 GiB board experienced severe compiler memory
pressure at higher parallelism. Full native source builds can take a long time;
ordinary installation is specifically designed to avoid them.

## Workstation-assisted build

The included `build/offload-compiler.py` preprocesses using the Pi's Linux GCC and
headers, sends compressed preprocessed input through a target-loopback SSH tunnel,
receives real RISC-V object code, and leaves linking on the Pi. Assembly/linking
and configuration probes that are not offloaded remain native.

Install `paramiko` on a workstation. Establish the target SSH host key with OpenSSH;
the public relay rejects unknown host keys. Start:

```sh
python build/cross-relay.py --ssh-host TARGET --ssh-user root --ssh-key YOUR_KEY \
  --toolchain-bin PATH_TO_XPACK_GCC_BIN
```

On the Pi, make the wrapper executable and create `offload-cc`/`offload-cxx` symlinks
to it. In the patched source tree, with the recorded SCons virtual environment:

```sh
scons -j4 --opt=on --dbg=off --disable-warnings-as-errors --js-engine=none \
  --allocator=system --linker=bfd --separate-debug=off --link-model=static \
  --build-dir=/opt/mongodb-codegen-out MONGO_VERSION=7.0.43 \
  PREFIX=/opt/unifi-riscv/mongodb CC=/path/offload-cc CXX=/path/offload-cxx install-mongod
```

The fifth patch compiles its TLS adapter explicitly with **native Linux GCC**.
It maps only the two external std::call_once TLS slots to real Linux libstdc++ TLS;
other portable TLS requests delegate to native libgcc. This is a language-runtime
ABI adapter, not instruction emulation. A 16-thread TLS/call_once/exception test
passed during the original build.

The final original link was resumed from the emitted SCons linker command after
repairing four interrupted object builds, with the native adapter and
`-Wl,--wrap=__emutls_get_address`. The final patch's SCons graph reproduces that
source/link composition without needing the original private build directory.

Builds are not promised byte-for-byte identical across paths/toolchain revisions.
After rebuilding, regenerate checksums/ISA/dependency records, run installation
and lifecycle tests, and distribute the corresponding source with the new binary.
