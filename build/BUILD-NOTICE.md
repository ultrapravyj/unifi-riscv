# Modified MongoDB build notice — 2026-10-13

Upstream: MongoDB tag `r7.0.43`; commit
`75b4e8457392dfd3ee501669e8a1835f4c08b654` (tag object
`21f4483e9eafcaa1c702ade43fb8fd4873179241`). The original archive SHA256 is
`00dd40bcd385103a5d98e342656e7444cdfadf34464c308206b804d9f5f47c75`.

This is a modified version, not an official MongoDB RISC-V distribution. The
program and modifications are released under SSPL-1.0, preserving upstream
third-party licenses. Applied patches, in order:

1. Portable RISC-V processor-yield hint.
2. Python 3.13 importlib module loader compatibility.
3. Omit debug symbols for build resource limits.
4. Correct the `--js-engine=none` option's false/true interpretation.
5. Native Linux bridge for the cross compiler's two external `std::call_once`
   TLS descriptors, forwarding other portable TLS requests to native libgcc.

Executable build: GCC 14.2, SCons 4.9.1, `-O2`, PIE, system allocator, no server-side
JavaScript engine. Linux preprocessing and final linking used Debian riscv64
GCC/G++ 14.2.0-19 and binutils 2.44-3. Resource-heavy code generation was offloaded
to the unmodified xPack RISC-V Embedded GCC 14.2.0-3 Windows-hosted toolchain with
`-march=rv64gc -mabi=lp64d -mtune=rocket`. Its published archive SHA256 was verified:
`9bb15efdeca256532c4a83ce6462c7dc1f9cfebe1f1f43d581b2ad7d077209b6`.

The exact cross wrapper/relay source is included in corresponding source. The
TLS adapter was compiled with native Linux GCC; a 16-thread, 16,000-iteration
call_once/TLS/exception integration test passed on the target. The emitted
database link command is reproducible from the patched SCons build graph.
Compiler dependencies are recorded in `python-requirements.txt`.

ELF build ID: `ad9023cca36137ebe8a5513dbd442a28ca12523b`. The tarball source
build reports `gitVersion=nogitversion`; the verified upstream commit above,
source archive and patches establish provenance.
