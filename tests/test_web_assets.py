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
