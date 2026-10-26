# Backup upload, restore and 9.0.120 migration

Older Network backups can normally be restored on newer UniFi versions, as
described in Ubiquiti's [Backups and Migration](https://help.ui.com/hc/en-us/articles/360008976393-Backups-and-Migration-in-UniFi)
guide. Investigation found three separate implementation/configuration gaps in
this project, plus one specific omission in the official version metadata.

## 1. Temporary restore databases and fsync

The local HAR showed `/upload/backup` returning HTTP 200 / `rc: ok` for a
10.6.106 backup, then an accepted restore command. Server-side import failed:

```text
Unauthorized: not authorized on unifi_restore to execute command { dropDatabase: 1 }
Failed to import backup. No changes were applied.
```

The earlier external-MongoDB account owned the active databases but lacked their
temporary restore databases. The installer/repair now grants `dbOwner` only on
`unifi_restore`, `unifi_stat_restore`, and `unifi_audit_restore`, preserving
existing grants and credentials. Real 9.x migrations additionally require
`fsync`; a custom `unifi-riscv-fsync` role grants **only that cluster action**.
The application is not granted MongoDB root, dbOwner on admin, or hostManager.

## 2. Clean application exit after restore

UniFi exits with code 0 after its restore workflow. `Restart=on-failure` left
the controller stopped and the browser polling **Restoring** indefinitely.
The service now uses **`Restart=always`**, including a legacy-layout drop-in.
An explicit `systemctl stop` still stops the service normally. Successful
same-version and 9.0.120 restores verified automatic return to readiness.

## 3. Missing MIME type on remote .unf uploads

The official Java remote-upload bridge calls `ContentType.parse(contentType)`
and constructs an Apache `FileBody`. Browser `.unf` files can have no registered
MIME type; null/empty input triggers `NullPointerException: Content type`.

The native adapter supplies `application/octet-stream` only to `.unf`
`/upload/backup` envelopes with missing/null/blank `contentType`. It preserves
the operation ID, file bytes and authentication fields and leaves other requests
unchanged. Native regression tests cover the fallback and exact passthrough of
non-upload traffic. The user subsequently restored the 9.0.120 backup **through
Site Manager**, exercising the real multipart/upload/import path.

## 4. Missing 9.0.120 entry in the official 10.6.106 migration table

A second HAR showed a different failure, before import:

```text
/upload/backup: HTTP 400, api.err.InvalidBackupVersion
```

The backup's actual internal version was **9.0.120**, not merely its filename.
The source controller also reported 9.0.120. The original official 10.6.106
`ace.jar` lists `9.0.[67-114]` and `9.0.118` in `product.properties`, but omits
9.0.120. This is not a general prohibition on restoring older backups.

The fix adds exactly **9.0.120** to that metadata resource in the checksum-pinned
**10.6.106** JAR. Every other JAR entry, including every Java class and all
authentication/authorization code, is verified unchanged. The original JAR is
kept in a protected backup. The `.unf` file and its internal version are never
rewritten; the real official database migrations run from **9.0.120 to 10.6.106**.
Unknown JAR hashes are rejected, other application versions are not patched,
and repeat application is a no-op. No wildcard acceptance of arbitrary versions
is introduced.

Before deployment, this exact backup was restored twice into a separate native
Debian/systemd fixture, with **no default route** so source cloud/device identities
could not reach the Internet, original controller or devices. After the scoped
fsync correction, the repeat test recorded **zero import/migration errors**, a
completed 9.0.120 → 10.6.106 migration, and preserved 9 networks, 2 WLANs and 3
device records. The user then confirmed the real cloud restore on the RV2.

This does not establish physical adoption/migration of those devices: their
inform targets and migration cutover remain separate operational steps.

## Install and diagnose

```sh
curl -fsSL https://github.com/ultrapravyj/unifi-riscv/releases/download/v0.2.0/install.sh | sudo bash -s -- --repair-cloud
sudo python3 /opt/unifi-riscv/scripts/cloud.py check
systemctl show unifi-riscv -p ActiveState -p Restart -p NRestarts
```

The same bundle deploys the cloud transport and these validated restore fixes.
Diagnostics include temporary-database privileges, the fsync grant and the
9.0.120 metadata entry. Raw HARs, source backups, databases, session identifiers
and authentication material remain private and are not GitHub assets.
