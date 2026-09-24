# Checksum-verified curl workflow

## Status

Version `1.0.5` is the installed and owner-approved production baseline.
Version `1.0.3` is
withdrawn because live download verification correctly detected that its
published bundle bytes did not match its embedded checksum.  Do not use the
version `1.0.3` bootstrap.  Version `1.0.5` supports uninstalling any verified
installed version and corrects post-install cleanup.  Reboot,
interrupted-install, and explicit purge acceptance remain tracked in issue #3.

## Trust chain

The documented command will never pipe a mutable branch directly into a shell.
It will:

1. download a small bootstrap from an immutable Git commit over HTTPS;
2. verify the bootstrap against the SHA-256 value printed in the repository;
3. run the verified bootstrap without elevated privileges;
4. download a versioned release bundle from a second immutable Git commit;
5. verify the complete bundle against the checksum embedded in the verified
   bootstrap;
6. validate the bundle's source-commit marker;
7. invoke `sudo` only for the selected, verified installation or removal phase.

No branch-based curl command is supported.

## Production trust anchors

| Item | Immutable value |
| --- | --- |
| Application source commit | `2400a3108235a477c6d9c2c3af0d2024f1cf9633` |
| GitHub CI | Run 68 passed |
| Bundle asset commit | `0c9f90a10ed418fffd761b8b719351357167b46e` |
| Bundle SHA-256 | `b5da1523ec3b458a694be3d178effa33cb5fa67e0578d43e26b7fcdfe7c323b0` |
| Bootstrap commit | `8d6a779b34341a302a8a6c84502f2d95002dc95e` |
| Bootstrap SHA-256 | `af2d2ca9c17d2420c22bb0ba894a409f00f468b0557eb95e8aacddfe9b430335` |

## Production install command

Run this on the Raspberry Pi.  It downloads and verifies the bootstrap before
the bootstrap downloads and verifies the complete bundle.  `sudo` is invoked
only after both checks pass.

```bash
bootstrap=/tmp/pihole-speedtest-v6-bootstrap.sh && \
curl --fail --show-error --silent --location \
  --proto '=https' --tlsv1.2 \
  --output "$bootstrap" \
  https://raw.githubusercontent.com/RamrattanN/PiHoleSpeedtestV6/8d6a779b34341a302a8a6c84502f2d95002dc95e/release/pihole-speedtest-v6-bootstrap.sh && \
printf '%s  %s\n' \
  'af2d2ca9c17d2420c22bb0ba894a409f00f468b0557eb95e8aacddfe9b430335' \
  "$bootstrap" | sha256sum --check --status - && \
bash "$bootstrap" install
```

The default capture interval is 15 minutes.  A supported alternative can be
selected by adding, for example, `--interval-minutes 60` after `install`.

## Sidebar install command

After the companion installation passes, use the already verified bootstrap:

```bash
bash /tmp/pihole-speedtest-v6-bootstrap.sh install-adapter
```

The adapter action verifies the companion commit recorded by the installed
manifest.  It does not assume that the companion and bootstrap were published
from the same source commit, and it does not upgrade the companion.

Automatic origin detection is suitable for a typical HTTP installation opened
by the Pi's primary address.  A hostname, HTTPS, reverse proxy, or nonstandard
origin must be supplied explicitly:

```bash
bash /tmp/pihole-speedtest-v6-bootstrap.sh install-adapter \
  --pihole-origin https://pihole.example.net \
  --companion-url https://speedtest.example.net
```

## Removal commands

If the sidebar adapter is installed, remove and verify that independent layer
first:

```bash
bash /tmp/pihole-speedtest-v6-bootstrap.sh remove-adapter
```

Then remove the companion while preserving all user data:

```bash
bash /tmp/pihole-speedtest-v6-bootstrap.sh uninstall
```

If `/tmp` has been cleared, repeat the download and bootstrap checksum steps
from the production install command, then replace the final `install` action
with the required removal action.

Permanent deletion remains a separate command and must never be combined with
default uninstall:

```bash
bash /tmp/pihole-speedtest-v6-bootstrap.sh purge-data \
  --confirm 'DELETE /var/lib/pihole-speedtest'
```

## Supported actions

The one bootstrap exposes five distinct actions:

- `install` installs the unprivileged companion service and collection timer;
- `install-adapter` separately installs the Pi-hole Web v6.6 sidebar adapter;
- `remove-adapter` verifies and removes only the sidebar adapter;
- `uninstall` removes services, application files, and the service account but
  preserves all user data;
- `purge-data` is a separate destructive action requiring the exact
  confirmation `DELETE /var/lib/pihole-speedtest`.

## Dynamic device configuration

The installer does not contain a private network address.  It detects the
device's primary address at runtime for a typical HTTP Pi-hole installation.
Users with a hostname, HTTPS, reverse proxy, or nonstandard origin can provide
their own `--pihole-origin` and `--companion-url` values.

## Fail-closed checks

Installation refuses to continue unless all of the following are true:

- the release bundle checksum and source marker match;
- the architecture is `aarch64` or `x86_64`;
- Python 3.9 or newer is available;
- Pi-hole Core v6 is installed;
- the official Ookla CLI is installed at `/usr/bin/speedtest`;
- no conflicting active companion installation exists;
- preserved data comes from a verified uninstall or failed installation;
- any preserved SQLite database passes `PRAGMA integrity_check`;
- the selected collection interval is supported.

The optional adapter retains its stricter Pi-hole Web v6.6 layout and checksum
gates.

## Preservation and recovery

Default uninstall creates and verifies an online SQLite recovery copy before
removing services.  It retains `/var/lib/pihole-speedtest`, including history,
settings, backups, migration reports, manifests, and prior recovery evidence.
A later install reuses that directory and verifies the database before starting
services.  Installation and removal traps restore service files after a partial
failure without deleting user data.

The purge action is unavailable while any application, unit, environment file,
or service account remains.  It also refuses data without a verified uninstall
marker.

## Acceptance still required

- clean Raspberry Pi 3 ARM64 installation;
- separate sidebar installation and exact removal;
- interrupted-install rollback and repeat invocation;
- default uninstall with unchanged history and settings;
- reinstall using the preserved history;
- reboot with dashboard and timer continuity;
- explicit purge test using disposable data only.
