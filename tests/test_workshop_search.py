import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.database.dao_ext import ExtDAO
from backend.database.models_ext import ModReplacement, WorkshopAuthorCache, WorkshopManifest, WorkshopOnlineCache, ext_db
from backend.api import API
from backend.managers.mgr_steam_api import SteamWebAPI
from backend.translation import TranslationManager
from backend.translation.contracts import TranslationDocument
from backend.utils.constants import get_steam_elanguage_options, to_steam_elanguage


class TestWorkshopSearch(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        if not ext_db.is_closed():
            ext_db.close()
        ext_db.init(str(Path(self.temp_dir.name) / "workshop-cache.db"))
        ext_db.connect(reuse_if_open=True)
        ext_db.create_tables([WorkshopManifest, WorkshopOnlineCache, WorkshopAuthorCache, ModReplacement])

        WorkshopManifest.insert_many(
            [
                {
                    "workshop_id": "1111111111",
                    "package_id": "alpha.tools",
                    "name": "Alpha Tools",
                    "author": "Alice",
                    "game_versions": ["1.5"],
                    "dependencies_mods": {},
                },
                {
                    "workshop_id": "2222222222",
                    "package_id": "beta.animals",
                    "name": "Beta Animals",
                    "author": "Bob",
                    "game_versions": ["1.5"],
                    "dependencies_mods": {},
                },
                {
                    "workshop_id": "3333333333",
                    "package_id": "alpha.library",
                    "name": "Alpha Library",
                    "author": "Carol",
                    "game_versions": ["1.4"],
                    "dependencies_mods": {"ludeon.rimworld.royalty": "Royalty"},
                },
            ]
        ).execute()
        WorkshopOnlineCache.insert_many(
            [
                {
                    "workshop_id": "1111111111",
                    "title": "Alpha Tools",
                    "author_steam_id": "76561198000000001",
                    "tags": ["Combat", "QoL"],
                    "time_updated": 1000,
                    "stats": {"subscriptions": 50},
                },
                {
                    "workshop_id": "2222222222",
                    "title": "Beta Animals",
                    "author_steam_id": "76561198000000002",
                    "tags": ["Animals"],
                    "time_updated": 2000,
                    "stats": {"subscriptions": 100},
                },
                {
                    "workshop_id": "3333333333",
                    "title": "Alpha Library",
                    "author_steam_id": "76561198000000003",
                    "tags": ["Combat"],
                    "time_updated": 500,
                    "stats": {"subscriptions": 10},
                },
            ]
        ).execute()

    def tearDown(self):
        if not ext_db.is_closed():
            ext_db.close()

    def test_cache_search_filters_author_tags_and_exclusions(self):
        result = ExtDAO.search_workshop(
            "alpha",
            filters={
                "author": "alice",
                "required_tags": ["Combat"],
                "excluded_tags": ["1.4"],
                "match_all_tags": True,
                "sort": "subscriptions",
            },
        )

        self.assertEqual([item["workshop_id"] for item in result["items"]], ["1111111111"])

    def test_cache_search_supports_or_query_and_any_tag_match(self):
        result = ExtDAO.search_workshop(
            "tools | animals",
            filters={
                "required_tags": ["QoL", "Animals"],
                "match_all_tags": False,
                "sort": "subscriptions",
            },
        )

        self.assertEqual([item["workshop_id"] for item in result["items"]], ["2222222222", "1111111111"])

    def test_cache_search_supports_dlc_appid_dependency(self):
        result = ExtDAO.search_workshop(
            "",
            filters={
                "required_dlc_appids": ["1149640"],
                "sort": "latest",
            },
        )

        self.assertEqual([item["workshop_id"] for item in result["items"]], ["3333333333"])

    def test_cache_related_queries_return_three_explicit_categories(self):
        WorkshopManifest.update(
            dependencies_mods={"2222222222": "Beta Animals"}
        ).where(WorkshopManifest.workshop_id == "1111111111").execute()
        WorkshopManifest.create(
            workshop_id="4444444444",
            package_id="alice.extra",
            name="Alice Extra",
            author="Alice",
            game_versions=["1.5"],
            dependencies_mods={"1111111111": "Alpha Tools"},
        )
        WorkshopOnlineCache.create(
            workshop_id="4444444444",
            title="Alice Extra",
            author_steam_id="76561198000000004",
            tags=["QoL"],
            time_updated=3000,
            stats={"subscriptions": 25},
        )

        dependencies = ExtDAO.get_workshop_dependencies("1111111111")
        dependents = ExtDAO.search_workshop_dependents("1111111111", page=1, page_size=20)
        same_author = ExtDAO.get_workshop_same_author("1111111111", page=1, page_size=20)

        self.assertEqual(dependencies["source"], "cache_dependencies")
        self.assertEqual([item["workshop_id"] for item in dependencies["items"]], ["2222222222"])
        self.assertEqual(dependents["source"], "cache_dependents")
        self.assertEqual([item["workshop_id"] for item in dependents["items"]], ["4444444444"])
        self.assertEqual(same_author["source"], "cache_same_author")
        self.assertEqual([item["workshop_id"] for item in same_author["items"]], ["4444444444"])

    def test_online_search_maps_queryfiles_filters_and_elanguage(self):
        captured = {}

        def fake_request_json(method, url, *, params=None, **_kwargs):
            captured["method"] = method
            captured["url"] = url
            captured["params"] = params or {}
            return {"response": {"publishedfiledetails": [], "total": 0, "next_cursor": ""}}

        with (
            patch.object(SteamWebAPI, "_get_steam_web_api_key", return_value="test-key"),
            patch.object(SteamWebAPI, "_request_json", side_effect=fake_request_json),
            patch.object(SteamWebAPI, "_save_online_search_summaries"),
        ):
            result = SteamWebAPI.search_workshop_enhanced(
                "alpha",
                sort="relevance",
                filters={
                    "language": 6,
                    "required_tags": ["1.5", "Mod"],
                    "excluded_tags": "Translation",
                    "match_all_tags": False,
                    "filetype": 1,
                    "query_type": 21,
                    "days": 3,
                    "include_recent_votes_only": True,
                    "return_vote_data": True,
                    "return_metadata": True,
                    "required_flags": "flagged",
                    "omitted_flags": "hidden",
                    "child_publishedfileid": "1234567890",
                    "required_kv_tags": [{"key": "packageId", "value": "alpha.tools"}],
                },
            )

        params = captured["params"]
        self.assertEqual(params["language"], 6)
        self.assertNotIn("requiredtags", params)
        self.assertNotIn("excludedtags", params)
        self.assertEqual(params["requiredtags[0]"], "1.5")
        self.assertEqual(params["requiredtags[1]"], "Mod")
        self.assertEqual(params["excludedtags[0]"], "Translation")
        self.assertEqual(params["required_kv_tags[0][key]"], "packageId")
        self.assertEqual(params["required_kv_tags[0][value]"], "alpha.tools")
        self.assertEqual(params["match_all_tags"], 0)
        self.assertEqual(params["filetype"], 1)
        self.assertEqual(params["query_type"], 21)
        self.assertEqual(params["days"], 3)
        self.assertEqual(params["include_recent_votes_only"], 1)
        self.assertEqual(params["return_vote_data"], 1)
        self.assertEqual(params["return_metadata"], 1)
        self.assertEqual(params["required_flags"], "flagged")
        self.assertEqual(params["omitted_flags"], "hidden")
        self.assertEqual(params["child_publishedfileid"], "1234567890")
        self.assertEqual(result["language"], 6)

    def test_online_item_search_does_not_repeat_getdetails_by_default(self):
        captured_detail_ids = []

        def fake_request_json(_method, _url, *, params=None, **_kwargs):
            return {
                "response": {
                    "publishedfiledetails": [
                        {"publishedfileid": "1111111111", "title": "Alpha", "creator": "76561198000000001"},
                    ],
                    "total": 1,
                    "next_cursor": "",
                }
            }

        def fake_details(workshop_ids, **_kwargs):
            captured_detail_ids.extend(workshop_ids)
            return {
                "1111111111": {
                    "workshop_id": "1111111111",
                    "title": "Alpha Full",
                    "description": "Full text",
                    "vote_data": {"votes_up": 10},
                }
            }

        with (
            patch.object(SteamWebAPI, "_get_steam_web_api_key", return_value="test-key"),
            patch.object(SteamWebAPI, "_request_json", side_effect=fake_request_json),
            patch.object(SteamWebAPI, "fetch_published_file_service_details", side_effect=fake_details),
        ):
            result = SteamWebAPI.search_workshop_items_enhanced("alpha", page_size=100)

        self.assertEqual(captured_detail_ids, [])
        self.assertEqual(result["items"][0]["title"], "Alpha")
        self.assertEqual(result["items"][0]["description"], "")

    def test_elanguage_mapping_uses_steam_integer_values(self):
        self.assertEqual(SteamWebAPI._resolve_steam_query_language("en"), 0)
        self.assertEqual(SteamWebAPI._resolve_steam_query_language("zh-CN"), 6)
        self.assertEqual(SteamWebAPI._resolve_steam_query_language("zh-TW"), 7)
        self.assertEqual(SteamWebAPI._resolve_steam_query_language("ja"), 10)
        self.assertEqual(to_steam_elanguage("PortugueseBrazilian"), 22)
        self.assertEqual(to_steam_elanguage("none"), -1)
        options = get_steam_elanguage_options()
        self.assertTrue(any(option["value"] == 6 and option["code"] == "zh-CN" for option in options))

    def test_get_details_uses_published_file_service_and_caches_supported_fields(self):
        captured = {}

        def fake_request_service(method_name, *, params=None, **_kwargs):
            captured["method_name"] = method_name
            captured["params"] = params or {}
            return {
                "response": {
                    "publishedfiledetails": [
                        {
                            "publishedfileid": "1111111111",
                            "title": "Alpha Tools",
                            "file_description": "Full description",
                            "creator": "76561198000000001",
                            "tags": [{"tag": "1.5"}, {"tag": "QoL"}],
                            "preview_url": "https://example.test/preview.png",
                            "metadata": "dev-data",
                            "kvtags": [{"key": "packageId", "value": "alpha.tools"}],
                            "votes_up": 12,
                            "votes_down": 1,
                            "time_updated": 10,
                        }
                    ]
                }
            }

        with (
            patch.object(SteamWebAPI, "_get_steam_web_api_key", return_value="test-key"),
            patch.object(SteamWebAPI, "_request_published_file_service", side_effect=fake_request_service),
            patch.object(SteamWebAPI, "_save_online_details") as save_mock,
        ):
            result = SteamWebAPI.fetch_published_file_service_details(["1111111111"], language="zh-CN")

        params = captured["params"]
        self.assertEqual(captured["method_name"], "GetDetails")
        self.assertEqual(params["publishedfileids[0]"], "1111111111")
        self.assertEqual(params["language"], 6)
        self.assertEqual(params["includetags"], 1)
        self.assertEqual(result["1111111111"]["description"], "Full description")
        self.assertEqual(result["1111111111"]["kv_tags"][0], {"key": "packageId", "value": "alpha.tools"})
        save_mock.assert_called_once()

    def test_service_detail_request_rejects_malformed_response(self):
        with (
            patch.object(SteamWebAPI, "_get_steam_web_api_key", return_value="test-key"),
            patch.object(SteamWebAPI, "_request_published_file_service", return_value={"unexpected": {}}),
        ):
            with self.assertRaises(RuntimeError):
                SteamWebAPI.fetch_published_file_service_details(["9999999999"])

    def test_legacy_detail_request_logs_malformed_response(self):
        with patch.object(SteamWebAPI, "_request_json", return_value={"unexpected": {}}), \
             patch("backend.managers.mgr_steam_api.logger.error") as log_error:
            result = SteamWebAPI._request_published_file_details(["1111111111"])

        self.assertEqual(result, {})
        self.assertTrue(any("Steam API 请求失败" in str(call.args[0]) for call in log_error.call_args_list))

    def test_enhanced_details_reuse_cached_online_detail_without_api_key(self):
        SteamWebAPI._save_online_details(
            {
                "1111111111": {
                    "title": "Cached Alpha",
                    "description": "Cached rich detail",
                    "author_steam_id": "76561198000000001",
                    "children": [{"workshop_id": "2222222222"}],
                    "item_type": "mod",
                }
            },
            int(SteamWebAPI.CACHE_TTL_MS),
        )

        with (
            patch("backend.managers.mgr_steam_api.time.time", return_value=SteamWebAPI.CACHE_TTL_MS / 1000),
            patch.object(SteamWebAPI, "_get_steam_web_api_key", return_value="") as key_mock,
            patch.object(SteamWebAPI, "_request_published_file_service") as request_mock,
        ):
            result = SteamWebAPI.fetch_published_file_service_details(["1111111111"])

        key_mock.assert_not_called()
        request_mock.assert_not_called()
        self.assertEqual(result["1111111111"]["title"], "Cached Alpha")
        self.assertEqual(result["1111111111"]["author_steam_id"], "76561198000000001")

    def test_enhanced_details_cache_fetched_rows_even_when_author_profiles_skipped(self):
        def fake_request_service(_method_name, *, params=None, **_kwargs):
            return {
                "response": {
                    "publishedfiledetails": [
                        {
                            "publishedfileid": "1111111111",
                            "title": "Fetched Alpha",
                            "file_description": "Fetched detail",
                            "creator": "76561198000000001",
                            "children": [{"publishedfileid": "2222222222", "filetype": 0}],
                        }
                    ]
                }
            }

        with (
            patch.object(SteamWebAPI, "_get_steam_web_api_key", return_value="test-key"),
            patch.object(SteamWebAPI, "_request_published_file_service", side_effect=fake_request_service),
        ):
            result = SteamWebAPI.fetch_published_file_service_details(["1111111111"], options={"skip_author_profiles": True})

        row = WorkshopOnlineCache.get_by_id("1111111111")
        self.assertEqual(result["1111111111"]["title"], "Fetched Alpha")
        self.assertEqual(row.title, "Fetched Alpha")
        self.assertEqual(row.description, "Fetched detail")
        self.assertEqual(row.children[0]["workshop_id"], "2222222222")

    def test_online_detail_cache_ignores_non_table_fields(self):
        SteamWebAPI._save_online_details(
            {
                "1111111111": {
                    "name": "Alpha Tools",
                    "title": "Alpha Tools",
                    "description": "Full description",
                    "source": "steam_online",
                    "stats": {"vote_score": 0.95, "votes_up": 12},
                    "kv_tags": [{"key": "packageId", "value": "alpha.tools"}],
                    "preview_url": "https://example.test/preview.png",
                    "screenshots": ["https://example.test/shot.png"],
                    "time_updated": 1000,
                }
            },
            123456,
        )

        row = WorkshopOnlineCache.get_by_id("1111111111")
        self.assertEqual(row.title, "Alpha Tools")
        self.assertEqual(row.description, "Full description")
        self.assertEqual(row.stats["vote_score"], 0.95)
        self.assertEqual(row.stats["votes_up"], 12)
        self.assertEqual(row.kv_tags[0]["key"], "packageId")
        self.assertEqual(row.preview_url, "https://example.test/preview.png")
        self.assertEqual(row.detail_last_sync_time, 123456)

    def test_online_summary_upsert_does_not_overwrite_detail_sync_time(self):
        SteamWebAPI._save_online_details(
            {
                "1111111111": {
                    "title": "Detail Title",
                    "description": "Detail description",
                }
            },
            123456,
        )
        SteamWebAPI._save_online_search_summaries(
            [
                {
                    "workshop_id": "1111111111",
                    "title": "Summary Title",
                    "source": "steam_online",
                    "url": "https://steamcommunity.com/sharedfiles/filedetails/?id=1111111111",
                }
            ],
            234567,
        )

        row = WorkshopOnlineCache.get_by_id("1111111111")
        self.assertEqual(row.title, "Summary Title")
        self.assertEqual(row.summary_last_sync_time, 234567)
        self.assertEqual(row.detail_last_sync_time, 123456)
        self.assertEqual(row.last_sync_time, 234567)

    def test_modern_item_parser_and_cache_persist_useful_fields(self):
        normalized = SteamWebAPI._normalize_published_file_item(
            {
                "publishedfileid": "1111111111",
                "creator": "76561198000000001",
                "creator_appid": 294100,
                "consumer_appid": 294100,
                "file_size": 123456,
                "file_url": "https://example.test/file.zip",
                "preview_url": "https://example.test/preview.png",
                "hcontent_file": "file-handle",
                "hcontent_preview": "preview-handle",
                "title": "Modern Alpha",
                "short_description": "Short text",
                "file_description": "[b]Full[/b] text",
                "time_created": 100,
                "time_updated": 200,
                "visibility": 0,
                "flags": 8,
                "num_comments_public": 7,
                "banned": False,
                "ban_reason": "ok",
                "app_name": "RimWorld",
                "file_type": 0,
                "can_subscribe": True,
                "subscriptions": 10,
                "favorited": 11,
                "followers": 12,
                "lifetime_subscriptions": 13,
                "lifetime_favorited": 14,
                "lifetime_followers": 15,
                "views": 16,
                "num_children": 1,
                "previews": [{"previewid": "p1", "sortorder": 1, "url": "https://example.test/shot.png", "preview_type": 0}],
                "tags": [{"tag": "1.5"}, {"tag": "QoL"}],
                "children": [{"publishedfileid": "2222222222", "file_type": 0, "sortorder": 1}],
                "vote_data": {"score": 0.9, "votes_up": 9, "votes_down": 1},
                "language": 6,
                "maybe_inappropriate_sex": False,
                "maybe_inappropriate_violence": True,
                "revision_change_number": 1234,
                "ban_text_check_result": 1,
                "translations": {"zh-CN": {"title": "现代阿尔法", "description": "完整译文"}},
                "appids_required_for_use": [1149640],
                "filename": "ignored.zip",
                "preview_file_size": 99,
            }
        )

        SteamWebAPI._save_online_search_summaries([normalized], 123456)
        row = WorkshopOnlineCache.get_by_id("1111111111")

        self.assertEqual(row.title, "Modern Alpha")
        self.assertEqual(row.description, "[b]Full[/b] text")
        self.assertEqual(row.file_size, 123456)
        self.assertEqual(row.item_type, "mod")
        self.assertEqual(row.stats["subscriptions"], 10)
        self.assertEqual(row.stats["favorited"], 11)
        self.assertEqual(row.stats["votes_up"], 9)
        self.assertEqual(row.stats["votes_down"], 1)
        self.assertEqual(row.stats["vote_score"], 0.9)
        self.assertEqual(row.stats["num_comments_public"], 7)
        self.assertEqual(normalized["translations"], {})
        self.assertEqual(row.translations, {})
        self.assertEqual(row.status["visibility"], 0)
        self.assertEqual(row.status["flags"], 8)
        self.assertEqual(row.status["can_subscribe"], True)
        self.assertEqual(row.status["banned"], False)
        self.assertEqual(row.status["ban_reason"], "ok")
        self.assertEqual(row.maybe_inappropriate_violence, 1)
        self.assertEqual(row.revision_change_number, 1234)
        self.assertEqual(row.status["ban_text_check_result"], 1)
        self.assertEqual(row.children[0]["workshop_id"], "2222222222")
        self.assertEqual(row.children[0]["item_type"], "mod")
        self.assertEqual(row.screenshots, ["https://example.test/shot.png"])
        self.assertEqual(row.summary_last_sync_time, 123456)

    def test_translation_manager_returns_segment_based_result(self):
        class DummyAIManager:
            def execute_structured_task(self, task_key, payload, override_config=None):
                self.task_key = task_key
                self.payload = payload
                return {"segments": [{"key": "title", "text": "现代阿尔法"}, {"key": "description", "text": "完整译文"}]}

        ai_mgr = DummyAIManager()
        document = TranslationDocument.from_segments(
            [
                {"key": "title", "role": "title", "text": "Modern Alpha"},
                {"key": "description", "role": "body", "text": "[b]Full[/b] text"},
            ],
            format="steam_rich_text",
            context="Steam Workshop item detail",
            glossary=[{"source": "RimWorld", "target": "环世界"}],
        )
        result = TranslationManager(ai_mgr).translate_document(document, "zh-CN")
        translated = result.segment_map()

        self.assertEqual(ai_mgr.task_key, "task.translation")
        self.assertIn("translation_input_json", ai_mgr.payload["variables"])
        self.assertIn("RimWorld", ai_mgr.payload["variables"]["glossary_block"])
        self.assertEqual(result.provider, "ai.default")
        self.assertEqual(translated["title"], "现代阿尔法")
        self.assertEqual(translated["description"], "完整译文")
        self.assertEqual(result.source_hash, TranslationManager.build_source_hash(document))
        self.assertGreater(result.updated_at, 0)

        same_source = TranslationDocument.from_segments(
            [
                {"key": "title", "role": "body", "text": "Modern Alpha"},
                {"key": "description", "role": "note", "text": "[b]Full[/b] text"},
            ],
            format="plain_text",
        )
        self.assertEqual(result.source_hash, TranslationManager.build_source_hash(same_source))

    def test_translation_manager_retries_when_title_is_missing(self):
        class DummyAIManager:
            def __init__(self):
                self.calls = 0
                self.contexts = []

            def execute_structured_task(self, task_key, payload, override_config=None):
                self.calls += 1
                self.contexts.append(payload["variables"].get("translation_context", ""))
                if self.calls == 1:
                    return {"segments": [{"key": "description", "text": "完整译文"}]}
                return {"segments": [{"key": "title", "text": "现代阿尔法"}, {"key": "description", "text": "完整译文"}]}

        document = TranslationDocument.from_segments(
            [
                {"key": "title", "role": "title", "text": "Modern Alpha"},
                {"key": "description", "role": "body", "text": "Full text"},
            ],
            context="Steam Workshop item detail",
        )
        ai_mgr = DummyAIManager()
        translated = TranslationManager(ai_mgr).translate_document(document, "zh-CN").segment_map()

        self.assertEqual(ai_mgr.calls, 2)
        self.assertIn("缺少这些 key", ai_mgr.contexts[1])
        self.assertEqual(translated["title"], "现代阿尔法")
        self.assertEqual(translated["description"], "完整译文")

    def test_author_summaries_are_cached_and_attached_to_items(self):
        captured = {}

        def fake_request_json(method, url, *, params=None, **_kwargs):
            captured["method"] = method
            captured["url"] = url
            captured["params"] = params or {}
            return {
                "response": {
                    "players": [
                        {
                            "steamid": "76561198000000001",
                            "personaname": "Alice Steam",
                            "profileurl": "https://steamcommunity.com/id/alice/",
                            "avatar": "https://example.test/a.jpg",
                            "avatarmedium": "https://example.test/a_medium.jpg",
                            "avatarfull": "https://example.test/a_full.jpg",
                            "loccountrycode": "CN",
                            "timecreated": 100,
                        }
                    ]
                }
            }

        with (
            patch.object(SteamWebAPI, "_get_steam_web_api_key", return_value="test-key"),
            patch.object(SteamWebAPI, "_request_json", side_effect=fake_request_json),
        ):
            items = SteamWebAPI._attach_author_profiles([
                {"workshop_id": "1111111111", "title": "Alpha", "author_steam_id": "76561198000000001"}
            ])

        self.assertIn("ISteamUser/GetPlayerSummaries", captured["url"])
        self.assertEqual(captured["params"]["steamids"], "76561198000000001")
        self.assertEqual(items[0]["author"], "Alice Steam")
        self.assertEqual(items[0]["author_profile"]["avatar"], "https://example.test/a.jpg")
        row = WorkshopAuthorCache.get_by_id("76561198000000001")
        self.assertEqual(row.personaname, "Alice Steam")

    def test_fetch_player_summaries_rejects_malformed_response(self):
        with (
            patch.object(SteamWebAPI, "_get_steam_web_api_key", return_value="test-key"),
            patch.object(SteamWebAPI, "_request_json", return_value={"unexpected": {}}),
        ):
            with self.assertRaises(RuntimeError):
                SteamWebAPI.fetch_player_summaries(["76561198000000009"], force_refresh=True)

    def test_legacy_item_parser_handles_field_name_differences_and_url_cleanup(self):
        normalized = SteamWebAPI._normalize_published_file_item(
            {
                "publishedfileid": "1111111111",
                "title": "Legacy Alpha",
                "description": "Legacy description",
                "creator": "76561198000000001",
                "creator_app_id": 294100,
                "consumer_app_id": 294100,
                "preview_url": "https: //example.test/legacy.png",
                "time_created": 10,
                "time_updated": 20,
                "filetype": 0,
                "subscriptions": 3,
                "favorited": 4,
                "views": 5,
                "tags": [{"tag": "1.4"}],
            },
            source="legacy",
        )

        self.assertEqual(normalized["description"], "Legacy description")
        self.assertEqual(normalized["preview_url"], "https://example.test/legacy.png")
        self.assertEqual(normalized["consumer_app_id"], 294100)
        self.assertEqual(normalized["time_created"], 10000)
        self.assertEqual(normalized["time_updated"], 20000)
        self.assertEqual(normalized["item_type"], "mod")
        self.assertEqual(normalized["stats"]["subscriptions"], 3)
        self.assertEqual(normalized["stats"]["favorited"], 4)
        self.assertEqual(normalized["tags"], ["1.4"])
        self.assertEqual(normalized["source"], "steam_legacy")

    def test_workshop_file_type_uses_result_enum_not_search_filter_enum(self):
        item = SteamWebAPI._normalize_published_file_item({"publishedfileid": "2222222222", "title": "Pack", "file_type": 2})

        self.assertEqual(item["item_type"], "collection")

    def test_legacy_detail_request_does_not_use_published_file_service_when_key_exists(self):
        captured = {}

        def fake_request_json(method, url, *, data=None, **_kwargs):
            captured["method"] = method
            captured["url"] = url
            captured["data"] = data or {}
            return {
                "response": {
                    "publishedfiledetails": [
                        {
                            "publishedfileid": "1111111111",
                            "title": "Legacy Alpha",
                            "description": "Legacy description",
                            "preview_url": "https://example.test/legacy.png",
                            "time_updated": 10,
                        }
                    ]
                }
            }

        with (
            patch.object(SteamWebAPI, "_get_steam_web_api_key", return_value="test-key"),
            patch.object(SteamWebAPI, "_request_json", side_effect=fake_request_json),
            patch.object(SteamWebAPI, "fetch_published_file_service_details") as rich_mock,
        ):
            result = SteamWebAPI._request_published_file_details(["1111111111"])

        rich_mock.assert_not_called()
        self.assertEqual(captured["method"], "POST")
        self.assertIn("ISteamRemoteStorage/GetPublishedFileDetails", captured["url"])
        self.assertEqual(result["1111111111"]["title"], "Legacy Alpha")

    def test_online_search_rejects_malformed_response(self):
        with (
            patch.object(SteamWebAPI, "_get_steam_web_api_key", return_value="test-key"),
            patch.object(SteamWebAPI, "_request_json", return_value={"response": {}}),
        ):
            with self.assertRaises(RuntimeError):
                SteamWebAPI.search_workshop_enhanced("alpha", filters={"skip_author_profiles": True})

    def test_get_user_files_maps_filters(self):
        captured = {}

        def fake_request_service(method_name, *, params=None, **_kwargs):
            captured["method_name"] = method_name
            captured["params"] = params or {}
            return {"response": {"publishedfiledetails": [], "total": 0}}

        with (
            patch.object(SteamWebAPI, "_get_steam_web_api_key", return_value="test-key"),
            patch.object(SteamWebAPI, "_request_published_file_service", side_effect=fake_request_service),
        ):
            result = SteamWebAPI.get_user_files(
                "76561198000000001",
                page=2,
                page_size=12,
                filters={
                    "language": "zh-TW",
                    "required_tags": ["1.5"],
                    "excluded_tags": "Translation",
                    "return_vote_data": True,
                    "return_kv_tags": True,
                    "required_kv_tags": [{"key": "packageId", "value": "alpha.tools"}],
                    "date_range_updated": {"start": 100, "end": 200},
                },
            )

        params = captured["params"]
        self.assertEqual(captured["method_name"], "GetUserFiles")
        self.assertEqual(params["steamid"], "76561198000000001")
        self.assertEqual(params["page"], 2)
        self.assertEqual(params["numperpage"], 12)
        self.assertEqual(params["type"], "myfiles")
        self.assertEqual(params["sortmethod"], "lastupdated")
        self.assertNotIn("privacy", params)
        self.assertEqual(params["language"], 7)
        self.assertNotIn("requiredtags", params)
        self.assertNotIn("excludedtags", params)
        self.assertEqual(params["requiredtags[0]"], "1.5")
        self.assertEqual(params["excludedtags[0]"], "Translation")
        self.assertEqual(params["required_kv_tags[0][key]"], "packageId")
        self.assertEqual(params["required_kv_tags[0][value]"], "alpha.tools")
        self.assertEqual(params["return_vote_data"], 1)
        self.assertEqual(params["return_kv_tags"], 1)
        self.assertEqual(params["date_range_updated[0]"], 100)
        self.assertEqual(params["date_range_updated[1]"], 200)
        self.assertEqual(result["total"], 0)

    def test_get_user_files_rejects_malformed_response(self):
        with (
            patch.object(SteamWebAPI, "_get_steam_web_api_key", return_value="test-key"),
            patch.object(SteamWebAPI, "_request_published_file_service", return_value={"response": {}}),
        ):
            with self.assertRaises(RuntimeError):
                SteamWebAPI.get_user_files("76561198000000001")

    def test_get_user_files_only_sends_privacy_when_explicit(self):
        captured = {}

        def fake_request_service(_method_name, *, params=None, **_kwargs):
            captured["params"] = params or {}
            return {"response": {"publishedfiledetails": [], "total": 0}}

        with (
            patch.object(SteamWebAPI, "_get_steam_web_api_key", return_value="test-key"),
            patch.object(SteamWebAPI, "_request_published_file_service", side_effect=fake_request_service),
        ):
            SteamWebAPI.get_user_files("76561198000000001", filters={"privacy": 1})

        self.assertEqual(captured["params"]["privacy"], 1)

    def test_get_user_files_persists_returned_items_to_online_cache(self):
        def fake_request_service(_method_name, *, params=None, **_kwargs):
            return {
                "response": {
                    "publishedfiledetails": [
                        {
                            "publishedfileid": "1111111111",
                            "title": "Author Alpha",
                            "creator": "76561198000000001",
                            "consumer_appid": 294100,
                            "subscriptions": 88,
                            "vote_data": {"score": 0.8, "votes_up": 8, "votes_down": 2},
                            "tags": [{"tag": "1.5"}],
                        }
                    ],
                    "total": 1,
                }
            }

        with (
            patch.object(SteamWebAPI, "_get_steam_web_api_key", return_value="test-key"),
            patch.object(SteamWebAPI, "_request_published_file_service", side_effect=fake_request_service),
        ):
            result = SteamWebAPI.get_user_files("76561198000000001", filters={"return_vote_data": True})

        row = WorkshopOnlineCache.get_by_id("1111111111")
        self.assertEqual(result["items"][0]["title"], "Author Alpha")
        self.assertEqual(row.title, "Author Alpha")
        self.assertEqual(row.stats["subscriptions"], 88)
        self.assertEqual(row.stats["votes_up"], 8)
        self.assertEqual(row.stats["vote_score"], 0.8)
        self.assertEqual(row.tags, ["1.5"])
        self.assertGreater(row.summary_last_sync_time, 0)

    def test_cached_public_detail_keeps_author_id_for_same_author_query(self):
        sync_time = int(SteamWebAPI.CACHE_TTL_MS)
        WorkshopOnlineCache.update(
            detail_last_sync_time=sync_time,
            last_sync_time=sync_time,
            short_description="Cached summary",
            description="Cached detail",
            item_type="mod",
            children=[{"workshop_id": "2222222222"}],
        ).where(WorkshopOnlineCache.workshop_id == "1111111111").execute()

        with patch("backend.managers.mgr_steam_api.time.time", return_value=sync_time / 1000):
            details, missing_ids = SteamWebAPI.fetch_item_details(["1111111111"], only_cache=True)

        detail = details["1111111111"]
        self.assertEqual(missing_ids, [])
        self.assertEqual(detail["workshop_id"], "1111111111")
        self.assertEqual(detail["author_steam_id"], "76561198000000001")
        self.assertEqual(detail["item_type"], "mod")
        self.assertEqual(detail["children"], [{"workshop_id": "2222222222"}])

    def test_same_author_enhanced_uses_author_steam_id_with_get_user_files(self):
        captured = {}

        def fake_get_user_files(steamid, *, page=1, page_size=25, filters=None):
            captured["steamid"] = steamid
            captured["page"] = page
            captured["page_size"] = page_size
            captured["filters"] = filters or {}
            return {
                "items": [
                    {"workshop_id": "1111111111", "title": "Current", "author_steam_id": steamid},
                    {"workshop_id": "2222222222", "title": "Other", "author_steam_id": steamid},
                ],
                "total": 2,
            }

        with patch.object(SteamWebAPI, "get_user_files", side_effect=fake_get_user_files):
            result = SteamWebAPI.get_workshop_same_author_enhanced(
                "1111111111",
                author_steam_id="76561198000000001",
                page=1,
                page_size=20,
                filters={"skip_author_profiles": True},
            )

        self.assertEqual(captured["steamid"], "76561198000000001")
        self.assertEqual(captured["page"], 1)
        self.assertEqual(captured["page_size"], 20)
        self.assertEqual(captured["filters"]["filetype"], 0)
        self.assertTrue(captured["filters"]["return_vote_data"])
        self.assertEqual([item["workshop_id"] for item in result["items"]], ["2222222222"])
        self.assertEqual(result["total"], 1)
        self.assertFalse(result["has_more"])
        self.assertEqual(result["author_steam_id"], "76561198000000001")

    def test_normal_detail_does_not_block_on_screenshot_scraper_by_default(self):
        WorkshopOnlineCache.update(
            description="Cached detail",
            detail_last_sync_time=int(SteamWebAPI.CACHE_TTL_MS),
            last_sync_time=int(SteamWebAPI.CACHE_TTL_MS),
        ).where(WorkshopOnlineCache.workshop_id == "1111111111").execute()

        with (
            patch("backend.managers.mgr_steam_api.time.time", return_value=SteamWebAPI.CACHE_TTL_MS / 1000),
            patch.object(SteamWebAPI, "_fetch_screenshots_via_scraper") as scraper_mock,
        ):
            detail = SteamWebAPI.get_or_fetch_details("1111111111")

        scraper_mock.assert_not_called()
        self.assertEqual(detail["workshop_id"], "1111111111")
        self.assertEqual(detail["description"], "Cached detail")

    def test_translation_meta_prefers_cached_translation_over_empty_online_value(self):
        cached_translation = {"zh-CN": {"title": "现代阿尔法", "description": "完整译文"}}
        api = object.__new__(API)
        api.translation_mgr = TranslationManager(None)
        item = {
            "workshop_id": "1111111111",
            "title": "Alpha Tools",
            "description": "English detail",
            "translations": {},
        }

        API._attach_workshop_translation_meta(api, item, cached_translation)

        self.assertEqual(item["translations"], cached_translation)

    def test_translation_meta_ignores_detail_translations_when_cache_exists(self):
        cached_translation = {"zh-CN": {"title": "本地译文", "description": "本地说明"}}
        api = object.__new__(API)
        api.translation_mgr = TranslationManager(None)
        item = {
            "workshop_id": "1111111111",
            "title": "Alpha Tools",
            "description": "English detail",
            "translations": {
                "zh-CN": {"title": "外部译文", "description": "外部说明"},
                "ja": {"title": "外部日文", "description": "外部说明"},
            },
        }

        API._attach_workshop_translation_meta(api, item, cached_translation)

        self.assertEqual(item["translations"], cached_translation)
        self.assertNotIn("ja", item["translations"])

    def test_translation_meta_does_not_trust_detail_translations_without_cache(self):
        api = object.__new__(API)
        api.translation_mgr = TranslationManager(None)
        item = {
            "workshop_id": "1111111111",
            "title": "Alpha Tools",
            "description": "English detail",
            "translations": {"zh-CN": {"title": "外部译文", "description": "外部说明"}},
        }

        API._attach_workshop_translation_meta(api, item)

        self.assertEqual(item["translations"], {})

    def test_account_and_creator_operations_validate_required_params(self):
        with patch.object(SteamWebAPI, "_get_steam_web_api_key", return_value=""):
            with self.assertRaises(ValueError):
                SteamWebAPI.subscribe_published_file("1111111111")

        with patch.object(SteamWebAPI, "_get_steam_web_api_key", return_value="test-key"):
            with self.assertRaises(ValueError):
                SteamWebAPI.publish_file({"appid": 294100, "title": "Missing files"})
            with self.assertRaises(ValueError):
                SteamWebAPI.update_tags({"appid": 294100, "publishedfileid": "1111111111"})

    def test_detail_related_ids_include_dependencies(self):
        detail = {
            "meta": {"dependencies_mods": {"4444444444": "Dependency Mod"}},
            "same_author_mods": [{"workshop_id": "2222222222"}],
            "dependents_mods": [{"workshop_id": "3333333333"}],
        }

        self.assertEqual(
            SteamWebAPI._collect_related_workshop_ids(detail),
            ["2222222222", "3333333333", "4444444444"],
        )

    def test_collection_children_logs_malformed_response(self):
        with patch.object(SteamWebAPI, "_request_json", return_value={"response": {}}), \
             patch("backend.managers.mgr_steam_api.logger.error") as log_error:
            children = SteamWebAPI.fetch_collection_children("1234567890")

        self.assertEqual(children, [])
        self.assertTrue(any("解析合集失败" in str(call.args[0]) for call in log_error.call_args_list))


if __name__ == "__main__":
    unittest.main()
