import unittest

from pihole_speedtest.pihole_headers import HeaderPolicyError, allow_companion_frame


DEFAULT_HEADERS = [
    "X-DNS-Prefetch-Control: off",
    "Content-Security-Policy: default-src 'none'; connect-src 'self'; "
    "font-src 'self'; frame-ancestors 'none'; img-src 'self'; "
    "script-src 'self'; style-src 'self' 'unsafe-inline'; form-action 'self'",
    "X-Frame-Options: DENY",
]


class PiHoleHeaderTests(unittest.TestCase):
    def test_adds_only_exact_companion_frame_source(self):
        changed = allow_companion_frame(
            DEFAULT_HEADERS,
            "http://pihole.example.test:8765",
        )

        self.assertEqual(changed[0], DEFAULT_HEADERS[0])
        self.assertEqual(changed[2], DEFAULT_HEADERS[2])
        self.assertIn(
            "frame-src http://pihole.example.test:8765; frame-ancestors 'none'",
            changed[1],
        )
        self.assertIn("default-src 'none'", changed[1])

    def test_extends_verified_pihole_v6_6_policy(self):
        headers = [
            "X-DNS-Prefetch-Control: off",
            "Content-Security-Policy: default-src 'self' 'unsafe-inline';",
            "X-Frame-Options: DENY",
            "X-XSS-Protection: 0",
            "X-Content-Type-Options: nosniff",
            "Referrer-Policy: strict-origin-when-cross-origin",
        ]

        changed = allow_companion_frame(
            headers,
            "http://pihole.example.test:8765",
        )

        self.assertEqual(changed[:1], headers[:1])
        self.assertEqual(changed[2:], headers[2:])
        self.assertEqual(
            changed[1],
            "Content-Security-Policy: default-src 'self' 'unsafe-inline'; "
            "frame-src http://pihole.example.test:8765",
        )

    def test_rejects_existing_frame_source(self):
        headers = ["Content-Security-Policy: default-src 'none'; frame-src 'self'"]
        with self.assertRaisesRegex(HeaderPolicyError, "already defines frame-src"):
            allow_companion_frame(headers, "http://pihole.example.test:8765")

    def test_rejects_ambiguous_or_unsafe_input(self):
        for headers, url in (
            ([], "http://pihole.example.test:8765"),
            (["X-Test: value"], "http://pihole.example.test:8765"),
            (DEFAULT_HEADERS, "http://user:secret@pihole.example.test:8765"),
            (DEFAULT_HEADERS, "http://pihole.example.test:8765/path"),
        ):
            with self.subTest(headers=headers, url=url):
                with self.assertRaises(HeaderPolicyError):
                    allow_companion_frame(headers, url)
