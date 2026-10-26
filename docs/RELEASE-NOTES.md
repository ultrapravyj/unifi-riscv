# v0.2.0 — native RISC-V Site Manager remote transport

Fixes the case where local login worked and Site Manager showed **Online**, but
opening the controller timed out. The original port lacked RISC-V WebRTC JNI;
the official same-version package only included x86-64/ARM64 builds.

- Adds an independently implemented native WebRTC JNI adapter, backed by pinned
  **libdatachannel 0.23.2**, libjuice and usrsctp.
- Real SDP/ICE, authenticated TURN relay allocation, verified DTLS, SCTP data
  channels and queued binary/file responses. Authentication/MFA and the vendor
  Java classes remain unchanged; the specific 9.0.120 metadata correction is described below.
- Adds `--repair-cloud` for the original project layout and v0.1.0 installations.
  Existing MongoDB data, UniFi settings and cloud registration are preserved.
- Clean installs and application updates deploy the native component, validate
  the actual vendor JNI declarations, and execute a real transport probe.
- Adds secret-safe cloud diagnostics and a negative DTLS fingerprint regression.
- Fixes backup restore with scoped `*_restore` database roles, a single-action
  fsync grant, and `Restart=always` for UniFi's clean restore exit.
- Corrects missing MIME types on remote `.unf` uploads, preserving file bytes
  and authorization fields.
- Adds the omitted 9.0.120 migration-table entry for pinned UniFi 10.6.106, after
  isolated real-backup restoration and zero-error migration tests. No backup
  version rewriting or Java/authentication-class modification is involved.
- The user confirmed restoration of the original 9.0.120 backup through Site Manager.
- Preserves MongoDB **7.0.43** and notify JNI binaries byte-for-byte. Tested UniFi
  **10.6.106-36011-1**, OpenJDK **25.0.4.1+1-1-deb13u1-Debian** on Orange Pi RV2 /
  Debian 13-based Armbian. All runtime components remain native riscv64.
- Ships complete corresponding WebRTC source and licenses alongside native binaries.

The user confirmed Site Manager dashboard and Networks-page access after repair.
The validation record documents installer, reboot and browser acceptance results:
[docs/VALIDATION.md](https://github.com/ultrapravyj/unifi-riscv/blob/v0.2.0/docs/VALIDATION.md). Root cause and diagnostics:
[docs/CLOUD-ACCESS.md](https://github.com/ultrapravyj/unifi-riscv/blob/v0.2.0/docs/CLOUD-ACCESS.md).

```sh
# Existing project installation:
curl -fsSL https://github.com/ultrapravyj/unifi-riscv/releases/download/v0.2.0/install.sh | sudo bash -s -- --repair-cloud
```

The adapter uses UDP ICE/STUN/TURN; TCP/TLS-only TURN networks are outside the
validated transport. Existing MongoDB server-side-JavaScript, UniFi OS-only
features and physical AP-adoption limitations remain documented below.

## v0.1.0 history — experimental native riscv64 UniFi installer

This is an **unofficial pre-release installer**, not an official Ubiquiti or
MongoDB distribution. Default components are stable UniFi **10.6.106** and
MongoDB **7.0.43**, with native OpenJDK **25** on Debian **13 riscv64**.

Ordinary installation uses checksum-pinned ready native MongoDB and notify JNI
archives and installs Java/platform libraries from Debian. UniFi is fetched
directly from Ubiquiti and checked against its published SHA256. No native
compilation takes place during installation or ordinary application update.

Includes persistent systemd services, individual database credentials, resumable
and idempotent installation, private cold backup, official stable application
updates and automatic rollback. SHA256SUMS and BUILD-INFO.json record the assets,
actual ISA/dependencies and provenance.

Validation: final installation on a second pristine native Debian/systemd container;
real setup page; authenticated DB; repeat-install preservation; cold backup;
same-version official update transaction; injected activation failure/automatic
rollback; explicit rollback; dependency restart; no compiler tools in the guest;
integrity/extraction tests. The original real-device deployment additionally
survived a physical full reboot. See docs/VALIDATION.md for exact boundaries.

Hardware-tested: Orange Pi RV2. Required CPU/ABI: little-endian RV64GC +
Zicsr/Zifencei, LP64D. Supported OS policy: Debian 13 Trixie with systemd and
native OpenJDK 25. Other boards/OSes and physical AP adoption are unverified.

Limitations: MongoDB **server-side JavaScript disabled**; UniFi OS-only ULP/SSL
inspection absent in this standalone installation. Some optional-feature retries
remain in vendor application logs. No hosted database service is provided.

Redistribution: installer and independent JNI bridge are MIT; modified MongoDB
is SSPL-1.0. The **complete corresponding-source archive is a Release asset
alongside its binary**, preserving upstream notices and the five patches/build
recipes. Do not remove the source asset while the binary is offered. UniFi, Java
and Debian shared libraries are not rehosted. See THIRD-PARTY.md.
