from __future__ import annotations

from abc import ABC, abstractmethod
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from typing import Callable, Iterable

from backend.settings import settings
from backend.utils.logger import logger
from backend.utils.text_decode import iter_text_decoding_candidates

from .effective_files import iter_root_candidate_files
from .models import CandidateFile, SearchRequest, SearchResult, SearchRoot, matches_all_file_types


class SearchBackend(ABC):
    backend_name = "python"
    backend_label = "Python"

    @abstractmethod
    def search(
        self,
        request: SearchRequest,
        search_roots: Iterable[SearchRoot],
        cancel_event: threading.Event,
        on_file_complete: Callable[[int, int], None] | None = None,
    ) -> Iterable[SearchResult]:
        raise NotImplementedError


class PythonStreamingSearchBackend(SearchBackend):
    backend_name = "python"
    backend_label = "Python"
    """
    纯 Python 回退搜索实现。

    仅在未找到 ripgrep 时使用，逐个有效搜索根展开文件并匹配。
    """

    def search(
        self,
        request: SearchRequest,
        search_roots: Iterable[SearchRoot],
        cancel_event: threading.Event,
        on_file_complete: Callable[[int, int], None] | None = None,
    ) -> Iterable[SearchResult]:
        pattern = request.compile_pattern()
        items = list(search_roots)
        total = len(items)
        processed = 0

        for search_root in items:
            if cancel_event.is_set():
                break
            for candidate in iter_root_candidate_files(search_root, request, cancel_event=cancel_event):
                if cancel_event.is_set():
                    break
                yield from self._search_single_file(candidate, pattern, cancel_event)
            processed += 1
            if on_file_complete:
                on_file_complete(processed, total)

    def _search_single_file(
        self,
        candidate: CandidateFile,
        pattern: re.Pattern[str],
        cancel_event: threading.Event,
    ) -> Iterable[SearchResult]:
        try:
            with Path(candidate.file_path).open("rb") as handle:
                sample = handle.read(4096)
        except OSError:
            return

        for encoding in iter_text_decoding_candidates(sample):
            try:
                yield from self._search_with_encoding(candidate, pattern, encoding, cancel_event)
                return
            except UnicodeError:
                continue
            except OSError:
                return

    def _search_with_encoding(
        self,
        candidate: CandidateFile,
        pattern: re.Pattern[str],
        encoding: str,
        cancel_event: threading.Event,
    ) -> Iterable[SearchResult]:
        with Path(candidate.file_path).open("r", encoding=encoding, errors="strict") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                if cancel_event.is_set(): return
                matched_line = raw_line.rstrip("\r\n")
                if not pattern.search(matched_line):
                    continue
                yield SearchResult(
                    package_id=candidate.package_id,
                    mod_name=candidate.mod_name,
                    store=candidate.store,
                    mod_path=candidate.mod_path,
                    file_path=candidate.file_path,
                    file_name=candidate.file_name,
                    line_number=line_number,
                    matched_line=matched_line,
                )


