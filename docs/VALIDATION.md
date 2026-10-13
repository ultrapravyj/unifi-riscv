# Validation record — v0.1.0

## 1. Original real-device deployment

The original Orange Pi RV2 deployment ran native UniFi **10.6.106**, native
OpenJDK **25.0.4.1**, and the same native MongoDB **7.0.43**/notify JNI executables
published in this release. Checks included authenticated database access,
actual application `/status` readiness, browser-rendered setup UI, inform/STUN
responses, service restart, database restart, and a **physical full Orange Pi
reboot** with automatic service/network recovery and durable database marker.

Those results establish runtime viability of the binaries; **they do not alone
establish correctness of the new installer**. Its tests are below.

## 2. New installer tests actually executed

Environment: two freshly debootstrapped **Debian 13 riscv64** root filesystems
on the real RISC-V board, booted with their own systemd/PID/mount namespace and
an isolated network namespace. These were native Linux containers, not CPU
emulation. The production controller stayed running in the host filesystem and
network throughout. A temporary private HTTP mirror served the exact checksum-
pinned Release archives; UniFi was fetched directly from Ubiquiti.

The first environment was used to debug and exercise installation resumption
and lifecycle operations. A **second pristine OS** then installed the final
prepared archives successfully from scratch, with no existing Java/MongoDB/app
data. Archive-download transport used the private mirror because GitHub Release
publication requires account authorization; this is distinct from testing a
public GitHub download after publication.

Passed checks:

- Final binary-first installation on the second pristine native Debian 13 OS.
- Both enabled services returned automatically after restarting that final
  container's systemd instance; settings, credentials and the independent
  durability marker remained intact, with automatic restart counters at zero.
- Native dependency/Java installation; component and official UniFi SHA256 checks.
- Native MongoDB execution, authenticated first-admin bootstrap, per-install
  generated credentials, app DB access and actual `meta.up=true` for **10.6.106**.
- Real browser rendering of the initial setup wizard, HTTP **200**, visible
  **Name Your UniFi Network Server**, no JavaScript page errors, over a temporary
  workstation-loopback SSH tunnel to the isolated guest.
- No installed **gcc, g++, make, SCons or javac** in the ordinary installed guest.
- Repeated installation preserved credentials, semantic setting values and a
  durable synthetic DB marker.
- Protected cold backup, official same-version `update --reinstall`, and actual
  application/database readiness after activation.
- Deliberately injected update activation failure: **automatic rollback** restored
  old application, configuration, credential file and synthetic DB marker; real
  services became ready again.
- Explicit `rollback` also completed and retained the old application/private state.
- Explicit MongoDB restart and subsequent automatic UniFi restart/readiness.
- Credentials were absent from application/database logs and installed scripts.
- Six integrity/extraction tests passed: verified cache avoids network, corrupt
  download fails closed, traversal/symlink extraction rejected, wrong ELF rejected,
  private file permissions, and non-root traversability of implicit archive directories.
- Shell syntax/Python compilation checks and public release/source audit.

Two real problems were found and fixed rather than attributed to the old deployment:
implicit tar directories inherited umask 077 and blocked service-account execution;
an interrupted retry attempted to overwrite a running MongoDB executable. The
final installer sets traversable binary-tree permissions and reuses checksum-matching
installed components without replacing mapped executables.

The test sandbox's default syscall filter blocked MongoDB's secure-memory `mlock`
calls. The **sandbox**, not MongoDB/production security settings, was adjusted to
allow the standard mlock/munlock syscall family. All host production services stayed
available. This is relevant for running MongoDB in other restricted containers.

The durability fixture lives in an independent synthetic test DB: factory-default
UniFi deliberately cleans app-owned DB state before administrator setup. Settings
were compared semantically because Java Properties.store can rewrite ordering,
comments and its generated timestamp. No production DB contents or credentials
were copied into public validation materials.

## 3. Validation boundaries / remaining checks

- The new installer has **not** been run on a separately flashed, independently
  booted bare-metal OS. Native clean-container installation is verified; the
  physical full-reboot result belongs to the original hand-built deployment.
- Full physical **AP adoption has not been performed**. Inform/STUN listener tests
  in the original deployment do not establish real AP adoption.
- No other RISC-V board model is hardware-tested.
- Update transaction was tested using the same official stable application version
  with `--reinstall` and failure injection, not a future unseen UniFi release.
- MongoDB server-side JavaScript remains disabled; UniFi OS ULP/SSL-inspection
  integrations remain outside this standalone installer.
- The full clean-OS installer lifecycle used the exact prepared native/runtime
  assets through a private mirror. The subsequent public-download checks below
  verify the published transport and checksum pins, without claiming another
  bare-metal installation.

The private integration logs, test root filesystems and backups remain on the
test machine for investigation and are intentionally not Release assets.

## 4. Public publication/download verification — 2026-10-13

- Public repository: https://github.com/ultrapravyj/unifi-riscv
- Published **Pre-release v0.1.0**, not a draft:
  https://github.com/ultrapravyj/unifi-riscv/releases/tag/v0.1.0
- All seven intended Release assets were uploaded, including corresponding source.
- Downloaded published assets on the workstation and verified every SHA256 against
  `SHA256SUMS` and the prepared local artifacts.
- Downloaded the bootstrap/runtime/MongoDB/JNI from their public GitHub URLs on
  the Orange Pi using **anonymous curl**, with no GitHub credentials, and verified
  checksums plus the embedded bootstrap SHA256/runtime manifest consistency.
- The actual repository field in the published bundle is `ultrapravyj/unifi-riscv`.
- GitHub Actions source/integrity/shell checks passed for both main and the v0.1.0 tag.
- The original production controller remained application-ready during these checks.
