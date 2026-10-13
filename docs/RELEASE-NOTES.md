# v0.1.0 — experimental native riscv64 UniFi installer

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
