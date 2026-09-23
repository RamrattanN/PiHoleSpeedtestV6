# Approved dashboard baseline

## Decision

The Pi-hole Speedtest dashboard presented on September 22, 2026 is the
owner-approved visual and interaction baseline for continued development.
Approval was completed against the local validation service with 98,627
imported legacy measurements and a one-hour collection interval.

This acceptance establishes the go-to interface.  It does not authorize
production installation on the Raspberry Pi or changes to Pi-hole Core, Web,
FTL, configuration, or data.

## Required visual identity

- use the Ramrattan shield logo as a local application asset;
- use the `Ramrattan Network Tools` product-family label;
- use `Pi-hole Speedtest` as the application title;
- retain the dark blue branded header and dark dashboard surface;
- use blue, green, amber, and red metric cards for download, upload, latency,
  and jitter respectively;
- retain a clear health indicator and functional Help control;
- remain usable on desktop and narrow browser widths.

## Required navigation and views

- provide top-level `Overview` and `Setup` navigation;
- keep the connection summary and charts in Overview;
- keep display, export, scheduling, and destructive controls in Setup;
- avoid modifying or replacing the native Pi-hole dashboard for the companion
  core experience.

## Required chart behavior

- provide separate download/upload and latency/jitter charts;
- provide line and bar presentation modes;
- apply horizontal time-axis zoom without rescaling the y-axis;
- support zoom controls, mouse-wheel zoom, and horizontal drag navigation;
- keep series names and colors identifiable through local legends;
- render a visible point when only one measurement exists.

## Required data controls

- allow the recent-measurements table to be shown or hidden;
- export the complete history as chronological CSV data;
- allow capture intervals of 15, 30, 60, 120, 240, 360, 720, or 1,440
  minutes;
- use 60 minutes as the default capture interval;
- require the administrator token for schedule changes;
- provide an administrator-token-protected `Run speed test now` control;
- show manual-test progress and refresh the dashboard after success;
- refuse overlapping manual and scheduled speed tests through one shared lock;
- require acknowledgement and the exact text `RESET` before reset;
- create and verify a recovery database before clearing active history.

## Regression rule

Automated checks must continue to cover the baseline's structural, security,
and data-safety requirements.  Material changes to branding, navigation,
chart interaction, settings, or reset safeguards require owner review before
this document is revised.

## Remaining deployment boundary

The accepted dashboard is now an unattended Raspberry Pi service.  Automated
collection, reboot testing, upgrade and restore testing, and complete release
acceptance remain open.  The owner approved a 15-minute initial collection
interval, subject to the guarded collector upgrade and live verification.  The
optional Pi-hole navigation adapter remains a separate, reversible checkpoint.