class RipgrepSearchBackend(SearchBackend):
    backend_name = "ripgrep"
    backend_label = "ripgrep"
    COMMAND_LINE_LIMIT = 24000
    MAX_ROOTS_PER_CHUNK = 96

    def __init__(self, executable_path: str | Path | None = None):
        self.executable_path = executable_path

    def search(
        self,
        request: SearchRequest,
        search_roots: Iterable[SearchRoot],
        cancel_event: threading.Event,
        on_file_complete: Callable[[int, int], None] | None = None,
    ) -> Iterable[SearchResult]:
        # ripgrep 的“检测/下载/安装”链依赖更重，这里按需导入，避免纯搜索测试被无关依赖阻塞。
        from .tooling import resolve_ripgrep_executable

        executable = resolve_ripgrep_executable(str(self.executable_path or ""))
        if not executable:
            raise RuntimeError("未找到 ripgrep 可执行文件。")

        items = list(search_roots)
        total = len(items)
        processed = 0
        debug_mode = bool(getattr(settings.config, "debug_mode", False))

        for root_chunk in self._chunk_roots(items):
            if cancel_event.is_set():
                break
            yield from self._run_chunk(
                executable=executable,
                request=request,
                search_roots=root_chunk,
                cancel_event=cancel_event,
                debug_mode=debug_mode,
            )
            processed += len(root_chunk)
            if on_file_complete:
                on_file_complete(processed, total)

    def _run_chunk(
        self,
        *,
        executable: Path,
        request: SearchRequest,
        search_roots: list[SearchRoot],
        cancel_event: threading.Event,
        debug_mode: bool,
    ) -> Iterable[SearchResult]:
        if not search_roots: return
        command = self._build_command(executable, request, search_roots)
        if debug_mode:
            logger.debug(
                "文件搜索 ripgrep 命令: query=%s roots=%s command=%s",
                request.query,
                len(search_roots),
                command,
            )

        creationflags = 0
        startupinfo = None
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )
        started_at = time.perf_counter()
        root_resolver = self._build_root_resolver(search_roots)

        try:
            assert process.stdout is not None
            for raw_line in process.stdout:
                if cancel_event.is_set():
                    self._terminate_process(process)
                    break
                result = self._parse_match_event(raw_line, root_resolver)
                if result is not None:
                    yield result
        finally:
            if process.poll() is None:
                self._terminate_process(process)

        stderr_text = ""
        if process.stderr:
            stderr_text = process.stderr.read().strip()
        return_code = process.wait(timeout=5)
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        if debug_mode:
            logger.debug(
                "文件搜索 ripgrep 完成: query=%s roots=%s returncode=%s elapsed_ms=%s stderr=%s",
                request.query,
                len(search_roots),
                return_code,
                elapsed_ms,
                stderr_text,
            )
        if cancel_event.is_set(): return
        if return_code not in {0, 1}:
            raise RuntimeError(stderr_text or "ripgrep 搜索执行失败")

    def _build_command(self, executable: Path, request: SearchRequest, search_roots: list[SearchRoot]) -> list[str]:
        command = [
            str(executable),
            "--json",
            "--line-number",
            "--with-filename",
            "--no-messages",
            "--encoding",
            "auto",
            "--text",
        ]
        if not request.exclude_options.get("skip_hidden", True):
            command.append("--hidden")
        if not request.case_sensitive:
            command.append("--ignore-case")
        if not request.use_regex:
            command.append("--fixed-strings")
        if not matches_all_file_types(request.file_types):
            for file_type in request.file_types:
                command.extend(["-g", f"*{file_type}"])
        for exclude_glob in self._build_common_exclude_globs(request):
            command.extend(["-g", f"!{exclude_glob}"])
        command.append(request.query)
        command.extend(root.root_path for root in search_roots)
        return command

    def _build_common_exclude_globs(self, request: SearchRequest) -> list[str]:
        globs: list[str] = []
        if request.exclude_options.get("skip_git", True):
            globs.append("**/.git/**")
        if request.exclude_options.get("skip_languages", True):
            globs.append("**/Languages/**")
        if request.exclude_options.get("skip_source", True):
            globs.append("**/Source/**")
        if request.exclude_options.get("skip_textures", True):
            globs.append("**/Textures/**")
            globs.append("**/TexturesExpanded/**")
        return globs

    def _chunk_roots(self, search_roots: list[SearchRoot]) -> list[list[SearchRoot]]:
        chunks: list[list[SearchRoot]] = []
        current_chunk: list[SearchRoot] = []
        current_length = 0
        for search_root in search_roots:
            path_length = len(search_root.root_path) + 1
            if current_chunk and (
                len(current_chunk) >= self.MAX_ROOTS_PER_CHUNK
                or current_length + path_length >= self.COMMAND_LINE_LIMIT
            ):
                chunks.append(current_chunk)
                current_chunk = []
                current_length = 0
            current_chunk.append(search_root)
            current_length += path_length
        if current_chunk:
            chunks.append(current_chunk)
        return chunks

    @staticmethod
    def _build_root_resolver(search_roots: list[SearchRoot]) -> list[SearchRoot]:
        return sorted(
            search_roots,
            key=lambda item: (
                0 if item.root_kind == "file" else 1,
                -len(Path(item.root_path).parts),
                str(item.root_path).lower(),
            ),
        )

    def _parse_match_event(self, raw_line: str, root_resolver: list[SearchRoot]) -> SearchResult | None:
        try: payload = json.loads(raw_line)
        except json.JSONDecodeError: return None
        if payload.get("type") != "match": return None

        data = payload.get("data") or {}
        file_path = self._extract_text(data.get("path") or {})
        if not file_path: return None
        line_number = int(data.get("line_number") or 0)
        if line_number <= 0: return None
        matched_line = self._extract_text(data.get("lines") or {}).rstrip("\r\n")
        owner = self._resolve_owner_root(file_path, root_resolver)
        if owner is None: return None
        absolute_path = str(Path(file_path).resolve())
        return SearchResult(
            package_id=owner.package_id,
            mod_name=owner.mod_name,
            store=owner.store,
            mod_path=owner.mod_path,
            file_path=absolute_path,
            file_name=Path(absolute_path).name,
            line_number=line_number,
            matched_line=matched_line,
        )

    @staticmethod
    def _resolve_owner_root(file_path: str, root_resolver: list[SearchRoot]) -> SearchRoot | None:
        normalized_file = str(Path(file_path).resolve()).lower()
        for search_root in root_resolver:
            root_path = str(Path(search_root.root_path).resolve()).lower()
            if search_root.root_kind == "file":
                if normalized_file == root_path: return search_root
                continue
            if normalized_file == root_path or normalized_file.startswith(f"{root_path}{os.sep}".lower()):
                return search_root
        return None

    @staticmethod
    def _extract_text(node: dict[str, object]) -> str:
        if not isinstance(node, dict): return ""
        text = node.get("text")
        if isinstance(text, str): return text
        return ""

    @staticmethod
    def _terminate_process(process: subprocess.Popen[str]) -> None:
        try:
            process.terminate()
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
        except OSError:
            pass
