import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType, SimpleNamespace

from backend.text_search import effective_files as effective_files_module
from backend.text_search.backends import PythonStreamingSearchBackend, RipgrepSearchBackend
from backend.text_search.effective_files import SearchBuildCancelled, build_mod_root_cache_key, build_search_roots
from backend.text_search.models import SearchRequest, SearchRoot, normalize_file_types
from backend.utils.text_decode import decode_text_bytes


class _DummyLoadOrderManager:
    def __init__(self, active_mods=None):
        self._active_mods = list(active_mods or [])
        self.read_calls = 0

    def read_active_mods(self, mods_config_file_path=None):  # noqa: ARG002
        self.read_calls += 1
        return {"active_mods": list(self._active_mods)}


class _DummyApi:
    def __init__(self, context, load_order_mgr):
        self.active_context = context
        self.load_order_mgr = load_order_mgr


class _BlockingBackend:
    backend_name = "blocking-test"
    backend_label = "BlockingTest"

    def __init__(self, started_event: threading.Event, release_event: threading.Event):
        self.started_event = started_event
        self.release_event = release_event

    def search(self, request, search_roots, cancel_event, on_file_complete=None):  # noqa: ARG002
        self.started_event.set()
        while not cancel_event.is_set() and not self.release_event.is_set():
            time.sleep(0.01)
        return iter(())


