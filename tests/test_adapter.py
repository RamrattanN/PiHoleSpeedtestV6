import json
import stat
import tempfile
import unittest
from pathlib import Path

from pihole_speedtest.adapter import (
    AdapterError,
    BEGIN_MARKER,
    install_adapter,
    remove_adapter,
)


SIDEBAR = """<aside>
<ul class="sidebar-menu" data-widget="tree">
                <!-- Donate button -->
</ul>
</aside>
"""


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "admin"
        self.sidebar = self.root / "scripts" / "lua" / "sidebar.lp"
        self.sidebar.parent.mkdir(parents=True)
        self.sidebar.write_text(SIDEBAR, encoding="utf-8")
        self.backups = Path(self.temporary.name) / "backups"

    def tearDown(self):
        self.temporary.cleanup()

    def install(self):
        return install_adapter(
            self.root,
            "v6.6",
            "http://pihole.example.test:8765",
            "http://pihole.example.test",
            self.backups,
        )

    def test_install_and_remove_restore_exact_sidebar(self):
        manifest_path = self.install()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertIn(BEGIN_MARKER, self.sidebar.read_text(encoding="utf-8"))
        self.assertIn("Speedtest", self.sidebar.read_text(encoding="utf-8"))
        self.assertIn(
            'class="menu-system menu-speedtest treeview',
            self.sidebar.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "?embed=1#overview",
            (self.root / "speedtest.lp").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "?embed=1#setup",
            (self.root / "speedtest-setup.lp").read_text(encoding="utf-8"),
        )
        overview = (self.root / "speedtest.lp").read_text(encoding="utf-8")
        self.assertNotIn('\n                    src="', overview)
        self.assertIn(
            'data-src="http://pihole.example.test:8765/?embed=1#overview"',
            overview,
        )
        self.assertIn(
            'const canonicalOrigin = "http://pihole.example.test";',
            overview,
        )
        self.assertIn("window.location.origin !== canonicalOrigin", overview)
        self.assertIn("window.location.replace(", overview)
        self.assertIn("frame.src = frame.dataset.src", overview)
        self.assertEqual(manifest["web_version"], "v6.6")
        self.assertEqual(
            manifest["pihole_origin"],
            "http://pihole.example.test",
        )
        self.assertEqual(
            stat.S_IMODE(self.sidebar.stat().st_mode),
            0o644,
        )
        self.assertEqual(
            stat.S_IMODE((self.root / "speedtest.lp").stat().st_mode),
            0o644,
        )
        self.assertEqual(
            stat.S_IMODE((self.root / "speedtest-setup.lp").stat().st_mode),
            0o644,
        )

        remove_adapter(manifest_path)

        self.assertEqual(self.sidebar.read_text(encoding="utf-8"), SIDEBAR)
        self.assertFalse((self.root / "speedtest.lp").exists())
        self.assertFalse((self.root / "speedtest-setup.lp").exists())
        self.assertTrue(manifest_path.with_name("removal.json").is_file())

    def test_unknown_version_is_refused_without_changes(self):
        with self.assertRaisesRegex(AdapterError, "unsupported"):
            install_adapter(
                self.root,
                "v6.7",
                "http://pihole.example.test:8765",
                "http://pihole.example.test",
                self.backups,
            )
        self.assertEqual(self.sidebar.read_text(encoding="utf-8"), SIDEBAR)
        self.assertFalse(self.backups.exists())

    def test_unrecognized_layout_is_refused(self):
        self.sidebar.write_text("<html>different</html>", encoding="utf-8")
        with self.assertRaisesRegex(AdapterError, "unrecognized"):
            self.install()

    def test_second_install_is_refused(self):
        self.install()
        with self.assertRaisesRegex(AdapterError, "markers already exist"):
            self.install()

    def test_remove_refuses_post_install_change(self):
        manifest = self.install()
        self.sidebar.write_text(
            self.sidebar.read_text(encoding="utf-8") + "changed",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(AdapterError, "changed after"):
            remove_adapter(manifest)

    def test_companion_url_rejects_unsafe_values(self):
        for value in (
            "file:///tmp/dashboard",
            "http://user:secret@example.test",
            "http://example.test/?unsafe=1",
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(AdapterError, "companion URL"):
                    install_adapter(
                        self.root,
                        "v6.6",
                        value,
                        "http://pihole.example.test",
                        self.backups,
                    )

    def test_noncanonical_http_access_redirects_to_https_origin(self):
        install_adapter(
            self.root,
            "v6.6",
            "https://pi.hole:8765",
            "https://pi.hole",
            self.backups,
        )

        for name in ("speedtest.lp", "speedtest-setup.lp"):
            with self.subTest(name=name):
                page = (self.root / name).read_text(encoding="utf-8")
                self.assertIn(
                    'const canonicalOrigin = "https://pi.hole";',
                    page,
                )
                self.assertIn(
                    "canonicalOrigin\n                + window.location.pathname",
                    page,
                )
                self.assertIn("frame.src = frame.dataset.src", page)
                self.assertNotIn('\n                    src="', page)

    def test_default_https_port_is_normalized_to_prevent_redirect_loop(self):
        manifest_path = install_adapter(
            self.root,
            "v6.6",
            "https://pi.hole:8765",
            "https://pi.hole:443",
            self.backups,
        )

        page = (self.root / "speedtest.lp").read_text(encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertIn('const canonicalOrigin = "https://pi.hole";', page)
        self.assertEqual(manifest["pihole_origin"], "https://pi.hole")

    def test_pihole_origin_rejects_unsafe_values(self):
        for value in (
            "file:///tmp/admin",
            "https://user:secret@pi.hole",
            "https://pi.hole/admin",
            "https://pi.hole/?unsafe=1",
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(AdapterError, "Pi-hole origin"):
                    install_adapter(
                        self.root,
                        "v6.6",
                        "https://pi.hole:8765",
                        value,
                        self.backups,
                    )
