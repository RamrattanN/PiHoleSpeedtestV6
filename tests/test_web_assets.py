import unittest
from importlib.resources import files


class WebAssetTests(unittest.TestCase):
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
        self.assertEqual(page.count("data-run-speedtest"), 1)
        navigation = page.split('<nav class="view-navigation"', 1)[1].split(
            "</nav>", 1
        )[0]
        self.assertIn("data-run-speedtest", navigation)
        self.assertIn('class="run-speedtest-button"', navigation)
        self.assertNotIn("<details", page)
        self.assertNotIn("<summary", page)
        self.assertEqual(page.count('class="panel setup-panel'), 4)
        self.assertIn('postJson("/api/collect", {})', script)
        self.assertNotIn("admin-token", page)
        self.assertNotIn("Authorization", script)
        self.assertIn('fetch("/api/collection-status"', script)
        self.assertIn("metric-download", page)
        self.assertIn("metric-upload", page)
        self.assertIn("metric-latency", page)
        self.assertIn("metric-jitter", page)
        styles = web.joinpath("styles.css").read_text(encoding="utf-8")
        self.assertIn("--metric-start", styles)
        self.assertIn(".metric-clock", styles)
        self.assertIn("justify-content: space-between", styles)
        self.assertIn(".setup-panel-title", styles)
        self.assertIn('byId("open-help")', script)
        self.assertIn("chartMaximum(allRecords", script)
        self.assertIn('data-zoom', page)
        self.assertIn('id="history-tooltip"', page)
        self.assertIn('id="latency-tooltip"', page)
        self.assertIn('canvas.addEventListener("pointermove"', script)
        self.assertIn("showChartTooltip", script)
        self.assertIn("series.label", script)
        self.assertIn('get("embed") === "1"', script)
        self.assertIn('window.location.hash === "#setup"', script)
        self.assertIn("body.embedded", web.joinpath("styles.css").read_text(encoding="utf-8"))
