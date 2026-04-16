"""
AI 管理器。

职责分层：
1. 委托 `PromptManager` 管理提示词模板
2. 通用单次 / 批量 AI 调用
3. 诊断型 Agent 流程（工具调用、流式输出、取消控制）
"""

import json
import asyncio
import os
import re
import threading
import time
import uuid
from typing import Any, Dict, List

from backend.ai.tools import AIToolExecutor
from backend.ai.prompts import PromptManager

# 禁用远程模型成本映射
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

from json_repair import repair_json

from backend.settings import DATA_DIR, AIConfig, settings
from backend.utils.logger import logger
from backend.utils.constants import get_lang_by_code
from backend.utils.event_bus import EventBus
from backend.ai.llm_gateway import LiteLLMGateway


DIAGNOSTIC_MAX_LOOPS = 10
FORCED_DIAGNOSTIC_SUMMARY_PROMPT = (
    "你已经完成资料查阅。禁止继续调用任何工具。"
    "请直接基于当前证据给出最终诊断；如果证据仍不足，也要明确给出最可能的 1-3 个原因、"
    "证据依据，以及下一步建议用户如何验证。"
)
DUPLICATE_TOOL_CALL_ERROR = (
    "系统警告：你已经使用完全相同的参数调用过该工具！"
    "请停止重复调用，立即基于已有证据进行分析和总结！"
)


