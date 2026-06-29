import unittest

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


if __name__ == "__main__":
    unittest.main()
