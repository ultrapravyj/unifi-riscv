# unifi-riscv

**Unofficial experimental binary-first UniFi Network installer for native riscv64.**
Release `v0.1.0` is a **pre-release of this installer**, using stable UniFi and
MongoDB versions. It is not an official Ubiquiti or MongoDB distribution.

[Русская инструкция](docs/INSTALL-RU.md) · [Binary compatibility](docs/COMPATIBILITY.md)
· [Build from source](docs/BUILD.md) · [Redistribution/source](THIRD-PARTY.md)

## One-command installation

On an Internet-connected supported machine with `curl` and `sudo`:

```sh
curl -fsSL https://github.com/ultrapravyj/unifi-riscv/releases/download/v0.1.0/install.sh | sudo bash
```

The bootstrap is version-pinned. It verifies the installer bundle's SHA256;
the bundle pins/verifies the native component archives. UniFi's unmodified
Debian package is fetched **directly from Ubiquiti**, with its published SHA256
verified. **No MongoDB, JNI or Java compilation occurs during installation.**

Optional advertised IP/DNS (this does not configure host networking):

```sh
curl -fsSL https://github.com/ultrapravyj/unifi-riscv/releases/download/v0.1.0/install.sh | sudo bash -s -- --host CONTROLLER_IP
```

The script reports the final URL, normally `https://CONTROLLER_IP:8443/`.
Open it and complete the initial setup wizard. The initial certificate is
self-signed. Allow several minutes for Java/application cold startup.

## Supported configuration

- **Debian 13 Trixie riscv64**, including Debian 13-based Armbian.
- **systemd** as the running service manager.
- Little-endian **RV64GC, LP64D**, including **Zicsr and Zifencei**. The ELF
  attributes and required symbol versions are recorded in `release.json`.
- glibc **>=2.38**, libstdc++ with **GLIBCXX_3.4.32 / CXXABI_1.3.15**, OpenSSL 3,
  OpenSSL-flavoured libcurl.so.4, native libsystemd.so.0.
- Native **OpenJDK 25** available from the configured Debian repositories.
- Recommended **2 GiB RAM or more**, and at least **3 GiB free storage** for
  installation/staging. Keep additional free storage for backups and data.
- Required default ports must be free. Internet, IP addressing, DNS and firewall
  access are prerequisites; the installer does not change those settings.

Hardware-tested: **Orange Pi RV2 / SpacemiT**, Debian 13-based Armbian. Other
RISC-V boards meeting the binary requirements are candidates, not hardware-tested
claims. Ubuntu, Debian 12, musl/Alpine, non-LP64D and emulated architectures are
not supported by this release. See [actual ELF properties](docs/COMPATIBILITY.md).

### Default tested versions

| Component | Version |
|---|---|
| UniFi Network | **10.6.106**, official package **10.6.106-36011-1** |
| MongoDB | **7.0.43**, modified native RISC-V build |
| Notify JNI | Project **v0.1.0**, native riscv64 |
| Java | Debian native OpenJDK **25**; original deployment tested **25.0.4.1** |

Java/platform libraries follow Debian repository security updates; their exact
installed package revisions are not frozen. MongoDB, JNI and UniFi application
archives are frozen by SHA256 in the release manifest.

## Persistence and repeated installation

| Item | Path |
|---|---|
| Application binaries/current link | `/opt/unifi-riscv/app/`, `/opt/unifi-riscv/app/current` |
| Native database/components | `/opt/unifi-riscv/mongodb/`, `/opt/unifi-riscv/components/` |
| UniFi persistent data | `/var/lib/unifi/` |
| MongoDB persistent data | `/var/lib/unifi-mongodb/` |
| Private DB credentials/config | `/etc/unifi-riscv/` |
| Service logs | `/var/log/unifi/`, `/var/log/unifi-mongodb/` |
| Installer state/cache/scripts | `/opt/unifi-riscv/` |
| Private cold backups | `/opt/unifi-riscv/backups/` |

Services: `unifi-riscv.service` and `mongod-riscv.service`. Both are enabled.
MongoDB binds only `127.0.0.1:27017`, with individual randomly generated admin
and application credentials. UniFi authenticates against its configuration,
statistics and audit databases. Credentials are not printed in installer output
or application connection logs.

