# Existing/legacy installation

`install.sh` manages installations with `/opt/unifi-riscv/state.json` schema 1.
If that state exists, repeated installation preserves settings, data and credentials
and verifies the current controller version, including a version installed by `update`.

An earlier hand-built installation can contain the same service names and paths
without that state file. The new installer **detects it before changing data or services**
and exits with an unmanaged/legacy installation message. This protects an existing
controller from being replaced by an unrelated installation.

For **v0.2.0**, the original project can receive an in-place, targeted **cloud
transport repair**, preserving the existing application, MongoDB data and cloud
registration:

```sh
curl -fsSL https://github.com/ultrapravyj/unifi-riscv/releases/download/v0.2.0/install.sh | sudo bash -s -- --repair-cloud
sudo python3 /opt/unifi-riscv/scripts/cloud.py check
```

This does not invent a managed-installation state file or convert the original
layout into a new installation. For a legacy deployment, use `cloud.py` for this
repair/diagnostics and retain its established application-update workflow.
The repair adds a pre-activation cloud deployment/ABI-probe hook to the recognized
original `update-unifi.py`, preserving its workflow and keeping a protected copy.
This prevents a later legacy application update from losing the native transport.
Unknown/custom updater layouts are preserved rather than overwritten.
Managed schema-1 installations retain `manage.py` backup/update/rollback support.
The repair backs up replaced native files and restores them if activation fails.

Do not remove real `/var/lib/unifi*` directories or invent a state file just to
bypass this detection. Existing host networking and the old controller are not
modified by the installer when the legacy check fires.
