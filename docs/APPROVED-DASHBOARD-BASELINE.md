# Approved dashboard baseline

> Version `0.1.0.dev4` remains the approved historical baseline described on
> this page.  Version `1.0.1` is the production maintenance revision.  It keeps
> substantial collection outages blank and breaks line charts across them
> without adding labels, shaded overlays, or synthetic measurements.  This
> page will be rebaselined only after owner visual acceptance.

## Decision

The Pi-hole Speedtest dashboard presented on September 22, 2026 is the
owner-approved visual and interaction baseline for continued development.
Initial approval was completed against the local validation service with
98,627 imported legacy measurements and a one-hour collection interval.

The owner approved the latest baseline on September 23, 2026 after live
Raspberry Pi verification of version `0.1.0.dev4` at commit
`4bd209c0d41c70dd7235ace2b2640be27450c052`.  The accepted revision includes
the embedded Ramrattan identity and manual-test control, true timestamp
spacing, labelled no-data gaps, chart mouseover details, and adaptive layered
bars that separate equal or nearly equal values.

This acceptance establishes the go-to interface and includes the installed,
reversible Pi-hole Web v6.6 navigation adapter.  It does not authorize other
changes to Pi-hole Core, Web, FTL, configuration, or data.

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
- align `Run speed test now` with the top-level navigation and keep it at the
  right edge on desktop widths;
- retain a compact Ramrattan identity and `Run speed test now` control when the
  dashboard is embedded in Pi-hole;
- keep the connection summary and charts in Overview;
- keep display, export, scheduling, and destructive controls in Setup;
- keep every Setup section expanded and do not provide section-collapse
  controls;
- avoid modifying or replacing the native Pi-hole dashboard for the companion
  core experience.

## Required chart behavior

- position measurements by their actual collection timestamps instead of by
  equal record spacing;
- leave expected but uncollected measurement intervals blank and label visible
  gaps as `No data` rather than inventing or interpolating performance values;
- break line charts across missing intervals so collection gaps remain visible;

- provide separate download/upload and latency/jitter charts;
- provide line and bar presentation modes;
- layer paired bars on a shared timestamp, with the taller value behind and a
  narrower shorter value in front, while showing equal or nearly equal values
  side by side so neither series is hidden;
- apply horizontal time-axis zoom without rescaling the y-axis;
- support zoom controls, mouse-wheel zoom, and horizontal drag navigation;
- keep series names and colors identifiable through local legends;
- show the measurement time and chart-series values when a user points to a
  chart measurement;
- render a visible point when only one measurement exists.

## Required data controls

- allow the recent-measurements table to be shown or hidden;
- export the complete history as chronological CSV data;
- allow capture intervals of 15, 30, 60, 120, 240, 360, 720, or 1,440
  minutes;
- use 60 minutes as the default capture interval;
- allow schedule changes directly from Setup without a separate key;
- provide a `Run speed test now` control directly on Overview;
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
collection and a guarded application upgrade have passed live verification
with history preserved.  Reboot testing, restore testing, and complete release
acceptance remain open.  The approved 15-minute collection interval is active.
The live Pi-hole navigation adapter has completed owner acceptance and remains
an independently reversible deployment layer.
