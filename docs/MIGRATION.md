# Existing/legacy installation

`install.sh` manages installations with `/opt/unifi-riscv/state.json` schema 1.
If that state exists, repeated installation preserves settings, data and credentials
and verifies the current controller version, including a version installed by `update`.

An earlier hand-built installation can contain the same service names and paths
without that state file. The new installer **detects it before changing data or services**
and exits with an unmanaged/legacy installation message. This protects an existing
controller from being replaced by an unrelated installation.

For v0.1.0 there is no automatic in-place conversion of the earlier experimental
layout. Keep it operational, take a private cold backup or a UniFi application backup,
and provision a separate supported OS/device/container with the new installer.
Restore the UniFi application's `.unf` backup through its setup wizard. Verify
management/adoption in the new environment before switching devices to it.

Do not remove real `/var/lib/unifi*` directories or invent a state file just to
bypass this detection. Existing host networking and the old controller are not
modified by the installer when the legacy check fires.
