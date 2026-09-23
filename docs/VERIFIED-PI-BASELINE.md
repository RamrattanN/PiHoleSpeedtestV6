# Verified Raspberry Pi baseline

## Scope

This baseline was captured on September 22, 2026, before deploying the new
companion.  Read-only inspection was followed by an explicitly approved,
recoverable pause of the legacy speed-test cron entry.

## Platform

| Item | Verified value |
| --- | --- |
| Device | Raspberry Pi 3 Model B Plus Rev 1.3 |
| Architecture | ARM64 (`aarch64`) |
| Operating system | Debian 12 Bookworm |
| Kernel | 6.12.20 Raspberry Pi v8 |
| Python | 3.11.2 |
| Pi-hole Core | 6.4.3 |
| Pi-hole Web | 6.6 |
| Pi-hole FTL | 6.7.1 |
| Official Ookla CLI | 1.2.0.84, Linux ARM64 |
| Root filesystem | 29 GB total, 16 GB available |
| Available memory | 465 MiB at inspection |
| CPU temperature | 46.2 C at inspection |
| Network | Ethernet; Wi-Fi disabled |

Pi-hole FTL was active and enabled, port 53 was listening on IPv4 and IPv6,
and blocking was enabled before and after the legacy schedule was paused.

## Legacy installation findings

The prototype installed in September 2025 was still collecting one official
Ookla measurement every five minutes through the root crontab.  Its web assets
remained under `/var/www/html/speedtest`, but Pi-hole v6 returned HTTP 404 and
HTTPS 404 for `/speedtest/`.

The finding explains the observed failure mode: collection survived, while the
dashboard stopped being reachable after Pi-hole's web architecture changed.

The legacy installation included:

- `/usr/local/bin/pihole-speedtest`;
- `/etc/default/pihole-speedtest`;
- CSV and JSON data under `/etc/pihole/speedtest`;
- a legacy log at `/etc/pihole/speedtest.log`;
- HTML and JavaScript under `/var/www/html/speedtest`.

The CSV was approximately 7.5 MB.  Inspection identified at least one row with
blank measurement fields, confirming that failed or unparseable results could
be recorded by the legacy shell runner.

## Recovery point and pause

The tagged root cron entry was removed after owner approval.  No other root cron
entry existed.  Subsequent checks crossed the former five-minute boundary and
confirmed:

- the CSV and JSON remained byte-identical to the recovery snapshot;
- no speed-test process was running;
- the root crontab remained empty;
- Pi-hole FTL and blocking remained healthy.

The recovery package exists on both the Raspberry Pi and the owner's Mac.  The
compressed archive SHA-256 is:

```text
4ca8c8bbb8bd02e1c67eff200589b947d6a35c018d995b4d87edbffb817fbfdc
```

The legacy files remain installed but inactive.  They must not be removed until
history migration, isolated companion acceptance, and rollback verification are
complete.

## Migration contract

`pihole-speedtest import-legacy-csv` will:

- require the complete expected legacy header;
- verify that epoch and ISO timestamps agree;
- tolerate up to five seconds between the legacy epoch and ISO timestamps;
- normalize accepted timestamps to UTC;
- require finite, non-negative measurements;
- stream rows without loading the full CSV into memory;
- skip exact duplicates on repeat imports;
- preserve and report distinct measurements that share a timestamp;
- report row numbers and reasons for malformed records;
- return a non-zero review status when any row is rejected.

The first import will use a temporary SQLite database and a copied CSV.  It will
not read from or write to the live legacy data directory.

## Legacy-history audit

The first copied-history validation processed 98,814 source rows.  It safely
imported 98,598 rows and rejected 216 for review.  A second pass inserted zero
rows, recognized all 98,598 imported rows as duplicates, and reproduced the
same 216 rejections.

Inspection of every rejected source row established:

- 187 rows contain timestamps but no download, upload, latency, jitter, server,
  or interface result and must remain rejected;
- one complete measurement has a four-second difference between its epoch and
  ISO timestamps and is recoverable within the documented tolerance;
- 28 complete, distinct measurements share one legacy timestamp and can be
  preserved without overwriting one another.

