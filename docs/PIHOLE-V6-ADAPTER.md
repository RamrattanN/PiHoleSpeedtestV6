# Pi-hole Web v6.6 adapter

## Purpose

The optional adapter places a native `Speedtest` group in the authenticated
Pi-hole sidebar.  Its submenu contains `Overview` and `Setup`.  Each destination
uses Pi-hole's normal header, sidebar, content wrapper, theme, and footer while
displaying an embedded view from the independent companion service.

The embedded view keeps a compact Ramrattan identity and manual speed-test
control while omitting the standalone dashboard's larger duplicate header and
navigation.

Charts retain their real time scale in the embedded view.  Routine timing
variation does not create synthetic chart points.  Substantial collection
outages remain blank, and line charts break across them.  Nothing is added to
SQLite history, the measurement table, health counts, or CSV exports.

The adapter does not move measurement data into Pi-hole, change FTL, change
DNS, or make Pi-hole responsible for collection and scheduling.

## Supported boundary

The first adapter supports Pi-hole Web `v6.6` only.  Installation refuses:

- any other declared Web version;
- a missing or unrecognized `scripts/lua/sidebar.lp` layout;
- existing adapter markers;
- pre-existing adapter page paths;
- unsafe companion URLs.

The installed Raspberry Pi layout passed disposable-copy validation and guarded
live installation against the official v6.6 structure.  Future installation or
repair work must reconfirm the live checksum and version immediately before any
change.

## Companion frame policy

The companion dashboard defaults to `frame-ancestors 'self'`.  Embedding must
be enabled for the exact Pi-hole origin through
`/etc/default/pihole-speedtest-v6`:

```text
PIHOLE_SPEEDTEST_FRAME_ANCESTORS=http://pihole.example.test
```

The value is an origin, not a URL path.  HTTPS Pi-hole pages cannot embed an
HTTP companion because browsers block mixed content.  Version 1.0.6 rc.5
detects native Pi-hole HTTPS, serves the companion through HTTPS on port 8765,
and requires both origins to use the same scheme.  The companion receives
`/etc/pihole/tls.pem` as a restricted systemd credential rather than direct
filesystem access.  Nonstandard reverse-proxy origins must still be supplied
explicitly.

HTTP-only Pi-hole installations retain an HTTP companion and HTTP wrapper.
When Pi-hole has native HTTPS, the configured HTTPS origin is canonical.  The
Overview and Setup wrappers redirect HTTP IP addresses, old bookmarks, and
other noncanonical origins to that HTTPS origin before loading the iframe.
This supports both installation types without allowing an insecure HTTP parent
through the companion's strict `frame-ancestors` policy.

Pi-hole's CSP may omit a `frame-src` directive.  In that case, `default-src`
is the browser fallback and a companion service on another port is blocked.
The guarded adapter installer preserves the existing policy and adds only the
exact, validated companion origin as `frame-src`.  Before making the change,
it archives Pi-hole's complete `webserver.headers` array.  Removal verifies
that the installed array has not changed and then restores the archived array
exactly.  It refuses to overwrite headers changed by an administrator after
adapter installation.

## Isolated installation shape

The command below is documentation of the intended isolated test.  It is not
approval to run against the live `/var/www/html/admin` tree.

```bash
pihole-speedtest adapter-install \
  --web-root /temporary/pihole-admin-copy \
  --web-version v6.6 \
  --companion-url http://pihole.example.test:8765 \
  --pihole-origin http://pihole.example.test \
  --backup-root /temporary/adapter-backups
```

The command creates a timestamped recovery directory containing:

- the exact pre-install sidebar;
- SHA-256 checksums for the original and installed sidebar;
- checksums for both created adapter pages;
- the tested version, web root, companion URL, and canonical Pi-hole origin;
- the exact Pi-hole web header array before and after the narrow `frame-src`
  addition;
- a manifest used for verified removal.

## Verified removal shape

```bash
pihole-speedtest adapter-remove \
  --manifest /temporary/adapter-backups/TIMESTAMP/manifest.json
```

Removal first verifies that the installed sidebar, adapter pages, and recovery
copy still match the recorded checksums.  It refuses restoration if any of them
changed after installation.  A successful removal restores the original
sidebar byte for byte, deletes only the two adapter-created pages, and writes a
removal record.

## Guarded live lifecycle

The live Raspberry Pi uses the repository wrappers rather than invoking the
low-level adapter commands directly:

```bash
sudo bash ./scripts/install_pihole_adapter.sh \
  --expected-source-commit APPROVED_SOURCE_SHA \
  --expected-installed-commit INSTALLED_SOURCE_SHA \
  --companion-url http://pihole.example.test:8765 \
  --pihole-origin http://pihole.example.test
```

Replace `pihole.example.test` with the hostname or IP address that resolves to
the user's own Pi-hole.  The installer does not contain or assume a private
network address.

The installer fails closed unless the approved source and installed companion
commits match, Pi-hole Web is exactly v6.6, the pristine sidebar checksum is
recognized, the adapter targets are absent, both companion services are
healthy, the companion frame policy permits the exact Pi-hole origin, and the
Pi-hole header policy can be extended with the exact companion origin without
replacing an existing `frame-src`.  It records the adapter recovery manifest in
both deployment manifests so later companion upgrades can verify and preserve
the installed adapter state.

Verified live removal uses the recorded recovery manifest automatically:

```bash
sudo bash ./scripts/remove_pihole_adapter.sh
```

Removal still refuses if Pi-hole or another process changed any installed
adapter file after installation.  This avoids overwriting a later Pi-hole Web
update with an older sidebar copy.

## Live acceptance requirements

Before touching the live Pi-hole web tree:

1. Confirm the installed Web version is still `v6.6`.
2. Resolve the actual web root and sidebar path read-only.
3. Copy the complete installed web tree to a disposable directory.
4. Install and remove the adapter against that copy.
5. Verify exact sidebar restoration and the absence of leftover pages.
6. Run the companion on its final Pi address and temporary service port.
7. Verify both CSP directions and both embedded pages from another LAN device.
8. Capture Pi-hole DNS, FTL, dashboard, and resource baselines.
9. Create an additional recovery point.
10. Obtain explicit approval for the live adapter installation.

These requirements were satisfied before the live installation.  The initial
embedded-page defects in LCARS menu styling and Pi-hole `frame-src` policy were
corrected through the same recovery-backed workflow.  The owner accepted the
live Overview and Setup integration with version `0.1.0.dev4` on September 23,
2026.  Companion upgrades preserve and verify the independently reversible
adapter state.

## Verified device-copy rehearsal

The install and removal workflow passed against a disposable copy of the
installed Pi-hole Web v6.6 tree on September 22, 2026 local time.  Evidence is
preserved on the Raspberry Pi at:

```text
/home/Nilesh/pihole-speedtest-adapter-rehearsal-20260923T014511Z
```

Verified outcomes:

- the live and copied `sidebar.lp` matched the official v6.6 SHA-256 checksum
  `83943cbdf5258fe43e819108a5135e070d6742e273753ba398a8d28e1a008fdb`;
- the adapter installed only in the disposable web tree;
- both `Overview` and `Setup` page targets were created;
- the recovery manifest was created and accepted by verified removal;
- removal restored `sidebar.lp` byte for byte;
- both created pages were removed;
- the live sidebar checksum remained unchanged;
- FTL continued listening on port 53 and Pi-hole blocking remained enabled.
