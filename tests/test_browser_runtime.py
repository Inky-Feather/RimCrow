import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from backend.browser_runtime import WorkshopPageRenderer


class TestWorkshopPageRenderer(unittest.TestCase):
    def test_injected_proxy_selectors_keep_rimcrow_namespace(self):
        renderer = WorkshopPageRenderer("http://127.0.0.1:8000", "browser")
        soup = BeautifulSoup(
            '<a href="/sharedfiles/filedetails/?id=123">mod</a><form action="/search" method="get"></form>',
            "html.parser",
        )

        renderer._sanitize_remote_soup(soup, "https://steamcommunity.com/workshop/")
        toolbar_html = renderer._build_toolbar_html("title", "https://steamcommunity.com/sharedfiles/filedetails/?id=123")
        bridge_script = renderer._build_bridge_script("https://steamcommunity.com/sharedfiles/filedetails/?id=123")

        self.assertEqual(soup.a["data-rimcrow-proxy-url"], "https://steamcommunity.com/sharedfiles/filedetails/?id=123")
        self.assertEqual(soup.form["data-rimcrow-proxy-form"], "https://steamcommunity.com/search")
        self.assertIn("rimcrow-workshop-toolbar", toolbar_html)
        self.assertIn("data-rimcrow-proxy-url", bridge_script)
        self.assertNotIn("data-proxy-url", bridge_script)

    def test_render_uses_managed_proxy_for_workshop_request(self):
        captured = {}

        class FakeResponse:
            url = "https://steamcommunity.com/sharedfiles/filedetails/?id=123"
            text = "<html><head><title>Demo</title></head><body><a href='/workshop/'>next</a></body></html>"

            def raise_for_status(self): pass

        class FakeSession:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def get(self, url, **kwargs):
                captured["url"] = url
                captured["kwargs"] = kwargs
                return FakeResponse()

        with patch("backend.browser_runtime.build_retry_session", return_value=FakeSession()) as retry_factory, \
             patch("backend.browser_runtime.network_mgr.get_proxy_url", return_value="http://127.0.0.1:10808"):
            html = WorkshopPageRenderer().render("https://steamcommunity.com/sharedfiles/filedetails/?id=123")

        self.assertIn("Demo", html)
        self.assertEqual(captured["url"], "https://steamcommunity.com/sharedfiles/filedetails/?id=123")
        self.assertEqual(captured["kwargs"]["proxies"], {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"})
        self.assertIn("User-Agent", captured["kwargs"]["headers"])
        self.assertNotIn(429, retry_factory.call_args.kwargs["status_forcelist"])

    def test_render_logs_network_context_on_failure(self):
        class FailingSession:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def get(self, *_args, **_kwargs):
                raise RuntimeError("SECRET_PROXY_FAILURE")

        with patch("backend.browser_runtime.build_retry_session", return_value=FailingSession()), \
             patch("backend.browser_runtime.network_mgr.get_proxy_url", return_value="http://user:pass@127.0.0.1:10808"), \
             patch("backend.browser_runtime.logger.warning") as warning:
            html = WorkshopPageRenderer().render("https://steamcommunity.com/sharedfiles/filedetails/?id=123")

        self.assertIn("加载页面失败", html)
        self.assertNotIn("SECRET_PROXY_FAILURE", html)
        extra_context = warning.call_args.kwargs["extra"]["extra_context"]
        self.assertEqual(extra_context["error_type"], "RuntimeError")
        self.assertTrue(extra_context["app_proxy_enabled"])
        self.assertIn("env_proxy_available", extra_context)
        self.assertEqual(extra_context["proxy_host"], "127.0.0.1")
        self.assertEqual(extra_context["proxy_port"], 10808)
        self.assertEqual(extra_context["status_code"], 0)

    def test_render_falls_back_to_direct_webview_load_when_proxy_fetch_is_limited(self):
        class Response429:
            status_code = 429

        class SteamRateLimitedError(Exception):
            response = Response429()

        class FailingSession:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def get(self, *_args, **_kwargs):
                raise SteamRateLimitedError("too many requests")

        target_url = "https://steamcommunity.com/sharedfiles/filedetails/?id=2023507013"
        with patch("backend.browser_runtime.build_retry_session", return_value=FailingSession()), \
             patch("backend.browser_runtime.network_mgr.get_proxy_url", return_value=""), \
             patch("backend.browser_runtime.logger.warning") as warning:
            html = WorkshopPageRenderer(navigation_mode="webview").render(target_url)

        self.assertIn("window.location.replace", html)
        self.assertIn(target_url, html)
        self.assertNotIn("加载页面失败", html)
        self.assertEqual(warning.call_args.kwargs["extra"]["extra_context"]["status_code"], 429)


if __name__ == "__main__":
    unittest.main()
