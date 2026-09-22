# Origin and Pi-hole v6 gap analysis

## Provenance

This project modernizes the MIT-licensed
[`arevindh/pihole-speedtest`](https://github.com/arevindh/pihole-speedtest).
The original project combined a runner, an SQLite database, modified Pi-hole
Core scripts, and an AdminLTE dashboard fork.

Its installer synchronized the local Pi-hole Core and AdminLTE repositories
with compatible modified forks.  That delivered deep integration, but tied the
product to Pi-hole's internal repository and web-interface structure.

## Product contract recovered from the original

| Capability | Original | v6 direction |
| --- | --- | --- |
| Scheduled tests | Available | Retain with systemd timer |
| Manual tests | Available | Retain after safe HTTP control design |
| History | SQLite | Retain with a new independent schema |
| Dashboard chart | Embedded in AdminLTE | Full companion dashboard |
| Pi-hole dashboard presence | Native modification | Optional adapter |
| CSV export | Available | Restore after foundation |
| Server selection | Available | Restore after foundation |
| Status and logs | Available | Restore through service health and journal |
| Database flush/restore | Available | Replace with backup, restore, and retention |
| Multiple CLI engines | Available | Official Ookla first; others require adapters and tests |
| Update/reinstall | Mod Script | Safe package upgrade |
| Uninstall | Restored stock Pi-hole | Remove companion and adapter independently |
| Docker | Modified Pi-hole image | Companion container after bare-metal acceptance |

## Why the original no longer fits Pi-hole v6

The original installation model depended on Pi-hole Core scripts, AdminLTE,
Lighttpd-era paths, and version-matched modified forks.  Pi-hole v6 changed the
web and service architecture.  Repeating the fork-replacement model would
recreate the same upgrade risk.

## Current repository gaps at the foundation baseline

The pre-foundation prototype contained:

- a runner with invalid direct-execution formatting;
- fragile shell parsing for multiple incompatible CLI JSON formats;
- potentially invalid generated JSON and CSV quoting;
- a web page with invalid inline JavaScript;
- CDN references despite the stated local-only objective;
- local chart assets that were not installed or used consistently;
- three overlapping installation approaches;
- a root Dockerfile that still installed the original upstream mod;
- no pull-request test workflow;
- no documented upgrade, uninstall, backup, or rollback contract.

These findings make the old prototype unsuitable for the live Pi-hole.  The
companion foundation replaces the active path while retaining historical files
until their removal can be reviewed separately.
