# Site Manager transport repair — v0.2.0

## Root cause

The original RISC-V port had **no `libubnt_webrtc_jni.so` for riscv64**.
UniFi Network 10.6.106 could authenticate local users, register with Ubiquiti,
and maintain its cloud MQTT connection, while being unable to create a remote
browser session. Site Manager displayed the controller as **Online**, then timed out.

The installed application was compared file-for-file with the extracted official
**10.6.106-36011-1** package, SHA256
`e93b70e73b9983c5e4d0a8ccc2d5d19b86db05e78f9a8c1850caf89ac069b240`.
No vendor files were missing or modified. The official package supplies WebRTC
JNI only for **x86_64 and aarch64**. The earlier port added native notify JNI,
but did not implement the separate native WebRTC dependency.

Evidence, with account/session data omitted:

```text
WARN system - cannot load native lib - ubnt_webrtc_jni
```

Inspection of the actual same-version Java class showed:

- `com.ubnt.net.n.AqxpICcpcuIxnda` loads `ubnt_webrtc_jni` at initialization.
- If loading fails, its native-availability flag remains false.
- Its remote-session creation method immediately returns `null` when that flag
  is false, before calling `WebRTCManager.createWebRTC` or generating SDP.
- `com.ubnt.webrtc.WebRTCManager` exposes native SDP, ICE transport, data-channel,
  file-transfer and teardown operations. There is no Java transport fallback here.

Consequently, opening firewall ports or changing the advertised IP cannot repair
this missing implementation. Authentication and registration were not bypassed
or reset. The user reproduced successful direct login and a Site Manager timeout
before deployment, then confirmed that Site Manager's dashboard and Networks page
loaded after the native transport was installed.

## Network evidence

On the real Orange Pi RV2:

- Internet route and all tested cloud socket source addresses used **wlan0**.
- DNS and certificate-validated HTTPS to the observed UI/SSO services passed.
- NTP reported synchronized; there was no usable IPv6 default route, and the
  successful cloud traffic used IPv4.
- The application maintained outbound TCP **8883** to its AWS IoT endpoint.
  A separate certificate-validating TLS check using its existing registration
  client certificate also passed. Certificates/keys were never printed.
- Actual successful browser sessions supplied **stun.cloudflare.com:3478** and
  **turn.cloudflare.com:3478**. STUN binding validation passed; authenticated TURN
  allocation produced relay candidates, followed by a connected transport.

```text
riscv-webrtc: STUN endpoint=stun:stun.cloudflare.com:3478
riscv-webrtc: TURN endpoint=turn:turn.cloudflare.com:3478
riscv-webrtc: ICE gathering complete; relay=yes
riscv-webrtc: transport state=2
```

UniFi's compiled default `turn.ubnt.com:3478` returned an ICMP refusal during a
standalone diagnostic. It was **not** the endpoint supplied for the successful
browser sessions. Diagnostics now prefer actual session endpoints instead of
assuming that every Ubiquiti hostname serves every cloud port.

The workstation's original management address was unavailable at investigation
start. The user supplied the board's Wi-Fi SSH address, which was used instead.
The board's Ethernet had no IPv4 lease at that point. Its existing advertised
`system_ip` setting and host network profiles were preserved: native ICE sockets
follow kernel routing, and cloud sessions succeeded using Wi-Fi.
After the final reboot, Ethernet again held its existing management address and
authenticated wired SSH was verified. The workstation's overlapping IPv4 /8
routes required an explicit Ethernet selection for that diagnostic socket;
global workstation routes and the board's network profiles were not changed.

The linked linuxserver issue #144 reports a **different stage**: its native ICE
engine was running, but TURN returned error 420 and peer connectivity checks
timed out. This installation originally could not start ICE at all. After repair,
the real Cloudflare TURN allocation succeeded; those repeating 420 errors were
not reproduced. A later ICE failure when a browser disappears is distinct from
a repeating failure that prevents an active dashboard from working.

## Fix and reproducibility

`native/webrtc_jni.cpp` independently implements the inspected JNI surface using
**libdatachannel 0.23.2**, libjuice, usrsctp, and the system OpenSSL libraries.
Both deployed ELF libraries are native little-endian **RISC-V / LP64D**. The JVM,
MongoDB and application remain native; no CPU emulation or foreign-architecture
sidecar is used. All vendor Java classes and authentication/authorization code
remain unchanged. The separately validated [9.0.120 restore fix](BACKUP-RESTORE.md)
adds one entry to `ace.jar`'s migration-metadata resource, with a protected original
and verification that no other JAR entry changes.

The JNI adapter provides real SDP gathering, verified DTLS, SCTP data channels,
queued binary/file transfer with backpressure/cancellation, and teardown.
It does not log SDP, TURN passwords, payloads, cookies or account tokens.
Its UDP ICE sockets are not bound to the controller's advertised management IP.

Pinned source revisions, runtime hashes and service endpoints are in `release.json`.
`build/build-webrtc.sh` builds the component and the real-vendor-class regression
probe; `tools/package-release.py --cloud-input-dir ...` packages the output and
complete corresponding upstream sources. MongoDB and notify artifacts are reused
byte-for-byte. See [BUILD.md](BUILD.md).

## Install, repair, diagnose

```sh
# Existing original project or v0.1.0 managed installation:
curl -fsSL https://github.com/ultrapravyj/unifi-riscv/releases/download/v0.2.0/install.sh | sudo bash -s -- --repair-cloud

# Secret-safe technical checks; does not claim browser authentication:
sudo python3 /opt/unifi-riscv/scripts/cloud.py check

# Real native transport and negative fingerprint regression tests:
sudo python3 /opt/unifi-riscv/scripts/cloud.py probe
```

The clean installer automatically deploys the transport, checks the vendor ABI,
runs a real native transport probe, and emits cloud diagnostics. Existing MongoDB
data, UniFi configuration, users, local credentials and cloud registration are
preserved. A systemd drop-in adds network-online ordering for legacy services
without replacing their database-readiness hooks. Future application updates
deploy the same verified transport into the new versioned application directory
and reject incompatible JNI declarations before activation.

## User-assisted acceptance check

1. Direct login at the current LAN address must load the dashboard.
2. Sign in to the UI Account in your own browser and complete MFA yourself.
3. Open the controller in Site Manager; load the dashboard and Settings → Networks.
4. Keep the dashboard open for at least two minutes and navigate again.
5. Where possible, repeat from an external network/mobile data connection.
6. Reboot, reconnect to SSH, check service startup and routing, then repeat steps 1–4.

`cloud.py check` distinguishes registration, TLS, native-library loading and STUN
checks from this browser acceptance test. A local login page or an Online badge
alone is not treated as proof of working remote access.

References:

- https://help.ui.com/hc/en-us/articles/115012240067-Enabling-UniFi-Remote-Management
- https://help.ui.com/hc/en-us/articles/218506997-Required-Ports-Reference
- https://github.com/linuxserver/docker-unifi-network-application/issues/144