The refined importer was then accepted on the owner's Mac against a new
temporary SQLite database.  The clean first pass preserved 98,627
measurements, reported 28 timestamp collisions, and rejected only the 187
empty rows.  The second pass inserted zero rows, recognized all 98,627
measurements as duplicates, reported no new collisions, and left the database
count unchanged at 98,627.

## Pi-hole Web v6.6 adapter rehearsal

On September 22, 2026 local time, the version-gated sidebar adapter was tested
against a disposable copy of `/var/www/html/admin`.  The installed sidebar
matched the official Pi-hole Web v6.6 SHA-256 checksum:

```text
83943cbdf5258fe43e819108a5135e070d6742e273753ba398a8d28e1a008fdb
```

The adapter installed into the copy, created its two wrapper pages and recovery
manifest, and then removed successfully.  Removal restored the copied sidebar
byte for byte and removed both created pages.  The live web tree was unchanged,
FTL remained listening on port 53, and Pi-hole blocking remained enabled.

Evidence directory on the Raspberry Pi:

```text
/home/Nilesh/pihole-speedtest-adapter-rehearsal-20260923T014511Z
```

## Dashboard-only staged installation

On September 22, 2026 local time, commit
`62fbcc88fc09b9f4d209a8fcec753a895665f7e0` was installed through the guarded
dashboard-only installer.  The installer preserved evidence at:

```text
/var/lib/pihole-speedtest-install-recovery/20260923T020244Z
```

Independent post-install verification established:

- `pihole-speedtest-dashboard.service` was active and enabled with zero
  restarts;
- the process ran as the dedicated `pihole-speedtest` user and group;
- the service listened on `0.0.0.0:8765`;
- `/api/health` reported version `0.1.0.dev0`, 98,627 measurements, and the
  expected final legacy timestamp;
- SQLite `PRAGMA integrity_check` returned `ok`;
- the migration recorded 98,627 inserted measurements, 187 rejected empty
  rows, and 28 preserved timestamp collisions;
- the content security policy allowed framing only from `self` and
  `http://192.168.2.14`;
- no collection timer was installed or active;
- the root crontab remained empty;
- neither live adapter page existed;
- the live sidebar retained SHA-256
  `83943cbdf5258fe43e819108a5135e070d6742e273753ba398a8d28e1a008fdb`;
- Pi-hole FTL remained listening on port 53 and blocking remained enabled.

The collection schedule and live sidebar adapter were initially kept behind
separate approval gates.

## Scheduled collection and approved companion upgrades

The 15-minute systemd collection timer was subsequently installed, enabled,
and verified.  Scheduled collection completed successfully through the official
Ookla CLI while the dashboard continued running as the dedicated unprivileged
service account.  The legacy root crontab remained empty.

The owner-approved keyless dashboard and the later interface refinement were
deployed through guarded upgrades.  The final verified application commit was:

```text
897e7d2a8e699f65e762ab6a8908f002443f2abb
```

The interface refinement aligned `Run speed test now` with the primary
navigation, kept all Setup sections permanently expanded, and added measurement
tooltips to both charts.  Post-upgrade health reported 98,632 preserved
measurements and the collection timer active and enabled.  Recovery evidence is
stored at:

```text
/var/lib/pihole-speedtest-upgrade-recovery/20260923T034009Z
```

All 52 automated tests and GitHub CI run 16 passed for the deployed application
revision.  The owner then completed visual testing and approved the result to
specification.  The live Pi-hole sidebar adapter remains absent and is tracked
separately in
[issue #2](https://github.com/RamrattanN/PiHoleSpeedtestV6/issues/2).

## Interface-label follow-up

The first measurements created by the systemd collector preserved all speed,
latency, jitter, server, and timestamp values, but the installed Ookla Linux CLI
did not include an interface name in its JSON result.  Those rows therefore
display `Not available`; this is a metadata omission, not a failed speed test.

The collector now falls back to the interface carrying Linux's active IPv4
default route when Ookla omits the name.  Automated coverage verifies both the
fallback and `/proc/net/route` parsing.  Existing historical rows are left
unchanged to preserve source fidelity.  Live acceptance remains pending a
guarded companion upgrade and one new Raspberry Pi measurement that records
`eth0`.