class AIManager:
    """全局单例 AI 管理器。"""

    _instance = None
    
    def __new__(cls):
        """实现单例模式，确保全局只保留一个 AI 管理器实例。"""
        if cls._instance is None:
            cls._instance = super(AIManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """初始化运行期状态、LLM 网关和本地 Prompt 仓库。"""
        if self._initialized:
            return
        self._initialized = True
        self.llm = LiteLLMGateway()
        self._cancelled_sessions: set[str] = set()
        self._cancel_lock = threading.Lock()
        
        # Prompt 的加载、保存、重置等生命周期全部交给专门的 PromptManager。
        self.prompt_manager = PromptManager(str(DATA_DIR / "prompts.json"))
        
        logger.info("AI Manager initialized.")

    # =========================================================================
    # 公开能力：厂商 / 模型探测
    # =========================================================================
    def get_providers(self) -> List[Dict[str, str]]:
        """返回前端 AI 设置页所需的协议列表。"""
        return self.llm.get_providers()

    def get_models(self, config_dict: dict) -> List[str]:
        """根据临时配置探测模型列表。"""
        return self.llm.get_models(config_dict)

    # =========================================================================
    # 通用基础工具
    # =========================================================================
    def _get_llm_kwargs(self, override_config: dict | None = None) -> dict:
        """委托网关统一组装 LLM 调用参数。"""
        return self.llm.build_kwargs(override_config)

    def _create_token_usage(self, model_name: str = "") -> dict[str, Any]:
        """构造诊断链路统一使用的 Token 统计结构。"""
        return {
            "estimated_prompt_tokens": 0,
            "estimated_completion_tokens": 0,
            "estimated_total_tokens": 0,
            "tool_rounds": 0,
            "forced_final_round": False,
            "model": model_name,
        }

    def _extract_json_from_text(self, text: str, is_batch: bool = False):
        """
        利用 json_repair 库进行究极容错解析
        """
        try:
            # repair_json 能自动处理 Markdown 代码块、未转义引号、缺少闭合括号等问题
            # return_objects=True 直接返回 Python 对象
            parsed = repair_json(text, return_objects=True)
            
            # 兼容性处理：有时候 AI 会自作聪明只返回对象没返回数组
            if isinstance(parsed, dict):
                return [parsed] if is_batch else parsed
            if isinstance(parsed, list):
                return parsed
                
            # 如果解析出来既不是 list 也不是 dict (比如解析成了空字符串)
            return None
        except Exception as e:
            logger.error(f"JSON Repair 彻底失败: {e}\n原文: {text[:200]}...")
            return None

    def _estimate_text_tokens(self, text: str, model_name: str) -> int:
        """
        使用后端统一的 tokenizer 估算文本 Token。
        这里的结果用于诊断链路的全局 Token 统计，比前端按字符粗算更稳定。
        """
        return self.llm.estimate_text_tokens(text, model_name)

    def _estimate_messages_tokens(self, messages: list[dict], model_name: str) -> int:
        """
        估算整轮 messages 进入模型前的输入 Token。
        某些模型不返回 usage 时，后端统一用这个值来做累计统计。
        """
        return self.llm.estimate_messages_tokens(messages, model_name)

    def _normalize_litellm_content(self, content: Any) -> str:
        """
        兼容 LiteLLM 不同模型返回的 content 结构，统一转成纯文本。
        某些模型会返回 list[part]，这里做一次后端规整，便于诊断流与兜底逻辑复用。
        """
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        text_parts.append(str(part.get("text", "")))
                    elif "text" in part:
                        text_parts.append(str(part.get("text", "")))
                else:
                    text_parts.append(str(part))
            return "".join(text_parts)
        return str(content)

    def _normalize_history_content(self, content: Any) -> str:
        """将历史消息内容规整为纯文本，避免对象结构污染上下文。"""
        if isinstance(content, dict):
            return json.dumps(content, ensure_ascii=False)
        return str(content or "")

    def _is_retryable_stream_error(self, error: Exception) -> bool:
        """
        判断是否属于典型的流式中断异常。
        这类错误常见于代理/网关提前断开 chunked 响应，适合自动回退到非流式重试。
        """
        error_text = str(error or "").lower()
        retry_signals = (
            "midstreamfallbackerror",
            "incomplete chunked read",
            "peer closed connection",
            "connection aborted",
            "server disconnected",
            "chunkedencodingerror",
        )
        return any(signal in error_text for signal in retry_signals)

    def _format_tool_calls(self, tool_calls: list[Any]) -> list[dict[str, Any]]:
        """把不同 SDK 风格的 tool call 对象规整成前端和 LiteLLM 统一使用的格式。"""
        formatted_tool_calls = []
        for index, tool_call in enumerate(tool_calls):
            function_obj = getattr(tool_call, "function", None)
            formatted_tool_calls.append({
                "id": getattr(tool_call, "id", None) or f"tool_call_{index}",
                "type": getattr(tool_call, "type", None) or "function",
                "function": {
                    "name": getattr(function_obj, "name", None) or "",
                    "arguments": getattr(function_obj, "arguments", None) or "{}",
                },
            })
        return formatted_tool_calls

    def _build_prompt_messages(
        self,
        prompt_config: dict,
        variables: dict,
        history: list[dict] | None = None,
    ) -> list[dict]:
        """根据 prompt 配置、变量和历史消息生成最终 messages。"""
        system_prompt = self._safe_format(prompt_config.get("system", ""), variables)
        user_prompt = self._safe_format(prompt_config.get("user_template", ""), variables)

        messages = [{"role": "system", "content": system_prompt}]
        for msg in history or []:
            if msg.get("role") in ("user", "assistant"):
                messages.append({
                    "role": msg["role"],
                    "content": self._normalize_history_content(msg.get("content", "")),
                })
        messages.append({"role": "user", "content": user_prompt})
        return messages

    def _build_diagnostic_error_response(
        self,
        error: Exception,
        token_usage: dict[str, Any],
        summary_label: str = "点击展开错误详情",
    ) -> dict[str, Any]:
        """统一生成诊断链路错误响应，避免多处复制粘贴。"""
        import traceback

        token_usage["estimated_total_tokens"] = (
            token_usage["estimated_prompt_tokens"] + token_usage["estimated_completion_tokens"]
        )
        error_trace = traceback.format_exc()
        error_markdown = (
            "⚠️ **AI 推理链路在本轮处理中发生严重中断。**\n\n"
            "这通常是因为 API 中转站超时、模型不支持流式工具调用，或者网络连接被强制断开。\n\n"
            f"<details><summary>{summary_label}</summary>\n\n"
            f"```text\n{str(error)}\n\n{error_trace}\n```\n"
            "</details>"
        )
        return {
            "analysis": error_markdown,
            "actions": [],
            "token_usage": token_usage,
        }

    def _complete_diagnostic_without_stream(self, messages: list[dict], llm_kwargs: dict, tools=None, tool_choice=None) -> dict:
        """
        非流式兜底请求。
        当流式输出半途断开时，退回同步 completion，尽量保住本轮分析结果或工具调用计划。
        """
        request_kwargs = dict(llm_kwargs)
        if tools is not None:
            request_kwargs["tools"] = tools
        if tool_choice is not None:
            request_kwargs["tool_choice"] = tool_choice

        response = self.llm.completion(messages=messages, llm_kwargs=request_kwargs)
        message = response.choices[0].message # type: ignore
        tool_calls = getattr(message, "tool_calls", None) or []

        if tool_calls:
            return {
                "is_tool_call": True,
                "tool_calls": self._format_tool_calls(tool_calls),
                "final_text": "",
            }

        return {
            "is_tool_call": False,
            "tool_calls": [],
            "final_text": self._normalize_litellm_content(getattr(message, "content", ""))
        }

    def _run_diagnostic_completion_with_fallback(self, messages: list[dict], llm_kwargs: dict, session_id: str, tools=None, tool_choice=None) -> dict:
        """
        统一封装诊断请求：
        1. 优先走流式，保留前端逐字体验；
        2. 如果流式在中途断开，则自动回退到非流式补救，避免把网络异常直接甩给用户。
        """
        try:
            return self._stream_diagnostic_completion( messages=messages, llm_kwargs=llm_kwargs, 
                                    session_id=session_id, tools=tools, tool_choice=tool_choice )
        
        except AIRequestCancelled:
            raise
        except Exception as e:
            if not self._is_retryable_stream_error(e): raise
            logger.warning(
                f"[AI诊断] 流式输出中断，自动回退为非流式补救 "
                f"session_id={session_id} error={type(e).__name__}: {e}"
            )
            return self._complete_diagnostic_without_stream(
                messages=messages,
                llm_kwargs=llm_kwargs,
                tools=tools,
                tool_choice=tool_choice,
            )

    def _summarize_tool_result(self, name: str, tool_result: str) -> str:
        """
        为前端步骤面板生成一条简短摘要，便于用户快速判断这一步拿回了什么信息。
        """
        try:
            parsed = json.loads(tool_result)
            if isinstance(parsed, dict):
                if name == "get_log_context" and not parsed.get("error"):
                    result_count = len(parsed.get("results", []) or [])
                    if result_count > 1:
                        return f"已批量返回 {result_count} 条候选日志上下文"
                    block_span = parsed.get("provided_context") or parsed.get("context_provided", "目标日志内容")
                    return f"已返回 {block_span} 的日志内容"
                if parsed.get("error"):
                    return f"执行失败：{parsed['error']}"
                if name == "get_log_context":
                    return f"已返回 {parsed.get('provided_context', '指定范围')} 的日志内容"
                if name == "get_active_mod_list":
                    return f"已返回 {parsed.get('total_active', 0)} 个激活模组"
                if name == "search_mods":
                    return f"已找到 {len(parsed.get('matched', []) or [])} 个候选模组"
                if name == "get_mod_info":
                    data = parsed.get("data", {}) if isinstance(parsed.get("data"), dict) else {}
                    return f"已返回模组元数据：{data.get('name') or parsed.get('package_id') or '未知模组'}"
                if name == "get_mod_rules":
                    return "已返回模组规则信息"
                if name == "get_mod_user_context":
                    return "已返回模组的用户备注/标签/分组信息"
                if name == "get_group_mods":
                    return f"已返回 {len(parsed.get('matched_groups', []) or [])} 个匹配分组"
        except Exception:
            pass

        safe_text = (tool_result or "").replace("\r", " ").replace("\n", " ").strip()
        if not safe_text:
            return "工具执行完成，但没有返回可展示内容"
        return safe_text[:180] + ("..." if len(safe_text) > 180 else "")

    def _parse_diagnostic_final_text(self, final_text: str, final_think: str = "") -> dict[str, Any]:
        """
        解析诊断链路的最终文本输出。

        处理目标有两个：
        1. 从正文末尾剥离前端可执行的 `<actions>` JSON
        2. 对空白结论做兜底，避免前端收到一段完全不可读的空字符串
        """
        # 优先寻找 <actions> 包裹的 JSON
        action_match = re.search(r'[-\s]*<actions>\s*(.*?)\s*</actions>', final_text, re.IGNORECASE | re.DOTALL)
        actions = []
        clean_text = final_text
        
        if action_match:
            json_str = action_match.group(1).strip()
            # 去除 AI 自作聪明的 ```json 和 ``` 标记
            json_str = re.sub(r'^[-\s]*```json\s*', '', json_str, flags=re.IGNORECASE)
            json_str = re.sub(r'```\s*$', '', json_str)
            
            parsed_json = self._extract_json_from_text(json_str)
            if isinstance(parsed_json, dict) and "actions" in parsed_json:
                actions = parsed_json["actions"]
            elif isinstance(parsed_json, list):
                actions = parsed_json
                
            # 从正文中剥离这块内容
            clean_text = final_text.replace(action_match.group(0), "").strip()
        else:
            #  兜底：如果没写 <actions> 标签，但结尾直接输出了 JSON 代码块
            fallback_match = re.search(r'[-\s]*```(?:json)?\s*(\{\s*"actions"[\s\S]*?\})\s*```', final_text, re.IGNORECASE)
            if fallback_match:
                parsed_json = self._extract_json_from_text(fallback_match.group(1))
                if isinstance(parsed_json, dict) and "actions" in parsed_json:
                    actions = parsed_json["actions"]
                    clean_text = final_text.replace(fallback_match.group(0), "").strip()
        
        # 移除末尾的分割符或空行
        lines = clean_text.splitlines()  # 按行拆分（自动处理 \n \r\n）
        while lines:
            last_line = lines[-1].strip()  # 去掉首尾空白（空格、制表符）
            # 如果最后一行 是空 或者 是 --- 分隔符，就删掉
            if last_line == "" or re.search(r'^[-~\s]*$', last_line):
                lines.pop()
            else:
                break
        clean_text = "\n".join(lines)
        
        # 【核心拦截】如果输出真的是空白的（被熔断或 Token 耗尽）
        if not clean_text.strip():
            if final_think.strip():
                clean_text = "⚠️ **AI 已耗尽最大输出长度限制，未能生成最终结论。**\n\n<details><summary>点击查看 AI 的深度思考过程</summary>\n\n```text\n" + final_think + "\n```\n</details>"
            else:
                clean_text = "⚠️ **AI 未能生成有效的诊断结论。** 可能是由于 API 超时、网络拦截或模型不支持导致的空白返回。"

        return {"analysis": clean_text, "actions": actions}

    def _stream_diagnostic_completion(self, messages, llm_kwargs, session_id, tools=None, tool_choice=None):
        """
        统一处理流式诊断请求：
        - 自动聚合 Tool Calls
        - 自动把普通文本流推给前端

        原理说明：
        - 模型流式返回的 tool_call 参数可能被拆成多个 chunk，这里需要手动拼回完整 JSON
        - reasoning_content 与正文 content 会分开发送，前端可据此展示“思考流”和“结论流”
        """
        response = self.llm.completion( messages=messages, llm_kwargs=llm_kwargs, stream=True,
            tools=tools, tool_choice=(tool_choice or "auto") if tools is not None else None,
        )
        self._raise_if_cancelled(session_id, response)
        is_tool_call = False
        tool_calls_dict: dict[int, dict[str, str]] = {}
        final_text = "" 
        final_think = ""

        for chunk in response: # type: ignore
            self._raise_if_cancelled(session_id, response)
            if isinstance(chunk, tuple) or not chunk.choices: continue
            delta = chunk.choices[0].delta
            if not delta: continue
            if getattr(delta, "tool_calls", None):
                is_tool_call = True
                for tc in (delta.tool_calls or []):
                    idx = tc.index
                    if idx not in tool_calls_dict:
                        tool_calls_dict[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc.id and not tool_calls_dict[idx]["id"]:
                        tool_calls_dict[idx]["id"] = tc.id
                    if getattr(tc.function, "name", None) and not tool_calls_dict[idx]["name"]:
                        tool_calls_dict[idx]["name"] = tc.function.name or ""
                    if getattr(tc.function, "arguments", None):
                        tool_calls_dict[idx]["arguments"] += tc.function.arguments or ""
            # 兼容 DeepSeek-R1 等模型的 reasoning_content。
            if getattr(delta, "reasoning_content", None):
                think_chunk = self._normalize_litellm_content(delta.reasoning_content)
                if think_chunk:
                    final_think += think_chunk
                    # 把思考过程单独推给前端，便于展示“模型正在推理”的状态。
                    EventBus.emit('ai-chat-stream', {'session_id': session_id, 'type': 'reasoning', 'chunk': think_chunk})
            
            if getattr(delta, "content", None):
                content_chunk = self._normalize_litellm_content(delta.content)
                if content_chunk:
                    final_text += content_chunk
                    # 正文内容按 chunk 实时透传，保留逐字输出体验。
                    EventBus.emit('ai-chat-stream', {'session_id': session_id, 'type': 'content', 'chunk': content_chunk})
        
        self._raise_if_cancelled(session_id, response)
        formatted_tool_calls = []
        if is_tool_call:
            for _, tc in sorted(tool_calls_dict.items()):
                formatted_tool_calls.append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]}
                })

        return {
            "is_tool_call": is_tool_call,
            "tool_calls": formatted_tool_calls,
            "final_think": final_think,
            "final_text": final_text
        }

    def _safe_format(self, template: str, variables: dict) -> str:
        """
        安全格式化工具：只替换模板中存在的变量，忽略其他大括号。
        解决 JSON 示例与 Python .format() 的冲突。
        """
        # 使用正则匹配 {key}，只有当 key 在 variables 字典中时才替换
        # 这样即使模板里有 {"package_id": "xxx"}，因为 package_id 不在变量里，就会被原样保留
        pattern = re.compile(r'\{(\w+)\}')
        
        def replace(match):
            """仅替换白名单变量，未命中的 `{key}` 原样保留。"""
            key = match.group(1)
            return str(variables.get(key, match.group(0))) # 找不到就返回原样 {key}
            
        return pattern.sub(replace, template)

    # =========================================================================
    #  核心：单次同步执行 (供简单的闲聊或单次测试使用)
    # =========================================================================
    def execute_task(self, task_key: str, variables: Dict[str, Any], override_config: dict | None = None) -> Any:
        """
        执行单次同步 AI 任务。

        适用场景：
        - 普通问答
        - 结构化单次生成
        - 前端的轻量测试调用
        """
        if task_key not in self.prompts:
            raise ValueError(f"Prompt template '{task_key}' not found.")

        runtime_variables = dict(variables)
        if 'target_lang' not in runtime_variables:
            runtime_variables['target_lang'] = get_lang_by_code(settings.config.language)

        prompt_config = self.prompts[task_key]
        llm_kwargs = self._get_llm_kwargs(override_config)
        messages = self._build_prompt_messages(prompt_config, runtime_variables)

        try:
            response = self.llm.completion(messages=messages, llm_kwargs=llm_kwargs)
            result_text = self._normalize_litellm_content(response.choices[0].message.content)  # type: ignore
            return self._extract_json_from_text(result_text) or result_text # type: ignore
        except Exception as e:
            logger.error(f"AI Task execution failed: {e}")
            raise e

    # =========================================================================
    #  核心：异步并发批量执行引擎
    # =========================================================================
    async def _process_chunk(
        self,
        chunk_id: str,
        chunk_data: List[Dict],
        prompt_config: dict,
        variables: dict,
        llm_kwargs: dict,
        semaphore: asyncio.Semaphore,
    ):
        """处理单个批量分块，负责并发限流、请求重试和结果解析。"""
        async with semaphore:
            try:
                # 动态注入当前块的数据 (转为紧凑的JSON字符串发给大模型)
                chunk_variables = variables.copy()
                chunk_variables['batch_json_data'] = json.dumps(chunk_data, ensure_ascii=False)
                messages = self._build_prompt_messages(prompt_config, chunk_variables)
                # LiteLLM 神级特性：内置重试逻辑 num_retries=3
                # 如果遇到 429 Rate Limit 或 503，它会自动按指数退避等待并重试
                response = await self.llm.acompletion(
                    messages=messages,
                    llm_kwargs=llm_kwargs,
                    num_retries=3,
                    # 如果模型支持强制JSON输出，可以解开下面这行的注释
                    # response_format={"type": "json_object"},
                )
                result_text = self._normalize_litellm_content(response.choices[0].message.content)  # type: ignore
                parsed_json = self._extract_json_from_text(result_text, is_batch=True) # type: ignore
                return {"chunk_id": chunk_id, "status": "success", "data": parsed_json, "raw": result_text}

            except Exception as e:
                logger.error(f"Chunk {chunk_id} failed after retries: {e}")
                return {"chunk_id": chunk_id, "status": "error", "error": str(e), "data": None}

    async def execute_batch_task_async(self, task_key: str, items: List[Dict], variables: Dict[str, Any], task_event_id: str):
        """
        异步批量调度中心。

        这里负责把大批量任务拆成安全分块，并在多轮重试后把成功项与失败项统一整理返回。
        """
        if task_key not in self.prompts:
            raise ValueError(f"Prompt template '{task_key}' not found.")
        raw_cfg = settings.config.ai
        cfg = AIConfig(**raw_cfg) if isinstance(raw_cfg, dict) else raw_cfg
        llm_kwargs = self._get_llm_kwargs()
        prompt_config = self.prompts[task_key]
        max_concurrency = getattr(cfg, 'max_concurrency', 3)
        
        # 估算单个 Chunk 安全容量
        safe_input_tokens = max(1000, int(getattr(cfg, 'max_tokens', 4096)) - 1000)
        max_chars_per_chunk = int(safe_input_tokens * 1.5)
        
        # ------------------------------------------
        # 内部函数：智能分块算法
        # ------------------------------------------
        def build_smart_chunks(items_to_chunk):
            """按大致字符预算切分批量任务，避免单次输入过大。"""
            chunks_list = []
            current_chunk, current_chunk_chars = [], 0
            for item in items_to_chunk:
                # 预估 item 长度
                item_char_len = len(json.dumps(item, ensure_ascii=False))
                
                # 如果单个 item 已经超过最大限制，强制截断其描述
                if item_char_len > max_chars_per_chunk:
                    if 'description' in item and isinstance(item['description'], str):
                        # 保留头部，截断描述
                        keep_len = int(max_chars_per_chunk * 0.6)
                        item['description'] = item['description'][:keep_len] + "...(截断)"
                        item_char_len = len(json.dumps(item, ensure_ascii=False))

                # 判断是否需要新起一个 Chunk
                if current_chunk_chars + item_char_len > max_chars_per_chunk and len(current_chunk) > 0:
                    chunks_list.append(current_chunk)
                    current_chunk = [item]
                    current_chunk_chars = item_char_len
                else:
                    current_chunk.append(item)
                    current_chunk_chars += item_char_len
                    
            if current_chunk: chunks_list.append(current_chunk)
            return chunks_list

        # ------------------------------------------
        # 核心逻辑：多轮重试循环
        # ------------------------------------------
        total_initial_items = len(items)
        # 深拷贝以防修改原引用，且确保每个 item 都有 package_id
        pending_items = [dict(i) for i in items if 'package_id' in i]
        
        all_results = []
        successful_ids = set()
        max_logic_retries = 3 
        
        logger.info(f"AI Batch Task Started. Total: {total_initial_items}")

        for attempt in range(max_logic_retries):
            if not pending_items: 
                break 
            
            # 对剩余项重新进行智能分块
            chunks = build_smart_chunks(pending_items)
            logger.info(f"AI Task [Round {attempt+1}]: {len(pending_items)} pending items -> {len(chunks)} chunks.")
            
            semaphore = asyncio.Semaphore(max_concurrency)
            # 这里必须把 chunk 自身也传给 zip，因为需要知道发出去的是谁
            chunk_tasks = []
            
            for idx, chunk in enumerate(chunks):
                # 任务 ID 加上轮次前缀方便调试
                t_id = f"r{attempt}_c{idx}"
                coro = self._process_chunk(t_id, chunk, prompt_config, variables, llm_kwargs, semaphore)
                chunk_tasks.append((asyncio.create_task(coro), chunk))
            
            # 等待本轮所有 Chunk 完成
            for future, original_chunk in chunk_tasks:
                result = await future
                
                # 计算该 Chunk 期望返回的所有 ID
                expected_ids = {i.get('package_id') for i in original_chunk}
                
                if result['status'] == 'success' and isinstance(result['data'], list):
                    # 过滤有效数据：必须是字典，且 ID 必须属于本次请求的范围
                    valid_data = []
                    for d in result['data']:
                        if isinstance(d, dict):
                            pid = d.get('package_id')
                            if pid in expected_ids:
                                valid_data.append(d)
                                successful_ids.add(pid)
                    
                    if valid_data:
                        all_results.extend(valid_data)
                        EventBus.emit('ai-batch-chunk-ready', {'task_event_id': task_event_id, 'items': valid_data})
                
                # 实时更新进度
                percent = int((len(successful_ids) / total_initial_items) * 100)
                # 预留 5% 给最终结算
                percent = min(95, percent) 
                
                EventBus.emit_progress(
                    task_event_id,
                    "ai-batch",
                    status="running",
                    progress=percent,
                    message=f"正在推理... [第{attempt+1}轮] 成功: {len(successful_ids)}/{total_initial_items}",
                    metrics={
                        "attempt": attempt + 1,
                        "current": len(successful_ids),
                        "total": total_initial_items,
                        "task_key": task_key,
                        "title": "AI 批量处理",
                    },
                )

            # 计算下一轮的待处理项 (过滤掉已经成功的)
            pending_items = [item for item in pending_items if item.get('package_id') not in successful_ids]
            
            # 如果还有剩下的，稍作休息
            if pending_items: 
                await asyncio.sleep(1)

        # ------------------------------------------
        # 终极处理：失败兜底 (Fallback)
        # ------------------------------------------
        failed_count = len(pending_items)
        if failed_count > 0:
            logger.warning(f"AI Task Completed with {failed_count} failures. Generating empty placeholders.")
            failed_results = []
            for item in pending_items:
                # 生成占位对象，包含原始 ID 和失败标记
                failed_obj = {
                    "package_id": item["package_id"],
                    "alias_name": "", 
                    "notes": "",
                    "_failed": True # 标记为失败项，供前端判断
                }
                failed_results.append(failed_obj)
                all_results.append(failed_obj)
            
            # 将这些空数据发给前端
            EventBus.emit('ai-batch-chunk-ready', {'task_event_id': task_event_id, 'items': failed_results})

        # ------------------------------------------
        # 任务结束，发送 100% 信号
        # ------------------------------------------
        EventBus.emit_progress(
            task_event_id,
            "ai-batch",
            status="success",
            progress=100,
            message=f"推理结束！成功: {len(successful_ids)}, 失败: {failed_count}",
            metrics={
                "current": len(successful_ids),
                "total": total_initial_items,
                "failed_count": failed_count,
                "task_key": task_key,
                "title": "AI 批量处理",
            },
        )
        
        # 返回指定的结构化数据
        return {
            "success_count": len(successful_ids),
            "failed_count": failed_count,
            "results": all_results
        }

    # =========================================================================
    # 通用测试入口
    # =========================================================================
    def test_chat(self, message: str, override_config: dict) -> str:
        """
        用于前端“测试模型”按钮的方法。

        这里会主动把 temperature 留空、max_tokens 压到很小，
        目的是尽量用最低成本验证“能否通”和“接口是否兼容”。
        """
        safe_override = dict(override_config or {})
        # 测试按钮默认不强传 temperature
        safe_override["temperature"] = None
        # 测试只要极小输出即可
        safe_override["max_tokens"] = min(int(safe_override.get("max_tokens") or 64), 64)
        # 默认自动 endpoint 选择
        safe_override["endpoint_mode"] = safe_override.get("endpoint_mode") or "auto"
        llm_kwargs = self._get_llm_kwargs(safe_override)
        messages = [{"role": "user", "content": message}]
        try:
            response = self.llm.completion(messages=messages, llm_kwargs=llm_kwargs)
            return self._normalize_litellm_content(response.choices[0].message.content)   # type: ignore
        except Exception as e:
            logger.error(f"Test Chat Error: {e}")
            err_text = str(e)
            err_lower = err_text.lower()
            if "unknown provider for model" in err_lower:
                raise Exception(
                    "请求失败：当前代理接口无法正确路由这个模型。"
                    "很可能该模型需要走 /v1/responses，或者该中转尚未为此模型配置 provider 映射。"
                )
            if "temperature" in err_lower and "unsupported" in err_lower:
                raise Exception(
                    "请求失败：当前模型不接受你传入的 temperature。"
                    "建议将 temperature 留空，或使用自动兼容模式。"
                )
            raise Exception(f"请求失败: {err_text}")
        


    # =========================================================================
    #  Prompt 管理委托层
    #  这里保留旧方法名，避免 API 层和历史调用链继续改动
    # =========================================================================
    
    def _get_default_prompts(self):
        """兼容旧调用：返回默认 Prompt。"""
        return self.prompt_manager.get_defaults()
    
    def _ensure_default_prompts(self):
        """兼容旧调用：确保默认 Prompt 文件存在。"""
        self.prompt_manager.ensure_default_prompts()

    def _save_prompts_to_disk(self, data):
        """兼容旧调用：把 Prompt 数据写回磁盘。"""
        self.prompt_manager.save_all(data)
    
    def reload_prompts(self):
        """兼容旧调用：重新从磁盘加载 Prompt。"""
        return self.prompt_manager.reload()
    
    def save_prompt(self, prompt_id: str, prompt_data: dict):
        """兼容旧调用：新增或更新单个 Prompt。"""
        return self.prompt_manager.save_prompt(prompt_id, prompt_data)

    def delete_prompt(self, prompt_id: str):
        """兼容旧调用：删除单个 Prompt。"""
        return self.prompt_manager.delete_prompt(prompt_id)

    def reset_system_prompts(self):
        """兼容旧调用：重置系统 Prompt。"""
        return self.prompt_manager.reset_system_prompts()

    @property
    def prompts(self) -> dict:
        """对外暴露当前 Prompt 字典，兼容 API 层直接读取。"""
        return self.prompt_manager.prompts

    # =========================================================================
    # 诊断链路专用辅助方法
    # =========================================================================
    def _get_diagnostic_prompt_config(self, source_type: str) -> dict:
        """按日志来源选择对应的诊断提示词模板。"""
        task_key = "app_log_analysis" if source_type == "app" else "game_log_analysis"
        prompt_config = self.prompts.get(task_key)
        if not prompt_config:
            raise ValueError(f"Prompt template '{task_key}' not found.")
        return prompt_config

    def _build_diagnostic_variables(self, payload: dict, source_type: str, tool_executor: AIToolExecutor) -> tuple[dict, Any, Any]:
        """构造诊断提示词变量，并决定当前会话可用的工具集。"""
        variables = {
            "source_type": source_type,
            "filename": payload.get("filename", ""),
            "target_lang": get_lang_by_code(settings.config.language),
            "tools_description": "",
        }

        tools = None
        tool_choice = None
        if source_type == "game":
            enabled_tools_list = payload.get("enabled_tools", [])
            all_tools = tool_executor.get_tool_schemas()

            if not enabled_tools_list:
                tools_description = "【警告】当前你被禁止使用任何外部工具，你只能基于我提供的日志摘要直接进行分析！"
            else:
                tools = tool_executor.get_tool_schemas(enabled_tools_list)
                tool_choice = "auto"
                tools_description = "当前你可以使用以下工具进行深度调查：\n" + "\n".join(
                    f"- {tool['function']['name']}: {tool['function']['description']}"
                    for tool in tools
                )

            variables["tools_description"] = tools_description
            variables["all_tools"] = all_tools
            variables["tools"] = tools

        return variables, tools, tool_choice

    def _build_diagnostic_user_content(self, variables: dict, diagnosis_context: Any, question: str) -> str:
        """把当前文件、摘要和补充提问拼成 user_template 的输入上下文。"""
        user_content_parts = [
            f"当前日志来源: {variables['source_type']}",
            f"当前文件名: {variables['filename']}",
        ]

        if diagnosis_context:
            user_content_parts.append(
                f"以下是核心错误日志摘要：\n```json\n{json.dumps(diagnosis_context, ensure_ascii=False)}\n```"
            )
        if question:
            user_content_parts.append(f"用户的补充提问：{question}")

        return "\n\n".join(user_content_parts)

    def _execute_diagnostic_tool_calls(
        self,
        session_id: str,
        formatted_tool_calls: list[dict[str, Any]],
        tool_executor: AIToolExecutor,
        messages: list[dict],
        executed_tool_signatures: set[str],
    ) -> None:
        """执行一轮工具调用，并把结果回填到消息流和前端事件流。"""
        for tc in formatted_tool_calls:
            func_name = tc["function"]["name"]
            func_args = tc["function"]["arguments"]
            tool_start_at = time.perf_counter()

            EventBus.emit("ai-tool-call", {
                "session_id": session_id,
                "tool_id": tc["id"],
                "name": func_name,
                "arguments": func_args,
            })

            call_signature = f"{func_name}|{func_args}"
            if call_signature in executed_tool_signatures:
                tool_result = json.dumps({"error": DUPLICATE_TOOL_CALL_ERROR}, ensure_ascii=False)
                logger.warning(f"[AI防死锁] 拦截重复调用: {call_signature}")
            else:
                executed_tool_signatures.add(call_signature)
                self._raise_if_cancelled(session_id)
                try:
                    tool_result = tool_executor.execute(func_name, func_args)
                except AIRequestCancelled:
                    raise
                except Exception as tool_err:
                    logger.error(f"[AI诊断] 工具执行异常 tool={func_name}: {tool_err}", exc_info=True)
                    tool_result = json.dumps({
                        "error": f"工具 {func_name} 执行异常: {str(tool_err)}"
                    }, ensure_ascii=False)
                self._raise_if_cancelled(session_id)

            duration_ms = int((time.perf_counter() - tool_start_at) * 1000)
            tool_ok = True
            try:
                parsed_tool_result = json.loads(tool_result)
                if isinstance(parsed_tool_result, dict) and parsed_tool_result.get("error"):
                    tool_ok = False
            except Exception:
                pass

            logger.debug(
                f"[AI诊断] 工具完成 session_id={session_id} tool={func_name} "
                f"ok={tool_ok} duration_ms={duration_ms} result_chars={len(tool_result or '')}"
            )

            EventBus.emit("ai-tool-result", {
                "session_id": session_id,
                "tool_id": tc["id"],
                "status": "done" if tool_ok else "error",
                "duration_ms": duration_ms,
                "summary": self._summarize_tool_result(func_name, tool_result),
                "result": tool_result,
            })

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": func_name,
                "content": tool_result,
            })

    # =========================================================================
    # 诊断 Agent 主流程
    # =========================================================================
    def ai_diagnostic_chat(self, payload: dict, active_context, reader=None) -> list[dict[str, Any]] | dict[str, Any] | list[Any]:
        """
        处理前端的诊断请求，支持 Agentic 工具调用和多轮会话
        payload: { "history": [...], "diagnosis_context": {...}, "question": "..." }
        """
        session_id = payload.get("session_id", str(uuid.uuid4()))
        token_usage = self._create_token_usage()
        try:
            tool_executor = AIToolExecutor(active_context, payload, reader)
            source_type = payload.get("log_source_type", "game")

            # 第一步：根据来源和上下文准备 Prompt 变量与工具权限。
            prompt_config = self._get_diagnostic_prompt_config(source_type)
            variables, tools, tool_choice = self._build_diagnostic_variables(payload, source_type, tool_executor)
            diagnosis_context = payload.get("diagnosis_context", None)
            question = payload.get("question", "")
            variables["user_content"] = self._build_diagnostic_user_content(variables, diagnosis_context, question)

            # 第二步：把历史消息和当前问题组装成最终消息流。
            messages = self._build_prompt_messages(prompt_config, variables, payload.get("history", []))

            llm_kwargs = self._get_llm_kwargs()
            model_name = llm_kwargs.get("model", settings.config.ai.model)
            token_usage = self._create_token_usage(model_name)

            logger.debug(
                f"[AI诊断] 会话开始 session_id={session_id} "
                f"history={len(payload.get('history', []))} has_context={bool(diagnosis_context)} "
                f"context_items={len(diagnosis_context.get('error_table_of_contents', [])) if isinstance(diagnosis_context, dict) else 0}"
            )

            loop_count = 0
            executed_tool_signatures = set()

            while loop_count < DIAGNOSTIC_MAX_LOOPS:
                loop_count += 1
                try:
                    # 每轮都先按“当前 messages”估算一次输入成本，便于前端展示累计消耗。
                    prompt_tokens_this_round = self._estimate_messages_tokens(messages, model_name)
                    token_usage["estimated_prompt_tokens"] += prompt_tokens_this_round
                    token_usage["estimated_total_tokens"] += prompt_tokens_this_round
                    logger.debug(
                        f"[AI诊断] 进入工具轮 session_id={session_id} loop={loop_count}/{DIAGNOSTIC_MAX_LOOPS} "
                        f"messages={len(messages)} prompt_tokens≈{prompt_tokens_this_round}"
                    )
                    stream_result = self._run_diagnostic_completion_with_fallback(
                        messages=messages,
                        llm_kwargs=llm_kwargs,
                        session_id=session_id,
                        tools=tools,
                        tool_choice=tool_choice
                    )
                    completion_payload = (
                        json.dumps(stream_result["tool_calls"], ensure_ascii=False)
                        if stream_result["is_tool_call"] else stream_result["final_text"]
                    )
                    output_tk = self._estimate_text_tokens(completion_payload, model_name)
                    token_usage["estimated_completion_tokens"] += output_tk
                    token_usage["estimated_total_tokens"] += output_tk

                    # 如果模型返回的是工具调用计划，则执行工具并把结果回灌回消息流。
                    if stream_result["is_tool_call"]:
                        token_usage["tool_rounds"] += 1
                        formatted_tool_calls = stream_result["tool_calls"]
                        messages.append({"role": "assistant", "content": "", "tool_calls": formatted_tool_calls})
                        logger.debug(
                            f"[AI诊断] 触发工具轮 session_id={session_id} loop={loop_count} "
                            f"tool_count={len(formatted_tool_calls)}"
                        )
                        self._execute_diagnostic_tool_calls(
                            session_id=session_id,
                            formatted_tool_calls=formatted_tool_calls,
                            tool_executor=tool_executor,
                            messages=messages,
                            executed_tool_signatures=executed_tool_signatures,
                        )
                        continue

                    # 否则说明模型已经收敛到最终文本，直接进入结论解析阶段。
                    final_response = self._parse_diagnostic_final_text(stream_result["final_text"], stream_result.get("final_think", ""))
                    token_usage["estimated_total_tokens"] = (
                        token_usage["estimated_prompt_tokens"] + token_usage["estimated_completion_tokens"]
                    )
                    final_response["token_usage"] = token_usage

                    logger.debug(
                        f"[AI诊断] 会话完成 session_id={session_id} loop={loop_count} "
                        f"analysis_chars={len(final_response.get('analysis', ''))} "
                        f"total_tokens≈{token_usage['estimated_total_tokens']}"
                    )
                    return final_response
                
                except AIRequestCancelled:
                    raise
                except Exception as e:
                    logger.error(f"AI Diagnostic Error: {str(e)}", exc_info=True)
                    return self._build_diagnostic_error_response(e, token_usage)

            # 如果多轮查证后仍不收敛，则强制进入“禁止再调工具”的总结轮。
            logger.warning(f"[AI诊断] 工具轮达到上限，转入强制总结 session_id={session_id}")
            token_usage["forced_final_round"] = True
            forced_messages = messages + [{
                "role": "system",
                "content": FORCED_DIAGNOSTIC_SUMMARY_PROMPT,
            }]

            try:
                prompt_tokens_this_round = self._estimate_messages_tokens(forced_messages, model_name)
                token_usage["estimated_prompt_tokens"] += prompt_tokens_this_round
                logger.debug(
                    f"[AI诊断] 强制总结开始 session_id={session_id} "
                    f"messages={len(forced_messages)} prompt_tokens≈{prompt_tokens_this_round}"
                )
                stream_result = self._run_diagnostic_completion_with_fallback(
                    messages=forced_messages,
                    llm_kwargs=llm_kwargs,
                    session_id=session_id,
                    tools=None,
                    tool_choice=None
                )
                token_usage["estimated_completion_tokens"] += self._estimate_text_tokens(stream_result["final_text"], model_name)
                token_usage["estimated_total_tokens"] = (
                    token_usage["estimated_prompt_tokens"] + token_usage["estimated_completion_tokens"]
                )

                final_response = self._parse_diagnostic_final_text(stream_result["final_text"], stream_result.get("final_think", ""))
                if not final_response.get("analysis"):
                    final_response["analysis"] = "AI 已完成查证，但没有生成有效总结文本。建议查看上方工具步骤详情，优先核对关键上下文和模组排序。"
                final_response["token_usage"] = token_usage

                logger.debug(
                    f"[AI诊断] 强制总结完成 session_id={session_id} "
                    f"analysis_chars={len(final_response.get('analysis', ''))} "
                    f"total_tokens≈{token_usage['estimated_total_tokens']}"
                )
                return final_response
            except AIRequestCancelled:
                raise
            except Exception as e:
                logger.error(f"AI Diagnostic Error: {str(e)}", exc_info=True)
                return self._build_diagnostic_error_response(e, token_usage, "点击展开查看技术报错详情")
        
        except AIRequestCancelled:
            logger.info(f"[AI诊断] 用户已取消 session_id={session_id}")
            EventBus.emit('ai-chat-cancelled', {'session_id': session_id})
            return {
                "cancelled": True,
                "analysis": "",
                "actions": [],
                "token_usage": token_usage
            }
        finally:
            self._clear_cancelled_request(session_id)

    # =========================================================================
    # 诊断取消控制
    # =========================================================================
    def cancel_diagnostic_request(self, session_id: str) -> bool:
        """标记某个诊断会话为已取消。"""
        if not session_id:
            return False
        with self._cancel_lock:
            self._cancelled_sessions.add(session_id)
        logger.info(f"[AI诊断] 收到取消请求 session_id={session_id}")
        return True
    
    def _clear_cancelled_request(self, session_id: str):
        """在会话结束后清理取消标记，避免污染下一次同 ID 检查。"""
        if not session_id:
            return
        with self._cancel_lock:
            self._cancelled_sessions.discard(session_id)
            
    def _is_diagnostic_cancelled(self, session_id: str) -> bool:
        """查询当前诊断会话是否已经被外部取消。"""
        if not session_id:
            return False
        with self._cancel_lock:
            return session_id in self._cancelled_sessions
        
    def _raise_if_cancelled(self, session_id: str, stream_response=None):
        """在关键步骤主动中断，必要时顺手关闭底层流式响应。"""
        if not self._is_diagnostic_cancelled(session_id):
            return
        try:
            closer = getattr(stream_response, "close", None)
            if callable(closer):
                closer()
        except Exception:
            pass
        raise AIRequestCancelled(f"AI diagnostic cancelled: {session_id}")

    
class AIRequestCancelled(Exception):
    """用户主动取消的诊断请求"""
    pass
    
