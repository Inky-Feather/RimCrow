from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from backend.settings import settings
from backend.utils.event_bus import EventBus
from backend.utils.logger import logger

from .backends import PythonStreamingSearchBackend, RipgrepSearchBackend
from .effective_files import (
    SearchBuildCancelled,
    build_search_roots,
)
from .models import SearchRequest


class FileSearchManager:
    RESULT_BATCH_SIZE = 40
    PROGRESS_THROTTLE_MS = 150
    BUILD_STAGE_MAX_PROGRESS = 24
    SCAN_STAGE_START_PROGRESS = 25
    SCAN_STAGE_MAX_PROGRESS = 99

    def __init__(self, api):
        self.api = api
        self.python_backend = PythonStreamingSearchBackend()
        self._lock = threading.Lock()
        self._task_events: dict[str, threading.Event] = {}

    def start_search(self, payload: dict[str, Any] | None) -> str:
        request = SearchRequest.from_payload(payload)
        task_id = uuid.uuid4().hex
        cancel_event = threading.Event()
        superseded_count = 0
        with self._lock:
            for active_event in self._task_events.values():
                if not active_event.is_set():
                    active_event.set()
                    superseded_count += 1
            self._task_events[task_id] = cancel_event

        EventBus.emit_progress(
            task_id,
            "file-search",
            status="pending",
            progress=0,
            message="搜索任务已加入后台队列" if superseded_count == 0 else f"搜索任务已加入后台队列，正在替换 {superseded_count} 个旧任务",
            metrics={
                "title": "文件内容搜索",
                "query": request.query,
                "scope": request.scope,
                "superseded_count": superseded_count,
            },
        )

        threading.Thread(
            target=self._run_search_task,
            args=(task_id, request, cancel_event),
            daemon=True,
        ).start()
        return task_id

    def cancel_task(self, task_id: str) -> bool:
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id: return False
        with self._lock:
            cancel_event = self._task_events.get(normalized_task_id)
        if not cancel_event: return False
        cancel_event.set()
        return True

    def _run_search_task(self, task_id: str, request: SearchRequest, cancel_event: threading.Event):
        try:
            context = self.api.active_context
            if not context:
                raise ValueError("当前环境未激活，无法执行搜索")
            EventBus.emit_progress(
                task_id,
                "file-search",
                status="running",
                progress=1,
                message=self._prepare_stage_message(request),
                metrics={
                    "title": "文件内容搜索",
                    "query": request.query,
                    "scope": request.scope,
                    "stage": "prepare",
                },
            )

            progress_state = {
                "processed": 0,
                "last_emit_ms": 0,
                "current_progress": 0,
            }

            def on_mod_progress(processed_mods: int, total_mods: int, mod_name: str):
                self._emit_build_progress_if_needed(
                    task_id=task_id,
                    request=request,
                    processed_mods=processed_mods,
                    total_mods=max(total_mods, 1),
                    mod_name=mod_name,
                    progress_state=progress_state,
                )

            mods, search_roots, cache_meta = self._load_search_roots(
                context,
                request,
                cancel_event=cancel_event,
                on_mod_progress=on_mod_progress,
            )
            if cancel_event.is_set():
                self._emit_results(task_id, [], done=True, status="cancelled", matched_count=0)
                EventBus.emit_progress(
                    task_id,
                    "file-search",
                    status="cancelled",
                    progress=0,
                    message="搜索任务已被新的搜索请求替换",
                    metrics={
                        "title": "文件内容搜索",
                        "query": request.query,
                        "scope": request.scope,
                    },
                )
                return
            backend = self._resolve_backend()
            total_roots = len(search_roots)
            EventBus.emit_progress(
                task_id,
                "file-search",
                status="running",
                progress=self.SCAN_STAGE_START_PROGRESS,
                message=f"已锁定 {total_roots} 个{self._root_unit_label(request)}，正在使用 {backend.backend_label} 扫描",
                metrics={
                    "title": "文件内容搜索",
                    "query": request.query,
                    "scope": request.scope,
                    "mod_count": len(mods),
                    "root_count": total_roots,
                    "cache_hit": cache_meta.get("cache_hit", False),
                    "cache_source": cache_meta.get("cache_source", ""),
                    "backend": backend.backend_name,
                    "task_created_at": int(time.time() * 1000),
                },
            )

            results_batch: list[dict[str, Any]] = []
            matched_count = 0

            def on_file_complete(processed: int, total: int):
                progress_state["processed"] = processed
                self._emit_progress_if_needed(
                    task_id=task_id,
                    request=request,
                    processed=processed,
                    total=max(total, 1),
                    matched_count=matched_count,
                    cache_hit=bool(cache_meta.get("cache_hit")),
                    backend_name=backend.backend_name,
                    progress_state=progress_state,
                    force=False,
                )

            for result in backend.search(request, search_roots, cancel_event, on_file_complete=on_file_complete):
                if cancel_event.is_set():
                    break
                matched_count += 1
                results_batch.append(result.to_dict())
                if len(results_batch) >= self.RESULT_BATCH_SIZE:
                    self._emit_results(task_id, results_batch, done=False, status="running", matched_count=matched_count)
                    results_batch = []

            if results_batch:
                self._emit_results(task_id, results_batch, done=False, status="running", matched_count=matched_count)

            if cancel_event.is_set():
                self._emit_results(task_id, [], done=True, status="cancelled", matched_count=matched_count)
                EventBus.emit_progress(
                    task_id,
                    "file-search",
                    status="cancelled",
                    progress=min(99, int(progress_state["processed"] * 100 / max(total_roots, 1))),
                    message="搜索任务已取消",
                    metrics={
                        "title": "文件内容搜索",
                        "query": request.query,
                        "scope": request.scope,
                        "matched_count": matched_count,
                        "root_count": total_roots,
                        "backend": backend.backend_name,
                    },
                )
                return

            self._emit_results(task_id, [], done=True, status="success", matched_count=matched_count)
            EventBus.emit_progress(
                task_id,
                "file-search",
                status="success",
                progress=100,
                message=f"搜索完成，共命中 {matched_count} 条结果",
                metrics={
                    "title": "文件内容搜索",
                    "query": request.query,
                    "scope": request.scope,
                    "matched_count": matched_count,
                    "root_count": total_roots,
                    "mod_count": len(mods),
                    "cache_hit": cache_meta.get("cache_hit", False),
                    "cache_source": cache_meta.get("cache_source", ""),
                    "backend": backend.backend_name,
                },
            )
        except SearchBuildCancelled:
            self._emit_results(task_id, [], done=True, status="cancelled", matched_count=0)
            EventBus.emit_progress(
                task_id,
                "file-search",
                status="cancelled",
                progress=max(0, int(progress_state.get("current_progress", 0) or 0)),
                message=f"搜索任务已在{self._build_stage_label(request)}阶段取消",
                metrics={
                    "title": "文件内容搜索",
                    "query": request.query,
                    "scope": request.scope,
                    "stage": "build-roots",
                },
            )
        except Exception as exc:
            logger.error(f"文件搜索任务失败: {exc}", exc_info=True)
            self._emit_results(task_id, [], done=True, status="failed", matched_count=0, message=str(exc))
            EventBus.emit_progress(
                task_id,
                "file-search",
                status="failed",
                progress=0,
                message=f"搜索失败: {exc}",
                metrics={
                    "title": "文件内容搜索",
                    "query": request.query,
                    "scope": request.scope,
                    "error": str(exc),
                },
            )
        finally:
            with self._lock:
                self._task_events.pop(task_id, None)

    def _emit_progress_if_needed(
        self,
        task_id: str,
        request: SearchRequest,
        processed: int,
        total: int,
        matched_count: int,
        cache_hit: bool,
        backend_name: str,
        progress_state: dict[str, int],
        force: bool,
    ):
        now_ms = int(time.time() * 1000)
        if not force and now_ms - int(progress_state.get("last_emit_ms", 0)) < self.PROGRESS_THROTTLE_MS: return
        progress_state["last_emit_ms"] = now_ms
        scan_span = self.SCAN_STAGE_MAX_PROGRESS - self.SCAN_STAGE_START_PROGRESS
        progress = min(
            self.SCAN_STAGE_MAX_PROGRESS,
            self.SCAN_STAGE_START_PROGRESS + int(processed * scan_span / max(total, 1)),
        )
        progress_state["current_progress"] = progress
        EventBus.emit_progress(
            task_id,
            "file-search",
            status="running",
            progress=progress,
            message=f"已扫描 {processed}/{total} 个{self._root_unit_label(request)}",
            metrics={
                "title": "文件内容搜索",
                "query": request.query,
                "scope": request.scope,
                "matched_count": matched_count,
                "processed_roots": processed,
                "root_count": total,
                "cache_hit": cache_hit,
                "backend": backend_name,
                "stage": "scan",
            },
        )

    def _emit_build_progress_if_needed(
        self,
        *,
        task_id: str,
        request: SearchRequest,
        processed_mods: int,
        total_mods: int,
        mod_name: str,
        progress_state: dict[str, int],
    ):
        now_ms = int(time.time() * 1000)
        if now_ms - int(progress_state.get("last_emit_ms", 0)) < self.PROGRESS_THROTTLE_MS and processed_mods < total_mods: return
        progress_state["last_emit_ms"] = now_ms
        progress = min(self.BUILD_STAGE_MAX_PROGRESS, int(processed_mods * self.BUILD_STAGE_MAX_PROGRESS / max(total_mods, 1)))
        progress_state["current_progress"] = progress
        EventBus.emit_progress(
            task_id,
            "file-search",
            status="running",
            progress=progress,
            message=f"正在整理{self._build_stage_label(request)} {processed_mods}/{total_mods}: {mod_name}",
            metrics={
                "title": "文件内容搜索",
                "query": request.query,
                "scope": request.scope,
                "processed_mods": processed_mods,
                "mod_count": total_mods,
                "stage": "build-roots",
            },
        )

    def _emit_results(
        self,
        task_id: str,
        results: list[dict[str, Any]],
        *,
        done: bool,
        status: str,
        matched_count: int,
        message: str = "",
    ):
        EventBus.emit(
            "file-search-results",
            {
                "task_id": task_id,
                "results": results,
                "done": done,
                "status": status,
                "matched_count": matched_count,
                "message": message,
            },
        )

    def _load_search_roots(self, context, request: SearchRequest, cancel_event=None, on_mod_progress=None):
        mods, search_roots, meta = build_search_roots(
            context=context,
            load_order_mgr=self.api.load_order_mgr,
            request=request,
            self_mods_path=settings.config.self_mods_path,
            on_mod_progress=on_mod_progress,
            cancel_event=cancel_event,
        )
        return mods, search_roots, meta

    def _resolve_backend(self):
        # 只有真正决定走 ripgrep 后端时才需要工具解析逻辑，
        # 这样纯管理器/纯算法测试不会被下载器和数据库依赖链拖住。
        from .tooling import resolve_ripgrep_executable

        executable = resolve_ripgrep_executable()
        if executable: return RipgrepSearchBackend(executable)
        return self.python_backend

    @staticmethod
    def _root_unit_label(request: SearchRequest) -> str:
        return "有效搜索根" if request.effective_only else "模组目录"

    @staticmethod
    def _build_stage_label(request: SearchRequest) -> str:
        return "有效搜索根" if request.effective_only else "搜索模组目录"

    def _prepare_stage_message(self, request: SearchRequest) -> str:
        if request.effective_only: return "正在准备有效搜索根与缓存签名"
        return "正在准备搜索模组目录"