Repeating the **same installer on an installation it manages** checks the
existing services/database/application and preserves data, settings and credentials.
Interrupted installation resumes using its saved state. An unknown or older
hand-built installation is detected and left unchanged; see [migration](docs/MIGRATION.md).
The installer does not silently reset a database, reuse default passwords, or
adopt an unrelated installation.

## Status, backup, update and rollback

```sh
sudo python3 /opt/unifi-riscv/scripts/manage.py status
sudo python3 /opt/unifi-riscv/scripts/manage.py backup
sudo python3 /opt/unifi-riscv/scripts/manage.py update
sudo python3 /opt/unifi-riscv/scripts/manage.py rollback
```

`update` discovers the newest **official stable Debian UniFi release** and verifies
its published checksum and Java/MongoDB/JNI requirements. It downloads/stages the
application before downtime, stops both services, takes a checksum-protected cold
backup, switches the application link, and waits for authenticated database and
application readiness. It restores the previous application and private runtime
state automatically if activation fails. It reuses the ready-made notify binary;
normal updates do not compile native components or rebuild the machine.

To select an official stable version or repeat the update transaction for testing:

```sh
sudo python3 /opt/unifi-riscv/scripts/manage.py update --version 10.6.106 --reinstall
sudo python3 /opt/unifi-riscv/scripts/manage.py rollback --archive /opt/unifi-riscv/backups/BACKUP.tar.gz
```

Earlier application directories and displaced private state are retained after
rollback for investigation. A changed Java/JNI/database requirement is rejected
for review rather than guessed. Native component upgrades require a new installer
release with a compatible tested component manifest.

**Cold backups contain real database/configuration/credential data.** They are
root-only private artifacts, never GitHub Release assets. Copy the `.tar.gz` and
its adjacent `.tar.json` checksum/application metadata together to private storage.

## Diagnostics and ports

```sh
systemctl status unifi-riscv mongod-riscv --no-pager
journalctl -u unifi-riscv -u mongod-riscv --no-pager
curl -kfsS https://127.0.0.1:8443/status
ss -lntup
free -h
```

Readiness means `/status` reports `meta.up=true` for the expected version, not
merely that Java started. UniFi uses native systemd `READY=1`; startup waits for
authenticated MongoDB. An explicit MongoDB restart restarts UniFi through `PartOf=`.

Core listeners: TCP **8443** (management), **8080** (inform); UDP **3478** (STUN),
**10001** (discovery). Other observed listeners: TCP 8880, 8843, 6789, 28082 and
UDP 5514. The installer does not enable a host firewall or expose MongoDB remotely.

## What is tested

See [the validation record](docs/VALIDATION.md), which separates:

1. The original real Orange Pi deployment, including a physical full reboot.
2. Tests of **this new installer** in a clean native Debian/systemd container.
3. Checks still needed on an independently provisioned bare-metal OS / physical AP.

This distinction matters: a working original deployment alone is not a test of
the new installation code.

## Actual limitations

- MongoDB is compiled with **server-side JavaScript disabled**. `$where`,
  JavaScript `$function`, legacy map-reduce/eval operations are unavailable.
  Verified UniFi startup/database/UI use works with this build; future UniFi
  changes that require such operations must be evaluated.
- **No physical AP adoption was validated.** Inform/STUN listener tests are not
  a claim of a completed real-device adoption test.
- Standalone UniFi 10.6 periodically retries the absent UniFi OS **ULP/SSL-inspection**
  endpoint `127.0.0.1:9080/api/ucore/manifest`. UniFi OS-only functionality is not
  provided by this standalone Network Server installer; the optional retry is
  not a controller restart loop.
- The original executable used a cross-build TLS compatibility bridge. All
  runtime code remains native RISC-V; build provenance/patches are published.

## Release contents and source

Release assets: `install.sh`, the installer bundle, ready MongoDB archive, ready
notify JNI archive, corresponding MongoDB source archive, `BUILD-INFO.json`,
and `SHA256SUMS`. UniFi, Java and Debian shared libraries are not rehosted.
Redistribution/license details are in [THIRD-PARTY.md](THIRD-PARTY.md).

Project installer code is MIT. MongoDB and its modifications are SSPL-1.0,
with their corresponding source and upstream notices provided alongside binaries.
Ordinary users need none of the optional source-build toolchains.
