# Validation record

## v0.2.0 cloud transport and restore — 2026-10-22 through 2026-10-25

Verified on the existing real Orange Pi RV2 controller, using unmodified official
UniFi **10.6.106-36011-1**, native OpenJDK **25.0.4.1+1-1-deb13u1-Debian**, native
MongoDB **7.0.43**, kernel **6.18.55-current-spacemit** and Debian **13.7** /
Armbian Community **26.11.0-trunk.83**.

- Reproduced successful direct login and Site Manager Online → Connection Timeout
  with user assistance; distinguished this from local authentication failure.
- Compared every original vendor application file with the exact same official
  package: no removals/changes. WebRTC JNI was absent for riscv64 in both, while
  x86-64/ARM64 vendor WebRTC libraries were present. The startup warning and
  actual Java native-availability early return established the transport gap.
- Wi-Fi default route, synchronized time, validated HTTPS and registered-client
  mutual TLS on the actual AWS IoT port **8883** passed.
- Compiled both missing-transport libraries natively with **GCC 14.2.0-19**,
  **CMake 3.31.6-2** and **Ninja 1.12.1-1**, using pinned upstream source revisions.
- Executed the real vendor-class JNI probe: SDP, ICE, DTLS, SCTP and bidirectional
  binary transfer passed. Deliberately altered certificate fingerprint was rejected.
- Deployed the native component and restarted UniFi; the JVM mapped both native
  libraries, and local application readiness returned without a database replacement.
- The user confirmed that **Site Manager's dashboard and Settings → Networks
  loaded**, and direct local login remained functional. Correlated native events
  showed actual Cloudflare STUN/TURN endpoints, `relay=yes`, and connected transports.
- Ran the packaged legacy repair and repeated it idempotently. Its cloud check
  verified native hashes/loading, database ping, registration presence, HTTPS,
  mutual TLS, correct Wi-Fi source routing, and a valid Cloudflare STUN response.
- A private cold backup and configuration/database-count baseline were taken before
  deployment. No account keys, tokens, databases or private logs are release assets.

Additional completed checks:

- Fresh native Debian 13/systemd installation on the same board in a separate
  root filesystem and network namespace; repeated install, repair, same-version
  application update and native-library loading in the new application directory.
  No compiler/JDK was installed in that ordinary-install guest.
- Physical full-board reboot, changed boot ID, Wi-Fi SSH reconnection, enabled
  services active with zero automatic restarts, native library hashes/loading,
  registered-client TLS, STUN, routing and database readiness after boot.
- The user explicitly confirmed dashboard/Networks access from an **external
  network** after reboot, with local login intact and continued navigation.
- Eleven integrity/metadata/updater-boundary tests passed. Native probes verified real
  transport, altered-fingerprint rejection, backup MIME fallback/body/auth-field
  preservation, and byte-identical non-upload passthrough.
- A local HAR isolated missing `unifi_restore` permissions and clean-exit restart
  behavior. A same-version restore completed after those corrections.
- A real 9.0.120 backup first reproduced the official metadata-list rejection.
  The actual source version was then admitted in an isolated, non-Internet-routed
  fixture with no Java/authentication-class changes or backup version rewriting.
  After the minimal fsync grant, a fresh repeat completed real migrations with
  **zero** import/migration errors and 9 networks, 2 WLANs, 3 device records.
- The user confirmed the 9.0.120 restore on the real RV2 **through Site Manager**;
  actual database counts and the completed migration matched the isolated result,
  and the controller automatically returned after its clean restore exit.
- The final installer was also tested with fresh application/database state in
  the retained isolated Debian OS. Fresh privilege creation, migration metadata,
  native transport, JRE-only deployment and a repeated/idempotent install passed.
  The repeat test caught and corrected the need for explicit `showPrivileges`
  when validating the existing custom MongoDB role.
- The recognized legacy updater also receives a backed-up, idempotent staging
  hook that deploys/probes cloud support before downtime; unknown custom updater
  layouts are not overwritten.
- A second full physical reboot with the final component and restored data
  retained all 9 networks, 2 WLANs and 3 device records. Both enabled services
  became active with zero restart counters; Wi-Fi cloud routing, verified cloud
  TLS, STUN and authenticated Ethernet SSH passed. The user again confirmed
  working remote dashboard/Networks/Wi-Fi navigation from an **external network**.

Browser results are user-assisted; technical socket checks do not substitute
for loading actual remote pages. Physical adoption of the restored device records
has not been verified. Private HARs, fixtures and backup data are not public assets.

## Historical v0.1.0 validation

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
