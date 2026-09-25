import json
import shutil
import subprocess
import unittest
from importlib.resources import files


class WebAssetTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is needed to run chart logic")
    def test_zoom_scales_visible_values_and_widens_bars_without_overlap(self):
        script = files("pihole_speedtest").joinpath("web", "app.js").read_text(encoding="utf-8")
        check = r'''
const vm = require("node:vm");
const assert = require("node:assert/strict");
const script = JSON.parse(process.argv[1]).replace(/installControls\(\); load\(\);\s*$/, "");
const context = vm.createContext({
  localStorage: { getItem: () => null },
  window: { addEventListener: () => {} },
});
vm.runInContext(script, context);
const results = vm.runInContext(`(() => {
  const series = [{ field: "latency_ms" }, { field: "jitter_ms" }];
  const records = [
    { latency_ms: 220, jitter_ms: 2 },
    { latency_ms: 10, jitter_ms: 3 },
    { latency_ms: 13, jitter_ms: 4 },
  ];
  const wide = { intervalMs: 900000, duration: 86400000 };
  const zoomed = { intervalMs: 900000, duration: 10800000 };
  const width = 1600;
  return {
    allMaximum: chartMaximum(records, series, 10),
    visibleMaximum: chartMaximum(records.slice(1), series, 10),
    wideBar: chartBarGroupWidth(wide, width, 17),
    zoomedBar: chartBarGroupWidth(zoomed, width, 180),
    closeBar: chartBarGroupWidth(zoomed, width, 8),
    loneBar: chartBarGroupWidth(zoomed, width, chartBarSpacing(zoomed, [500])),
  };
})()`, context);
assert.ok(results.allMaximum >= 242);
assert.equal(results.visibleMaximum, 15);
assert.ok(results.zoomedBar > results.wideBar * 3);
assert.equal(results.zoomedBar, 56);
assert.ok(results.closeBar <= 6);
assert.equal(results.loneBar, 56);
'''
        subprocess.run(["node", "-e", check, json.dumps(script)], check=True, timeout=10)

    def test_assets_are_local_only(self):
        web = files("pihole_speedtest").joinpath("web")
        for name in ("index.html", "app.js", "styles.css"):
            content = web.joinpath(name).read_text(encoding="utf-8")
            self.assertNotIn("http://", content, name)
            self.assertNotIn("https://", content, name)
            self.assertNotIn("//cdn.", content, name)

    def test_single_measurement_chart_has_visible_point(self):
        script = (
            files("pihole_speedtest")
            .joinpath("web", "app.js")
            .read_text(encoding="utf-8")
        )
        self.assertIn('count === 1 ? "measurement" : "measurements"', script)
        self.assertIn("context.arc(x, y, 4", script)

    def test_latency_and_jitter_have_a_dedicated_chart(self):
        web = files("pihole_speedtest").joinpath("web")
        page = web.joinpath("index.html").read_text(encoding="utf-8")
        script = web.joinpath("app.js").read_text(encoding="utf-8")

        self.assertIn("Latency and jitter", page)
        self.assertIn('id="latency-chart"', page)
        self.assertIn('field: "latency_ms"', script)
        self.assertIn('field: "jitter_ms"', script)

    def test_ramrattan_logo_is_local_and_accessible(self):
        web = files("pihole_speedtest").joinpath("web")
        page = web.joinpath("index.html").read_text(encoding="utf-8")
        logo = web.joinpath("ramrattan-logo.png").read_bytes()

        self.assertIn('src="/ramrattan-logo.png"', page)
        self.assertIn('alt="Ramrattan"', page)
        self.assertTrue(logo.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_setup_and_chart_controls_are_present(self):
        web = files("pihole_speedtest").joinpath("web")
        page = web.joinpath("index.html").read_text(encoding="utf-8")
        script = web.joinpath("app.js").read_text(encoding="utf-8")

        self.assertIn('data-view="setup"', page)
        self.assertIn('data-chart-mode="bar"', page)
        self.assertIn('id="show-table"', page)
        self.assertIn('href="/api/export.csv"', page)
        self.assertIn("Every 15 minutes", page)
        self.assertIn("Once a day", page)
        self.assertIn('id="reset-confirmation"', page)
        self.assertIn('id="help-dialog"', page)
        self.assertIn("Run speed test now", page)
        self.assertIn("data-run-speedtest", page)
        self.assertEqual(page.count("data-run-speedtest"), 2)
        navigation = page.split('<nav class="view-navigation"', 1)[1].split(
            "</nav>", 1
        )[0]
        self.assertIn("data-run-speedtest", navigation)
        self.assertIn('class="run-speedtest-button"', navigation)
        embedded_toolbar = page.split('<div class="embedded-toolbar"', 1)[1].split(
            "</div>\n\n    <nav", 1
        )[0]
        self.assertIn('src="/ramrattan-logo.png"', embedded_toolbar)
        self.assertIn("Ramrattan Network Tools", embedded_toolbar)
        self.assertIn("data-run-speedtest", embedded_toolbar)
        self.assertNotIn("<details", page)
        self.assertNotIn("<summary", page)
        self.assertEqual(page.count('class="panel setup-panel'), 4)
        self.assertIn('id="app-version"', page)
        self.assertIn('setText("app-version", `version ${health.version}`)', script)
        self.assertIn('postJson("/api/collect", {})', script)
        self.assertNotIn("admin-token", page)
        self.assertNotIn("Authorization", script)
        self.assertIn('fetch("/api/collection-status"', script)
        self.assertIn("metric-download", page)
        self.assertIn("metric-upload", page)
        self.assertIn("metric-latency", page)
        self.assertIn("metric-jitter", page)
        styles = web.joinpath("styles.css").read_text(encoding="utf-8")
        self.assertIn(".app-version", styles)
        self.assertIn("--metric-start", styles)
        self.assertIn(".metric-clock", styles)
        self.assertIn("justify-content: space-between", styles)
        self.assertIn(".setup-panel-title", styles)
        self.assertIn('byId("open-help")', script)
        self.assertIn("chartMaximum(plottedRecords", script)
        self.assertIn('data-zoom', page)
        self.assertIn('id="history-tooltip"', page)
        self.assertIn('id="latency-tooltip"', page)
        self.assertIn('canvas.addEventListener("pointermove"', script)
        self.assertIn("showChartTooltip", script)
        self.assertIn("series.label", script)
        self.assertIn("function chartTimeline(records)", script)
        self.assertIn("function chartBarSpacing(timeline, xPositions)", script)
        self.assertIn("const DEFAULT_CHART_WINDOW_MS = 24 * 60 * 60 * 1000", script)
        self.assertIn("function setDefaultZoomRange()", script)
        self.assertIn("end - DEFAULT_CHART_WINDOW_MS", script)
        self.assertIn("function chartTimeTicks(timeline, chartWidth)", script)
        self.assertIn("context.lineTo(x, padding.top + chartHeight)", script)
        self.assertIn("function chartBarGroupWidth(timeline, chartWidth, measuredSpacing)", script)
        self.assertIn("Math.min(expectedSpacing, measuredSpacing)", script)
        self.assertIn("const BAR_GROUP_GAP_PX = 2", script)
        self.assertIn("const BAR_GROUP_MAX_WIDTH_PX = 56", script)
        self.assertIn("Math.min(BAR_GROUP_GAP_PX, availableSpacing * 0.5)", script)
        self.assertIn("Math.min(BAR_GROUP_MAX_WIDTH_PX, availableSpacing - reservedGap)", script)
        self.assertNotIn("function chartBarGroupWidth(timeline, xPositions, index", script)
        self.assertNotIn("availableSpacing * 0.72", script)
        self.assertIn("function drawBarGroup(context, x, chartBottom, bars, groupWidth)", script)
        self.assertIn("Math.max(...heights) - Math.min(...heights) <= 3", script)
        self.assertIn("right.height - left.height", script)
        self.assertIn("groupWidth * Math.max(0.42, 0.68", script)
        self.assertNotIn("function buildChartRecords(records)", script)
        self.assertNotIn("synthetic_zero", script)
        self.assertIn("const cadenceMs = Math.max(intervalMs, medianDelta)", script)
        self.assertIn("gapThresholdMs: cadenceMs * 2.5", script)
        self.assertIn("elapsed > timeline.gapThresholdMs", script)
        self.assertNotIn('context.fillText("No data"', script)
        self.assertNotIn("no-data", script)
        self.assertIn("xPositions.reduce", script)
        self.assertIn("collectionIntervalMinutes = Number(settings.collection_interval_minutes)", script)
        self.assertIn('get("embed") === "1"', script)
        self.assertIn('window.location.hash === "#setup"', script)
        self.assertIn("body.embedded", web.joinpath("styles.css").read_text(encoding="utf-8"))
        self.assertIn("body.embedded .embedded-toolbar", styles)