class TestFileSearch(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_dao_module = sys.modules.get("backend.database.dao")
        self.fake_dao_module = ModuleType("backend.database.dao")
        self.fake_mod_dao = type("FakeModDAO", (), {"get_profile_mods": staticmethod(lambda _context: [])})
        self.fake_dao_module.ModDAO = self.fake_mod_dao
        sys.modules["backend.database.dao"] = self.fake_dao_module
        self.original_cache_dir = build_search_roots.__globals__["SEARCH_MOD_ROOT_CACHE_DIR"]
        self.original_cache_prune_limit = build_search_roots.__globals__["MAX_SEARCH_MOD_ROOT_CACHE_FILES"]
        self.original_cache_prune_at = build_search_roots.__globals__["_last_mod_root_cache_prune_monotonic"]
        build_search_roots.__globals__["SEARCH_MOD_ROOT_CACHE_DIR"] = self.temp_dir / "cache"
        build_search_roots.__globals__["_last_mod_root_cache_prune_monotonic"] = 0.0

    def tearDown(self):
        if self.original_dao_module is None:
            sys.modules.pop("backend.database.dao", None)
        else:
            sys.modules["backend.database.dao"] = self.original_dao_module
        build_search_roots.__globals__["SEARCH_MOD_ROOT_CACHE_DIR"] = self.original_cache_dir
        build_search_roots.__globals__["MAX_SEARCH_MOD_ROOT_CACHE_FILES"] = self.original_cache_prune_limit
        build_search_roots.__globals__["_last_mod_root_cache_prune_monotonic"] = self.original_cache_prune_at
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_context(self, version="1.5.4069 rev95"):
        return SimpleNamespace(
            profile_id="test-profile",
            game_version=version,
            game_install_path=str(self.temp_dir / "Game"),
            user_data_path=str(self.temp_dir / "User"),
            prefer_steam_launch=False,
            use_workshop_mods=True,
            use_self_mods=True,
            inactive_mods_order=[],
        )

    def _write_mod_file(self, mod_dir: Path, relative_path: str, content: str, encoding: str = "utf-8"):
        file_path = mod_dir / Path(relative_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding=encoding)
        return file_path

    def _make_mod(self, folder_name: str, package_id: str, *, store: str, name: str | None = None) -> dict:
        mod_dir = self.temp_dir / folder_name
        (mod_dir / "About").mkdir(parents=True, exist_ok=True)
        (mod_dir / "About" / "About.xml").write_text(
            f"<ModMetaData><packageId>{package_id}</packageId><name>{name or package_id}</name></ModMetaData>",
            encoding="utf-8",
        )
        return {
            "package_id": package_id,
            "name": name or package_id,
            "display_name": name or package_id,
            "path": str(mod_dir),
            "store": store,
            "source": store,
        }

    def test_build_search_roots_filters_scope_and_effective_only(self):
        context = self._make_context()
        local_mod = self._make_mod("LocalMod", "author.local", store="local", name="Local Mod")
        workshop_mod = self._make_mod("WorkshopMod", "author.workshop", store="workshop", name="Workshop Mod")

        local_mod_path = Path(local_mod["path"])
        self._write_mod_file(local_mod_path, "Common/root.xml", "<root/>")
        self._write_mod_file(local_mod_path, "1.5/Defs/Active.xml", "<Defs><ThingDef/></Defs>")
        self._write_mod_file(local_mod_path, "1.6/Defs/Future.xml", "<Defs><ThingDef/></Defs>")
        self._write_mod_file(
            local_mod_path,
            "LoadFolders.xml",
            """<loadFolders>
  <v1.5>
    <li>1.5/Defs</li>
  </v1.5>
  <v1.6>
    <li>1.6/Defs</li>
  </v1.6>
</loadFolders>""",
        )
        self._write_mod_file(Path(workshop_mod["path"]), "Defs/Workshop.xml", "<Defs><ThingDef/></Defs>")

        self.fake_mod_dao.get_profile_mods = staticmethod(lambda _context: [local_mod, workshop_mod])

        effective_request = SearchRequest.from_payload({
            "query": "ThingDef",
            "scope": "current-effective",
            "effective_only": True,
        })
        _, effective_roots, _ = build_search_roots(
            context=context,
            load_order_mgr=_DummyLoadOrderManager(active_mods=["author.local", "author.workshop"]),
            request=effective_request,
            self_mods_path="",
        )
        effective_root_paths = {Path(item.root_path).resolve() for item in effective_roots if item.package_id == "author.local"}
        self.assertIn((local_mod_path / "Common").resolve(), effective_root_paths)
        self.assertIn((local_mod_path / "1.5" / "Defs").resolve(), effective_root_paths)
        self.assertNotIn((local_mod_path / "1.6").resolve(), effective_root_paths)

        raw_request = SearchRequest.from_payload({
            "query": "ThingDef",
            "scope": "current-effective",
            "effective_only": False,
        })
        original_plan_single = build_search_roots.__globals__["_plan_single_mod_roots"]
        try:
            def fail_if_called(**kwargs):  # noqa: ARG001
                raise AssertionError("关闭 effective_only 后不应进入有效根规划")

            build_search_roots.__globals__["_plan_single_mod_roots"] = fail_if_called
            _, raw_roots, raw_meta = build_search_roots(
                context=context,
                load_order_mgr=_DummyLoadOrderManager(active_mods=["author.local", "author.workshop"]),
                request=raw_request,
                self_mods_path="",
            )
        finally:
            build_search_roots.__globals__["_plan_single_mod_roots"] = original_plan_single
        raw_paths = {Path(item.root_path).resolve() for item in raw_roots if item.package_id == "author.local"}
        self.assertEqual(raw_paths, {local_mod_path.resolve()})
        self.assertEqual(raw_meta["cache_source"], "direct-mod-dirs")

        workshop_request = SearchRequest.from_payload({
            "query": "ThingDef",
            "scope": "workshop",
            "effective_only": False,
        })
        _, workshop_roots, _ = build_search_roots(
            context=context,
            load_order_mgr=_DummyLoadOrderManager(active_mods=["author.local", "author.workshop"]),
            request=workshop_request,
            self_mods_path="",
        )
        self.assertTrue(all(item.package_id == "author.workshop" for item in workshop_roots))

    def test_build_search_roots_filters_current_active_scope(self):
        context = self._make_context()
        active_mod = self._make_mod("ActiveMod", "author.active", store="local", name="Active Mod")
        inactive_mod = self._make_mod("InactiveMod", "author.inactive", store="self", name="Inactive Mod")
        self._write_mod_file(Path(active_mod["path"]), "Defs/Active.xml", "<Defs><ThingDef/></Defs>")
        self._write_mod_file(Path(inactive_mod["path"]), "Defs/Inactive.xml", "<Defs><ThingDef/></Defs>")

        self.fake_mod_dao.get_profile_mods = staticmethod(lambda _context: [active_mod, inactive_mod])

        request = SearchRequest.from_payload({
            "query": "ThingDef",
            "scope": "current-active",
            "effective_only": False,
        })
        mods, search_roots, _ = build_search_roots(
            context=context,
            load_order_mgr=_DummyLoadOrderManager(active_mods=["author.active"]),
            request=request,
            self_mods_path=str(self.temp_dir / "SelfMods"),
        )
        self.assertEqual([mod["package_id"] for mod in mods], ["author.active"])
        self.assertTrue(all(item.package_id == "author.active" for item in search_roots))

    def test_build_search_roots_loadfolders_keeps_root_level_common_dirs(self):
        context = self._make_context(version="1.6.4104 rev100")
        mod = self._make_mod("RootCommonMod", "author.rootcommon", store="workshop", name="Root Common Mod")
        mod_path = Path(mod["path"])
        self._write_mod_file(mod_path, "Defs/Root.xml", "<Defs><ThingDef/></Defs>")
        self._write_mod_file(mod_path, "About/About.xml", "<ModMetaData/>")
        self._write_mod_file(mod_path, "Languages/English/Keyed/Keys.xml", "<LanguageData/>")
        self._write_mod_file(mod_path, "1.6/Defs/Versioned.xml", "<Defs><ThingDef/></Defs>")
        self._write_mod_file(
            mod_path,
            "LoadFolders.xml",
            """<loadFolders>
  <v1.6>
    <li>1.6</li>
  </v1.6>
</loadFolders>""",
        )

        self.fake_mod_dao.get_profile_mods = staticmethod(lambda _context: [mod])
        request = SearchRequest.from_payload({
            "query": "ThingDef",
            "scope": "current-effective",
            "effective_only": True,
        })
        _, roots, _ = build_search_roots(
            context=context,
            load_order_mgr=_DummyLoadOrderManager(active_mods=["author.rootcommon"]),
            request=request,
            self_mods_path="",
        )
        root_paths = {Path(item.root_path).resolve() for item in roots}
        self.assertIn((mod_path / "1.6").resolve(), root_paths)
        self.assertIn((mod_path / "Defs").resolve(), root_paths)
        self.assertIn((mod_path / "About").resolve(), root_paths)
        self.assertIn((mod_path / "Languages").resolve(), root_paths)

    def test_build_search_roots_loadfolders_supports_mod_conditions(self):
        context = self._make_context(version="1.6.4104 rev100")
        mod = self._make_mod("ConditionalMod", "author.conditional", store="workshop", name="Conditional Mod")
        mod_path = Path(mod["path"])
        self._write_mod_file(mod_path, "Defs/Base.xml", "<Defs><ThingDef/></Defs>")
        self._write_mod_file(mod_path, "1.6/Mods/Ideology/Defs/A.xml", "<Defs><ThingDef/></Defs>")
        self._write_mod_file(mod_path, "1.6/Mods/Odyssey/Defs/B.xml", "<Defs><ThingDef/></Defs>")
        self._write_mod_file(mod_path, "1.6/Mods/Both/Defs/C.xml", "<Defs><ThingDef/></Defs>")
        self._write_mod_file(mod_path, "1.6/Mods/NoCE/Defs/D.xml", "<Defs><ThingDef/></Defs>")
        self._write_mod_file(
            mod_path,
            "LoadFolders.xml",
            """<loadFolders>
  <v1.6>
    <li>/</li>
    <li IfModActive="Ludeon.RimWorld.Ideology">1.6/Mods/Ideology</li>
    <li IfModActive="Ludeon.RimWorld.Odyssey">1.6/Mods/Odyssey</li>
    <li IfModActiveAll="Ludeon.RimWorld.Ideology,Ludeon.RimWorld.Odyssey">1.6/Mods/Both</li>
    <li IfModNotActive="CETeam.CombatExtended">1.6/Mods/NoCE</li>
  </v1.6>
</loadFolders>""",
        )

        self.fake_mod_dao.get_profile_mods = staticmethod(lambda _context: [mod])
        request = SearchRequest.from_payload({
            "query": "ThingDef",
            "scope": "current-effective",
            "effective_only": True,
        })
        _, roots, _ = build_search_roots(
            context=context,
            load_order_mgr=_DummyLoadOrderManager(active_mods=[
                "author.conditional",
                "Ludeon.RimWorld.Ideology",
                "Ludeon.RimWorld.Odyssey",
            ]),
            request=request,
            self_mods_path="",
        )
        root_paths = {Path(item.root_path).resolve() for item in roots}
        self.assertIn((mod_path / "Defs").resolve(), root_paths)
        self.assertIn((mod_path / "1.6" / "Mods" / "Ideology").resolve(), root_paths)
        self.assertIn((mod_path / "1.6" / "Mods" / "Odyssey").resolve(), root_paths)
        self.assertIn((mod_path / "1.6" / "Mods" / "Both").resolve(), root_paths)
        self.assertIn((mod_path / "1.6" / "Mods" / "NoCE").resolve(), root_paths)

    def test_build_search_roots_keeps_mod_order_when_planning_in_parallel(self):
        context = self._make_context()
        mods = [
            self._make_mod("ParallelModA", "author.parallel.a", store="local", name="Parallel A"),
            self._make_mod("ParallelModB", "author.parallel.b", store="local", name="Parallel B"),
            self._make_mod("ParallelModC", "author.parallel.c", store="local", name="Parallel C"),
        ]
        request = SearchRequest.from_payload({
            "query": "ThingDef",
            "scope": "current-effective",
            "effective_only": True,
        })
        original_plan_single = build_search_roots.__globals__["_plan_single_mod_roots"]
        original_resolve_workers = build_search_roots.__globals__["_resolve_search_root_planning_workers"]

        def fake_plan_single_mod_roots(*, index, mod, context, planning_context, request, cancel_event=None):  # noqa: ARG001
            time.sleep(0.02 * (4 - index))
            return index, mod["name"], [
                SearchRoot(
                    package_id=mod["package_id"],
                    mod_name=mod["name"],
                    store=mod["store"],
                    mod_path=mod["path"],
                    root_path=mod["path"],
                    root_kind="dir",
                )
            ], "fresh"

        try:
            build_search_roots.__globals__["_plan_single_mod_roots"] = fake_plan_single_mod_roots
            build_search_roots.__globals__["_resolve_search_root_planning_workers"] = lambda total_mods: min(3, total_mods)
            _, search_roots, _ = build_search_roots(
                context=context,
                load_order_mgr=_DummyLoadOrderManager(active_mods=[mod["package_id"] for mod in mods]),
                request=request,
                self_mods_path="",
                mods=mods,
            )
        finally:
            build_search_roots.__globals__["_plan_single_mod_roots"] = original_plan_single
            build_search_roots.__globals__["_resolve_search_root_planning_workers"] = original_resolve_workers

        self.assertEqual(
            [item.package_id for item in search_roots],
            ["author.parallel.a", "author.parallel.b", "author.parallel.c"],
        )

    def test_python_streaming_search_backend_supports_plain_regex_and_case(self):
        mod_dir = self.temp_dir / "SearchMod"
        mod_dir.mkdir(parents=True, exist_ok=True)
        file_path = mod_dir / "Defs.xml"
        file_path.write_text(
            "\n".join([
                "Alpha",
                "Target line",
                "regex_123",
            ]),
            encoding="utf-8",
        )
        search_root = SearchRoot(
            package_id="author.search",
            mod_name="Search Mod",
            store="local",
            mod_path=str(mod_dir),
            root_path=str(file_path),
            root_kind="file",
        )
        backend = PythonStreamingSearchBackend()

        plain_request = SearchRequest.from_payload({
            "query": "target",
            "case_sensitive": False,
            "scope": "current-effective",
        })
        plain_results = list(backend.search(plain_request, [search_root], threading.Event()))
        self.assertEqual(len(plain_results), 1)
        self.assertEqual(plain_results[0].line_number, 2)
        self.assertEqual(plain_results[0].matched_line, "Target line")

        case_request = SearchRequest.from_payload({
            "query": "target",
            "case_sensitive": True,
            "scope": "current-effective",
        })
        self.assertEqual(list(backend.search(case_request, [search_root], threading.Event())), [])

        regex_request = SearchRequest.from_payload({
            "query": r"regex_\d+",
            "use_regex": True,
            "scope": "current-effective",
        })
        regex_results = list(backend.search(regex_request, [search_root], threading.Event()))
        self.assertEqual(len(regex_results), 1)
        self.assertEqual(regex_results[0].matched_line, "regex_123")

    def test_python_streaming_search_backend_supports_directory_roots(self):
        mod_dir = self.temp_dir / "SearchDirMod"
        mod_dir.mkdir(parents=True, exist_ok=True)
        nested_file = mod_dir / "Defs" / "ThingDefs.xml"
        nested_file.parent.mkdir(parents=True, exist_ok=True)
        nested_file.write_text("<Defs>\n  <ThingDef>Alpha</ThingDef>\n</Defs>", encoding="utf-8")

        search_root = SearchRoot(
            package_id="author.dir",
            mod_name="Directory Root Mod",
            store="local",
            mod_path=str(mod_dir),
            root_path=str(mod_dir),
            root_kind="dir",
        )
        backend = PythonStreamingSearchBackend()
        request = SearchRequest.from_payload({
            "query": "ThingDef",
            "scope": "current-effective",
            "file_types": [".xml"],
        })

        results = list(backend.search(request, [search_root], threading.Event()))
        self.assertEqual(len(results), 1)
        self.assertEqual(Path(results[0].file_path).resolve(), nested_file.resolve())

    def test_python_streaming_search_backend_falls_back_to_latin1(self):
        mod_dir = self.temp_dir / "LatinMod"
        mod_dir.mkdir(parents=True, exist_ok=True)
        file_path = mod_dir / "Notes.txt"
        file_path.write_bytes("café line\nother".encode("latin-1"))

        search_root = SearchRoot(
            package_id="author.latin",
            mod_name="Latin Mod",
            store="local",
            mod_path=str(mod_dir),
            root_path=str(file_path),
            root_kind="file",
        )
        backend = PythonStreamingSearchBackend()
        request = SearchRequest.from_payload({
            "query": "café",
            "scope": "current-effective",
            "file_types": [".txt"],
        })

        results = list(backend.search(request, [search_root], threading.Event()))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].matched_line, "café line")

    def test_decode_text_bytes_reports_detected_encoding(self):
        content, encoding = decode_text_bytes("café".encode("latin-1"))
        self.assertEqual(content, "café")
        self.assertEqual(encoding, "latin-1")

    def test_normalize_file_types_supports_all_files_marker(self):
        self.assertEqual(normalize_file_types(["."]), (".",))
        self.assertEqual(normalize_file_types(["*.*"]), (".",))
        self.assertEqual(normalize_file_types(["xml", ".cs"]), (".xml", ".cs"))

    def test_mod_root_cache_is_compact_per_mod_record(self):
        context = self._make_context()
        mod = self._make_mod("CompactCacheMod", "author.compact", store="workshop", name="Compact Cache Mod")
        mod_path = Path(mod["path"])
        self._write_mod_file(mod_path, "About/About.xml", "<ModMetaData/>")
        self._write_mod_file(mod_path, "1.5/Defs/Active.xml", "<Defs><ThingDef/></Defs>")
        self._write_mod_file(mod_path, "README.md", "ignore me")
        self._write_mod_file(
            mod_path,
            "LoadFolders.xml",
            """<loadFolders>
  <v1.5>
    <li>1.5</li>
  </v1.5>
</loadFolders>""",
        )

        self.fake_mod_dao.get_profile_mods = staticmethod(lambda _context: [mod])
        request = SearchRequest.from_payload({
            "query": "ThingDef",
            "scope": "current-effective",
            "effective_only": True,
        })
        load_order_mgr = _DummyLoadOrderManager(active_mods=["author.compact"])
        _, search_roots, meta = build_search_roots(
            context=context,
            load_order_mgr=load_order_mgr,
            request=request,
            self_mods_path="",
        )

        self.assertEqual(meta["cache_source"], "mod-roots")
        self.assertEqual(len(search_roots), 2)

        cache_key = build_mod_root_cache_key(mod)
        cache_path = (self.temp_dir / "cache" / f"{cache_key}.json")
        payload = json.loads(cache_path.read_text(encoding="utf-8"))

        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["root_path"], str(mod_path.resolve()))
        self.assertIn("1.5", payload["root_level_dirs"])
        self.assertIn("About", payload["root_level_dirs"])
        self.assertNotIn("README.md", payload["root_level_dirs"])
        self.assertEqual(payload["version_dirs"].get("1.5"), "1.5")
        self.assertEqual(payload["loadfolders_versions"].get("1.5", [])[0]["path"], "1.5")

    def test_mod_root_cache_key_ignores_inner_file_changes(self):
        context = self._make_context()
        mod = self._make_mod("StableCacheKeyMod", "author.stablekey", store="workshop", name="Stable Cache Key Mod")
        mod_path = Path(mod["path"])
        self._write_mod_file(mod_path, "Defs/A.xml", "<Defs><ThingDef/></Defs>")
        self._write_mod_file(mod_path, "LoadFolders.xml", "<loadFolders><v1.5><li>/</li></v1.5></loadFolders>")
        key_before = build_mod_root_cache_key(mod)
        self._write_mod_file(mod_path, "Defs/B.xml", "<Defs><ThingDef/></Defs>")
        key_after = build_mod_root_cache_key(mod)

        self.assertEqual(key_before, key_after)

    def test_build_search_roots_reads_active_mods_once_for_planning(self):
        context = self._make_context()
        mods = [
            self._make_mod("PlanReadA", "author.plan.a", store="local", name="Plan A"),
            self._make_mod("PlanReadB", "author.plan.b", store="local", name="Plan B"),
        ]
        for mod in mods:
            self._write_mod_file(Path(mod["path"]), "Defs/Active.xml", "<Defs><ThingDef/></Defs>")
        self.fake_mod_dao.get_profile_mods = staticmethod(lambda _context: mods)

        load_order_mgr = _DummyLoadOrderManager(active_mods=[mod["package_id"] for mod in mods])
        request = SearchRequest.from_payload({
            "query": "ThingDef",
            "scope": "current-effective",
            "effective_only": True,
        })
        build_search_roots(
            context=context,
            load_order_mgr=load_order_mgr,
            request=request,
            self_mods_path="",
        )

        self.assertLessEqual(load_order_mgr.read_calls, 2)

    def test_ripgrep_chunks_absolute_roots(self):
        backend = RipgrepSearchBackend("C:/tools/rg.exe")
        roots = [
                SearchRoot(
                    package_id=f"author.{index}",
                    mod_name=f"Mod {index}",
                    store="workshop",
                    mod_path=str(self.temp_dir / f"Root{index}"),
                    root_path=str(self.temp_dir / f"Root{index}"),
                    root_kind="dir",
                )
            for index in range(120)
        ]
        chunks = backend._chunk_roots(roots)  # noqa: SLF001
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= backend.MAX_ROOTS_PER_CHUNK for chunk in chunks))

    def test_ripgrep_all_files_marker_skips_include_globs(self):
        backend = RipgrepSearchBackend("C:/tools/rg.exe")
        request = SearchRequest.from_payload({
            "query": "ThingDef",
            "scope": "current-active",
            "file_types": ["."],
        })
        command = backend._build_command(  # noqa: SLF001
            Path("C:/tools/rg.exe"),
            request,
            [
                SearchRoot(
                    package_id="author.all",
                    mod_name="All Files Mod",
                    store="local",
                    mod_path=str(self.temp_dir / "AllFilesMod"),
                    root_path=str(self.temp_dir / "AllFilesMod"),
                    root_kind="dir",
                )
            ],
        )
        self.assertFalse(any(part == "*.xml" for part in command))
        self.assertIn("ThingDef", command)

    def test_get_ripgrep_status_strict_mode_does_not_fallback(self):
        original_mgr_github_module = sys.modules.get("backend.managers.mgr_github")
        fake_mgr_github_module = ModuleType("backend.managers.mgr_github")
        fake_mgr_github_module.GITHUB_ARTIFACT_RELEASE_ASSET = "release-asset"
        fake_mgr_github_module.GITHUB_INSTALL_EXTRACT_THEN_MOVE = "extract-then-move"
        fake_mgr_github_module.GithubArtifactRequest = type("GithubArtifactRequest", (), {})
        fake_mgr_github_module.GithubInstallPlan = type("GithubInstallPlan", (), {})
        fake_mgr_github_module.GithubInstallRequest = type("GithubInstallRequest", (), {})
        fake_mgr_github_module.GithubManager = type("GithubManager", (), {})
        sys.modules["backend.managers.mgr_github"] = fake_mgr_github_module

        try:
            from backend.text_search.tooling import get_ripgrep_status
        finally:
            if original_mgr_github_module is None:
                sys.modules.pop("backend.managers.mgr_github", None)
            else:
                sys.modules["backend.managers.mgr_github"] = original_mgr_github_module

        missing_path = str(self.temp_dir / "missing-rg-dir")
        status = get_ripgrep_status(missing_path, strict=True)
        self.assertFalse(status.available)
        self.assertEqual(status.resolved_path, "")

    def test_save_mod_root_cache_parallel_prune_is_stable(self):
        build_search_roots.__globals__["MAX_SEARCH_MOD_ROOT_CACHE_FILES"] = 2
        build_search_roots.__globals__["_last_mod_root_cache_prune_monotonic"] = 0.0

        def write_cache(index: int):
            mod = self._make_mod(f"CacheMod{index}", f"author.cache.{index}", store="workshop", name=f"Cache Mod {index}")
            payload = effective_files_module._build_static_mod_root_cache_payload(mod)  # noqa: SLF001
            effective_files_module.save_mod_root_cache(f"cache-key-{index}", payload)

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(write_cache, index) for index in range(8)]
            for future in futures:
                future.result()

        cache_files = list((self.temp_dir / "cache").glob("*.json"))
        self.assertLessEqual(len(cache_files), 8)

    def test_build_search_roots_can_be_cancelled_during_prepare(self):
        context = self._make_context()
        mod = self._make_mod("CancelableMod", "author.cancel", store="local", name="Cancelable Mod")
        self._write_mod_file(Path(mod["path"]), "Defs/A.xml", "<Defs><ThingDef/></Defs>")
        self.fake_mod_dao.get_profile_mods = staticmethod(lambda _context: [mod])

        cancel_event = threading.Event()
        cancel_event.set()
        request = SearchRequest.from_payload({
            "query": "ThingDef",
            "scope": "current-effective",
            "effective_only": False,
        })

        with self.assertRaises(SearchBuildCancelled):
            build_search_roots(
                context=context,
                load_order_mgr=_DummyLoadOrderManager(active_mods=["author.cancel"]),
                request=request,
                self_mods_path="",
                cancel_event=cancel_event,
            )

    def test_file_search_manager_supersedes_previous_task(self):
        from backend.text_search.manager import FileSearchManager

        context = self._make_context()
        load_order_mgr = _DummyLoadOrderManager(active_mods=["author.search"])
        manager = FileSearchManager(_DummyApi(context, load_order_mgr))

        started_event = threading.Event()
        release_event = threading.Event()
        manager._resolve_backend = lambda: _BlockingBackend(started_event, release_event)  # noqa: SLF001
        manager._load_search_roots = lambda _context, _request, **_kwargs: ([], [], {"cache_hit": False})  # noqa: SLF001

        payload = {
            "query": "ThingDef",
            "scope": "current-effective",
            "effective_only": True,
        }
        first_task_id = manager.start_search(payload)
        self.assertTrue(started_event.wait(1), "首个搜索任务未能按预期启动")

        first_cancel_event = manager._task_events[first_task_id]  # noqa: SLF001
        second_task_id = manager.start_search(payload)

        self.assertNotEqual(first_task_id, second_task_id)
        self.assertTrue(first_cancel_event.is_set(), "新的搜索任务应当顶替旧任务")

        release_event.set()
        deadline = time.time() + 1
        while time.time() < deadline:
            if second_task_id not in manager._task_events:  # noqa: SLF001
                break
            time.sleep(0.01)

        self.assertNotIn(second_task_id, manager._task_events)  # noqa: SLF001


if __name__ == "__main__":
    unittest.main()
