# backend/managers/mgr_ai.py
import json
import linecache
import os
import re
import time
import asyncio
from typing import List, Dict, Any, Union
from dataclasses import asdict
import uuid

from backend.managers.mgr_ai_tools import AIToolExecutor

# 禁用远程模型成本映射
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

# 引入 LiteLLM 的异步和同步方法
import litellm
from litellm import completion, acompletion
import requests
from json_repair import repair_json

from backend.settings import DATA_DIR, settings
from backend.utils.logger import logger
from backend.utils.constants import get_lang_by_code
from backend.utils.event_bus import EventBus
from backend.database.dao import ModDAO
from backend.managers.mgr_rules import RuleManager
from backend.managers.mgr_game_logs import LogCondenser
from backend.managers.mgr_network import network_mgr
from backend.database.dao import ModDAO
from backend.managers.mgr_load_order import LoadOrderManager
from backend.managers.mgr_game_logs import LogCondenser

class AIManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AIManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized: return
        self._initialized = True
        # 如果系统开启了 Debug 模式，开启 LiteLLM 的底层日志，打印完整的请求和响应
        if settings.config.debug_mode:
            os.environ['LITELLM_LOG'] = 'DEBUG'
        # 轻量级缓存字典，用于缓存自定义接口的模型列表
        # 格式: { "provider_baseurl_apikey": (timestamp, [models...]) }
        self._model_cache = {}
        self._cache_ttl = 300  # 缓存有效期 5 分钟 (300秒)
        
        # 加载提示词库
        self.prompts = {}
        self.prompt_file = str(DATA_DIR / 'prompts.json')
        # 1. 确保目录存在
        os.makedirs(os.path.dirname(self.prompt_file), exist_ok=True)
        # 2. 检查并生成默认配置
        self._ensure_default_prompts()
        # 3. 加载
        self.reload_prompts()
        
        logger.info("AI Manager initialized with LiteLLM.")


    # =========================================================================
    #  厂商与模型列表探测 (Providers & Models Discovery)
    # =========================================================================
    
    def get_providers(self, api_type: str) -> List[Dict[str, str]]:
        """
        获取支持的厂商或协议列表
        返回格式: [{"value": "openai", "label": "OpenAI"}, ...]
        """
        if api_type == 'custom':
            # 自定义模式：返回固定的标准协议
            return [
                {"value": "openai", "label": "OpenAI 兼容协议 (vLLM/中转/LM Studio)"},
                {"value": "ollama", "label": "Ollama 本地协议"},
                {"value": "gemini", "label": "Google Gemini 兼容协议 (中转/代理)"}
            ]
            
        # 官方模式：动态获取 LiteLLM 支持的真实厂商
        all_providers = list(litellm.models_by_provider.keys())
        # 定义常用厂商（置顶显示，按此顺序排列）
        common = ['openai', 'anthropic', 'gemini', 'deepseek', 'xai', 'openrouter',  'minimax', 'ollama', 'mistral', 'groq']
        
        result = []
        # 1. 优先加入常用厂商
        for p in common:
            if p in all_providers:
                # 简单格式化首字母大写作为显示名称
                label = p.replace('_', ' ').title()
                result.append({"value": p, "label": label})
                all_providers.remove(p)
                
        # 2. 剩余厂商按字母顺序追加 (过滤掉一些非常用的奇怪系统名称)
        ignored = ['custom', 'custom_openai', 'litellm_proxy', 'hosted_vllm']
        others = sorted([p for p in all_providers if p not in ignored])
        for p in others:
            result.append({"value": p, "label": p.replace('_', ' ').title()})
            
        return result

    def get_models(self, config_dict: dict) -> List[str]:
        """
        获取可用模型列表 (带缓存机制)
        :param config_dict: {api_type, provider, base_url, api_key}
        """
        api_type = config_dict.get('api_type', 'official')
        provider = config_dict.get('provider', '')
        
        # 1. 官方模式：直接从 LiteLLM 内存字典获取，无网络延迟，无需缓存
        if api_type == 'official':
            if not provider: return []
            models = list(litellm.models_by_provider.get(provider, []))
            models.sort(key=lambda x: x.lower())
            return models
            
        # 2. 自定义模式：需要发起网络请求
        base_url = config_dict.get('base_url', '').rstrip('/')
        api_key = config_dict.get('api_key', '')
        
        if not base_url: return []
        
        # 检查缓存
        cache_key = f"{provider}_{base_url}_{api_key}"
        if cache_key in self._model_cache:
            timestamp, cached_models = self._model_cache[cache_key]
            if time.time() - timestamp < self._cache_ttl:
                logger.debug(f"AI Models Cache hit for {base_url}")
                cached_models.sort(key=lambda x: x.lower())
                return cached_models
                
        # 缓存未命中，发起请求
        models = self._fetch_custom_models(provider, base_url, api_key)
        
        # 写入缓存
        if models: # 只有获取成功才缓存，防止缓存错误的空结果
            self._model_cache[cache_key] = (time.time(), models)
        # 按名称排序
        models.sort(key=lambda x: x.lower())
        return models

    def _fetch_custom_models(self, provider: str, base_url: str, api_key: str) -> List[str]:
        """(内部方法) 发送网络请求探测代理/本地服务的模型列表"""
        proxies = None
        if settings.config.network.use_proxy_on_ai:
            url = network_mgr.get_proxy_url()
            if url: proxies = {"http": url, "https": url}
            
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        try:
            # Ollama 格式探测
            if provider == 'ollama':
                resp = requests.get(f"{base_url}/api/tags", proxies=proxies, timeout=10)
                if resp.status_code == 200:
                    return [m['name'] for m in resp.json().get('models', [])]
            elif provider == 'gemini':
                # Gemini 协议通常在 URL 中带 key，或者从 Header 取
                resp = requests.get(f"{base_url}/v1/models", params={"key": api_key}, proxies=proxies, timeout=10)
                if resp.status_code == 200:
                    # 返回结果通常是 models/gemini-1.5-pro，需要剥离 models/ 前缀
                    return [m['name'].replace('models/', '') for m in resp.json().get('models', []) 
                            if 'generateContent' in m.get('supportedGenerationMethods', [])]
            # OpenAI 兼容格式探测 (LM Studio, vLLM, DeepSeek, 各大中转等)
            else: 
                # 兼容处理：有的 base_url 带有 /v1，有的没有
                endpoints = ["/models"] if base_url.endswith("/v1") else ["/v1/models", "/models"]
                for endpoint in endpoints:
                    try:
                        resp = requests.get(f"{base_url}{endpoint}", headers=headers, proxies=proxies, timeout=10)
                        if resp.status_code == 200:
                            data = resp.json()
                            if 'data' in data: # OpenAI 标准格式
                                return [item['id'] for item in data['data']]
                    except requests.exceptions.RequestException:
                        continue # 当前 endpoint 失败，尝试下一个
                        
        except Exception as e:
            logger.warning(f"Failed to fetch custom models from {base_url}: {e}")
            
        return []
    # =========================================================================
    #  LiteLLM 参数组装路由 (Routing)
    # =========================================================================

    def _get_litellm_kwargs(self, override_config: dict = {}) -> dict:
        """
        核心路由：组装 LiteLLM 需要的参数，彻底分离官方与代理逻辑
        """
        # 如果 AI 设置中明确关闭了代理，即使全局开启了，也对 AI 进程屏蔽它
        if not settings.config.network.use_proxy_on_ai:
            os.environ.pop('HTTP_PROXY', None)
            os.environ.pop('HTTPS_PROXY', None)
        else:
            # 确保应用最新的全局代理设置
            from backend.managers.mgr_network import network_mgr
            network_mgr.apply_proxy_settings()
            
        from backend.settings import AIConfig
        raw_cfg = settings.config.ai
        cfg = AIConfig(**raw_cfg) if isinstance(raw_cfg, dict) else raw_cfg
        
        if override_config:
            current_dict = asdict(cfg)
            current_dict.update(override_config)
            cfg = AIConfig(**current_dict)

        # 1. 基础公共参数
        kwargs = {
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
            # "stream": False,    # 显式禁用流式传输
            # 伪装成正常的 Chrome 浏览器，穿透绝大多数中转站的 Cloudflare 盾
            "extra_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json",
            }
        }

        # 2. 路由分支
        if cfg.api_type == 'official':
            # 官方原生模式
            # 如果模型名称未自带提供商前缀（如 gpt-4o 没有 openai/ 前缀），LiteLLM 也能自动识别，但为了极致安全，显式传入 custom_llm_provider
            kwargs["model"] = cfg.model
            kwargs["custom_llm_provider"] = cfg.provider
            kwargs["api_key"] = cfg.api_key or "dummy_key"
            if cfg.base_url: # 允许部分高阶用户为官方接口配反代
                kwargs["api_base"] = cfg.base_url.rstrip('/')
                
        else:
            # 自定义/代理模式 (强制使用前缀路由，接管底层处理)
            kwargs["api_key"] = cfg.api_key or "dummy_key" # 本地部署常无 key，补 dummy 防止库报错
            kwargs["api_base"] = cfg.base_url.rstrip('/')
            
            if cfg.provider == 'ollama':
                kwargs["model"] = f"ollama/{cfg.model}"
            elif cfg.provider == 'gemini':
                # 强制使用 gemini/ 前缀路由，LiteLLM 将采用 Google 协议格式
                kwargs["model"] = f"gemini/{cfg.model}"
            else:
                # openai 
                # 这里加上 openai/ 前缀是 LiteLLM 的终极奥义，它会强制按 OpenAI 官方数据结构请求目标 base_url
                kwargs["model"] = f"openai/{cfg.model}"

        # 核心逻辑：判断 AI 代理开关
        if settings.config.network.use_proxy_on_ai:
            proxy_url = network_mgr.get_proxy_url()
            if proxy_url:
                kwargs["proxy_url"] = proxy_url
        else:
            # 2. 如果 AI 明确关闭了代理，但全局代理可能开着
            # 为了防止 LiteLLM 自动读取环境变量，要显式告诉它：不要代理
            kwargs["proxy_url"] = None 
        
        return kwargs

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
        if not text:
            return 0
        try:
            return int(litellm.token_counter(model=model_name, text=text))
        except Exception as e:
            logger.debug(f"[AI诊断] 文本 Token 估算失败，改走字符兜底: {e}")
            return max(1, len(text) // 3)

    def _estimate_messages_tokens(self, messages: list[dict], model_name: str) -> int:
        """
        估算整轮 messages 进入模型前的输入 Token。
        某些模型不返回 usage 时，后端统一用这个值来做累计统计。
        """
        if not messages:
            return 0
        try:
            return int(litellm.token_counter(model=model_name, messages=messages))
        except Exception as e:
            logger.debug(f"[AI诊断] Messages Token 估算失败，改走文本拼接兜底: {e}")
            merged_text = "\n".join(str(m.get("content", "")) for m in messages)
            return self._estimate_text_tokens(merged_text, model_name)

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

        response = completion(messages=messages, **request_kwargs)
        message = response.choices[0].message # type: ignore
        tool_calls = getattr(message, "tool_calls", None) or []

        if tool_calls:
            formatted_tool_calls = []
            for index, tool_call in enumerate(tool_calls):
                function_obj = getattr(tool_call, "function", None)
                formatted_tool_calls.append({
                    "id": getattr(tool_call, "id", None) or f"tool_call_{index}",
                    "type": getattr(tool_call, "type", None) or "function",
                    "function": {
                        "name": getattr(function_obj, "name", None) or "",
                        "arguments": getattr(function_obj, "arguments", None) or "{}"
                    }
                })
            return {"is_tool_call": True, "tool_calls": formatted_tool_calls, "final_text": ""}

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
            return self._stream_diagnostic_completion( messages=messages, llm_kwargs=llm_kwargs, session_id=session_id, tools=tools, tool_choice=tool_choice )
        except Exception as e:
            if not self._is_retryable_stream_error(e): raise
            logger.warning(
                f"[AI诊断] 流式输出中断，自动回退为非流式补救 "
                f"session_id={session_id} error={type(e).__name__}: {e}"
            )
            return self._complete_diagnostic_without_stream( messages=messages, llm_kwargs=llm_kwargs, tools=tools, tool_choice=tool_choice )

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

    def _parse_diagnostic_final_text(self, final_text: str, reasoning_text: str = "") -> dict[str, Any]:
        # 优先寻找 <actions> 包裹的 JSON
        action_match = re.search(r'[-\s]*<actions>\s*(.*?)\s*</actions>', final_text, re.IGNORECASE | re.DOTALL)
        actions =[]
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
            if reasoning_text.strip():
                clean_text = "⚠️ **AI 已耗尽最大输出长度限制，未能生成最终结论。**\n\n<details><summary>点击查看 AI 的深度思考过程</summary>\n\n```text\n" + reasoning_text + "\n```\n</details>"
            else:
                clean_text = "⚠️ **AI 未能生成有效的诊断结论。** 可能是由于 API 超时、网络拦截或模型不支持导致的空白返回。"

        return {"analysis": clean_text, "actions": actions}

    def _stream_diagnostic_completion( self, messages: list[dict], llm_kwargs: dict, session_id: str, tools: list[dict] | None = None, tool_choice: str | None = None) -> dict[str, Any]:
        """
        统一处理流式诊断请求：
        - 自动聚合 Tool Calls
        - 自动把普通文本流推给前端
        """
        completion_kwargs = {
            "messages": messages,
            "stream": True,
            **llm_kwargs
        }
        if tools is not None:
            completion_kwargs["tools"] = tools
            completion_kwargs["tool_choice"] = tool_choice or "auto"

        response = completion(**completion_kwargs)
        is_tool_call = False
        tool_calls_dict: dict[int, dict[str, str]] = {}
        final_text = "" 
        final_think = ""

        for chunk in response:
            if isinstance(chunk, tuple) or not chunk.choices: continue
            delta = chunk.choices[0].delta
            if not delta: continue
            if getattr(delta, "tool_calls", None):
                is_tool_call = True
                for tc in (delta.tool_calls or []):
                    idx = tc.index
                    if idx not in tool_calls_dict:
                        tool_calls_dict[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc.id:
                        tool_calls_dict[idx]["id"] += tc.id
                    if getattr(tc.function, "name", None):
                        tool_calls_dict[idx]["name"] += tc.function.name or ""
                    if getattr(tc.function, "arguments", None):
                        tool_calls_dict[idx]["arguments"] += tc.function.arguments
            # 兼容 DeepSeek-R1 等模型的 reasoning_content
            if getattr(delta, "reasoning_content", None):
                think_chunk = delta.reasoning_content or ""
                final_think += think_chunk
                # 告诉前端：这是思考流
                EventBus.emit('ai-chat-stream', {'session_id': session_id, 'type': 'reasoning', 'chunk': think_chunk})
            
            if getattr(delta, "content", None):
                content_chunk = delta.content or ""
                final_text += content_chunk
                # 告诉前端：这是正文流
                EventBus.emit('ai-chat-stream', {'session_id': session_id, 'type': 'content', 'chunk': content_chunk})

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
            key = match.group(1)
            return str(variables.get(key, match.group(0))) # 找不到就返回原样 {key}
            
        return pattern.sub(replace, template)

    # =========================================================================
    #  核心：单次同步执行 (供简单的闲聊或单次测试使用)
    # =========================================================================
    def execute_task(self, task_key: str, variables: Dict[str, Any], override_config: dict = {}) -> Any:
        """
        执行具体的 AI 任务
        :param task_key: prompts.json 中的 key (如 'translation')
        :param variables: 模板变量 (如 {'content': '...', 'target_lang': 'zh-cn'})
        """
        if task_key not in self.prompts:
            raise ValueError(f"Prompt template '{task_key}' not found.")
        
        # 1. 自动注入目标语言 (如果变量里没传)
        if 'target_lang' not in variables:
            # 获取当前软件语言设置 (如 'zh-cn')
            # 转换为自然语言 (如 'Simplified Chinese')
            variables['target_lang'] = get_lang_by_code(settings.config.language)

        prompt_config = self.prompts[task_key]
        system_prompt = self._safe_format(prompt_config.get('system', ''), variables)
        user_content = self._safe_format(prompt_config.get('user_template', ''), variables)

        llm_kwargs = self._get_litellm_kwargs(override_config)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        try:
            # LiteLLM 统一同步调用
            response = completion(messages=messages, **llm_kwargs)
            result_text = response.choices[0].message.content # type: ignore
            return self._extract_json_from_text(result_text) or result_text # type: ignore
        except Exception as e:
            logger.error(f"AI Task execution failed: {e}")
            raise e

    # =========================================================================
    #  核心：异步并发批量执行引擎
    # =========================================================================
    async def _process_chunk(self, chunk_id: str, chunk_data: List[Dict], task_key: str, variables: dict, llm_kwargs: dict, semaphore: asyncio.Semaphore):
        """处理单个分块，包含并发控制和自动重试"""
        async with semaphore:
            try:
                # 动态注入当前块的数据 (转为紧凑的JSON字符串发给大模型)
                chunk_variables = variables.copy()
                chunk_variables['batch_json_data'] = json.dumps(chunk_data, ensure_ascii=False)
                prompt_config = self.prompts[task_key]
                system_prompt = self._safe_format(prompt_config.get('system', ''), chunk_variables)
                user_content = self._safe_format(prompt_config.get('user_template', ''), chunk_variables)
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ]
                # LiteLLM 神级特性：内置重试逻辑 num_retries=3
                # 如果遇到 429 Rate Limit 或 503，它会自动按指数退避等待并重试
                response = await acompletion(
                    messages=messages,
                    num_retries=3,
                    # 如果模型支持强制JSON输出，可以解开下面这行的注释
                    # response_format={"type": "json_object"}, 
                    **llm_kwargs
                )
                result_text = response.choices[0].message.content # type: ignore
                parsed_json = self._extract_json_from_text(result_text, is_batch=True) # type: ignore
                return {"chunk_id": chunk_id, "status": "success", "data": parsed_json, "raw": result_text}

            except Exception as e:
                logger.error(f"Chunk {chunk_id} failed after retries: {e}")
                return {"chunk_id": chunk_id, "status": "error", "error": str(e), "data": None}

    async def execute_batch_task_async(self, task_key: str, items: List[Dict], variables: Dict[str, Any], task_event_id: str):
        """
        异步批量调度中心 (集成智能重试 + 失败兜底 + 结构化返回)
        """
        cfg = settings.config.ai
        llm_kwargs = self._get_litellm_kwargs()
        max_concurrency = getattr(cfg, 'max_concurrency', 3)
        
        # 估算单个 Chunk 安全容量
        safe_input_tokens = max(1000, int(cfg.max_tokens) - 1000) 
        max_chars_per_chunk = int(safe_input_tokens * 1.5)
        
        # ------------------------------------------
        # 内部函数：智能分块算法
        # ------------------------------------------
        def build_smart_chunks(items_to_chunk):
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
        pending_items = [i for i in items if 'package_id' in i] 
        
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
                coro = self._process_chunk(t_id, chunk, task_key, variables, llm_kwargs, semaphore)
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
                        EventBus.emit('ai-batch-chunk-ready', valid_data)
                
                # 实时更新进度
                percent = int((len(successful_ids) / total_initial_items) * 100)
                # 预留 5% 给最终结算
                percent = min(95, percent) 
                
                EventBus.emit('ai-batch-progress', {
                    'scanning': True, 
                    'percent': percent,
                    'message': f"正在推理... [第{attempt+1}轮] 成功: {len(successful_ids)}/{total_initial_items}"
                })

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
            EventBus.emit('ai-batch-chunk-ready', failed_results)

        # ------------------------------------------
        # 任务结束，发送 100% 信号
        # ------------------------------------------
        EventBus.emit('ai-batch-progress', {
            'scanning': True, 
            'percent': 100,
            'message': f"推理结束！成功: {len(successful_ids)}, 失败: {failed_count}"
        })
        
        # 返回指定的结构化数据
        return {
            "success_count": len(successful_ids),
            "failed_count": failed_count,
            "results": all_results
        }
    
    def test_chat(self, message: str, override_config: dict) -> str:
        """
        用于前端“测试模型”按钮的方法
        """
        llm_kwargs = self._get_litellm_kwargs(override_config)
        messages = [{"role": "user", "content": message}]
        
        try:
            # 同步调用测试是否连通
            response = completion(messages=messages, **llm_kwargs)
            return response.choices[0].message.content # type: ignore
        except Exception as e:
            logger.error(f"Test Chat Error: {e}")
            raise Exception(f"请求失败: {str(e)}")
        


    # =========================================================================
    #  系统提示词管理 (System Prompts Management)
    #  系统提示词是不可删除的，只能修改
    # =========================================================================
    
    def _get_default_prompts(self):
        """定义系统默认提示词"""
        return {
            "chat": {
                "name": "自由对话",
                "description": "普通的对话模式",
                "system": "你是一个乐于助人的RimWorld游戏专家，你的回答应该总是使用{target_lang}。",
                "user_template": "{message}"
            },
            "alias_generation": {
                "name": "智能别名与通俗备注",
                "description": "生成新手也能瞬间秒懂的别名和备注说明",
                "system": "你是一个深耕 RimWorld 社区多年的老玩家，也是一位极具亲和力的模组讲解员。你的任务是把复杂的模组信息翻译成**连完全不懂电脑的新手玩家**都能瞬间听懂的话。\n\n**1. 别名 (alias_name) 准则：**\n- 必须原样保留名称中的元数据（如果有），如 `[作者名]`、`(版本如：Continued)` 等，严禁改动这些括号内容。\n- 核心名称要像玩家在群里聊天一样自然，直接称呼功能或物品，表述模糊的可以用“XX补丁”、“XX扩展”、“XX增强”等直观词汇。\n\n**2. 备注 (notes) 准则 (核心修改)：**\n- **禁止使用专业术语**：严禁出现“注入”、“XML”、“Def”、“程序集”、“算法”等词汇。如果一定要解释技术，请用生活中的例子打比方（比如：它像胶水一样把两个原本不合的模组粘在一起）。\n- **功能导向**：直接告诉玩家“装了这个之后，你的游戏里会多出什么”或者“它帮你解决了哪个让你头疼的问题”。\n- **语言风格**：通俗易懂，极致白话。字数控制在 100-200 字之间。 **排版建议**：用客观但亲切的语气描述，不要像说明书，要像老大哥带新手。\n\n请以 JSON 格式返回结果，包含两个字段：'alias_name' (别名) 和 'notes' (备注)。不要包含 Markdown 代码块标签。！！！严禁在生成的内容中使用双引号(可以改用单引号或书名号)，否则会导致系统崩溃！！！",
                "user_template": "模组原名: {name}\n模组简介:\n{description}"
            },
            "batch_alias_generation": {
                "name": "批量别名与备注生成",
                "description": "一次性为多个Mod生成通俗别名和备注",
                "system": """### Role\n你是一位深耕 RimWorld (环世界) 社区多年的资深玩家，也是一位极具亲和力的“模组导游”。你的受众是**完全不懂代码、不懂游戏术语的新手玩家**。\n\n### Task\n接收一组原始 Mod 数据，将其翻译并转化为用户语言 {target_lang}，生成通俗易懂的“别名”和“备注”。\n\n### Input Format\nJSON Array: [ {"package_id": "...", "name": "...", "description": "..."} ]\n\n### Output Format\nStrict JSON Array: [ {"package_id": "...", "alias_name": "...", "notes": "..."} ]\n\n### Style Guidelines\n1. **别名 (alias_name)**:\n   - **保留元数据**: 必须保留原名中括号内的内容（如 `[1.4]`, `(Continued)`, `[HMC]`），不要翻译或删除它们。\n   - **直观命名**: 抛弃晦涩的原名，直接用功能命名。例如 "Wall Light" -> "墙灯"，"RimFridige" -> "冰箱"。\n   - **格式**: 简短有力，不要超过 20 个字。\n\n2. **备注 (notes)**:\n   - **🚫 禁止术语**: 严禁出现 "XML", "Def", "Harmony", "渲染", "程序集", "注入" 等技术词汇。\n   - **✅ 功能导向**: 用生活化的比喻告诉玩家“装了这个能干嘛”或“解决了什么痛点”。\n   - **🗣 语气风格**: 像群里的老大哥在推荐 Mod。幽默、直白、接地气。\n   - **长度**: 控制在 100-200 字之间，通俗易懂，极致白话。\n\n### ⚠️ Technical Constraints (CRITICAL)\n1. **Output ONLY JSON**: Do NOT output Markdown blocks (```json), explanations, or any text outside the JSON array.\n2. **Quote Handling**: To prevent JSON syntax errors, **use SINGLE QUOTES (') or CHINESE QUOTES (「」 or “”) inside the content**. NEVER use double quotes (") inside the value strings.\n   - ❌ Wrong: "notes": "It adds "smart" weapons."\n   - ✅ Right: "notes": "It adds 'smart' weapons."\n3. **ID Matching**: The `package_id` must match the input exactly. Do not hallucinate new IDs.\n4. **Language**: Ensure all generated content is in {target_lang}.\n\n### Example\n**Input**:\n[\n  {"package_id": "ludeon.rimworld", "name": "Core", "description": "The core game data."}\n]\n\n**Output**:\n[\n  {\n    "package_id": "ludeon.rimworld",\n    "alias_name": "游戏核心",\n    "notes": "这是游戏本体的心脏，没它你连\\"游戏\\"都打不开，千万别动它。"\n  }\n]""",
                "user_template": """请根据 System 指令，将以下模组数据转化为面向新手的【通俗别名(alias_name)】与【大白话备注(notes)】。\n要求：ID 精准匹配、语气极度口语化、严禁技术术语；输出严格 JSON 数组，且值内仅限使用单引号，不包含 Markdown 标记。\n\n待处理数据：\n{batch_json_data}"""
            },
            "app_log_analysis": {
                "name": "软件日志分析",
                "description": "分析 RimModManager 自身的 Python/Vue 报错日志，供开发者使用。",
                "system": """你是一位资深的桌面应用开发专家，精通 Vue3 前端和 Python/Pywebview 后端架构。\n你的任务是分析这款名为 RimModManager 的软件自身的运行报错日志。\n\n- **日志来源 (source_type)**: {source_type}\n- **日志文件名 (filename)**: {filename}\n\n请严格遵守以下诊断流程：\n1. 提供的日志摘要包含 `target_line` (物理行号) 和 `stack_preview` (错误堆栈)。\n2. 重点寻找 Python 端的 `Traceback`、依赖报错，或前端 Vue 的组件渲染异常。\n3. 请直接基于提供的堆栈信息进行深度代码级排错。\n\n请直接使用 Markdown 输出，按以下结构组织：\n- **错误定位** (报错所在的模块、具体函数或组件)\n- **根因分析** (解释为什么会报错，例如变量为空、路径不存在、类型不匹配等)\n- **修复建议** (给开发者的具体代码修改思路，或给用户清理缓存/修正环境的方案)""",
                "user_template": "{user_content}"
            },
            "game_log_analysis": {
                "name": "游戏日志分析",
                "description": "分析 RimWorld 游戏日志，帮助玩家解决 Mod 冲突和报错。",
                "system": """你是一个专门处理 Unity3D 和 RimWorld 游戏错误日志的诊断专家，擅长判断真正根因、区分连锁报错，并给出尽量可靠且节制的修复建议。\n如果涉及Mod冲突或排序错误，请明确指出所有涉及Mod。\n\n- **日志来源 (source_type)**: {source_type}\n- **日志文件名 (filename)**: {filename}\n请严格遵守以下诊断流程：\n1. 【重视聚类特征】首轮提供的 `error_table_of_contents` 是已经过压缩聚类的错误摘要。\n   - ⚠️注意：为了压缩，摘要中的十六进制地址和特定实例后缀被替换为了 `<HEX>`、`<NUM>`、`<ID>` 占位符，这是正常的。\n   - `target_line` 是该类错误的【唯一代表行号】。\n   - `repeat_count` 表示该错误在日志中重复出现的总次数（次数高可能是性能杀手，但不一定是引发崩溃的根因）。\n   - `stack_preview` 是提炼过的核心堆栈。如果这几行已经足够定位问题，**坚决不要再调工具查详情**。\n2. 【节制调用】如果你必须查阅详情，只需使用摘要中的 `target_line` 作为参数调用工具，绝对不要猜测或遍历其他行号！\n3. 【推断明确性】请明确区分“已确认的结论”和“高概率推断”，不要把猜测写成既定事实。\n\n{tools_description}\n\n请直接使用 Markdown 输出，尽量按以下结构组织：\n- **结论** (直接指出导致问题的具体模组或原因)\n- **关键证据** (简述判定依据，无需长篇大论复制日志)\n- **修复建议** (给玩家的具体操作指南)\n- **待验证项** (仅当证据不足时再写)\n\n如果你有非常明确且前端可以执行的操作建议，请**必须在回答的最末尾**使用 `<actions>` 标签包裹 JSON 数据。\n格式要求：严格遵循 JSON 格式，不要在 `<actions>` 内部写 Markdown 代码块标记 (```json)。\n可用动作如下：\n<actions>\n{{\n  "actions":[\n    {{ "type": "ENABLE_MOD", "title": "一键启用前置", "description": "...", "payload": {{ "mod_id": "需要启用的包名" }} }},\n    {{ "type": "ADD_RULE", "title": "修正排序规则", "description": "...", "payload": {{ "mod_id": "主体包名", "rule_type": "loadAfter", "target_id": "必须放在其后的包名" }} }},\n    {{ "type": "DISABLE_MOD", "title": "停用冲突模组", "description": "...", "payload": {{ "mod_ids": ["冲突的包名"] }} }}\n  ]\n}}\n</actions>\n只有在包名、目标对象和动作方向都非常明确时才输出 actions；否则只给文字建议。""",
                "user_template": "{user_content}"
            }
        }
    
    def _ensure_default_prompts(self):
        """如果配置文件不存在，生成默认的 Prompts"""
        if os.path.exists(self.prompt_file): return
        logger.info("Generating default prompts.json...")
        self._save_prompts_to_disk(self._get_default_prompts())

    def _save_prompts_to_disk(self, data):
        """将提示词写入磁盘"""
        try:
            with open(self.prompt_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save prompts: {e}")
    
    def reload_prompts(self):
        """重新加载提示词配置文件"""
        if not os.path.exists(self.prompt_file): return
        try:
            with open(self.prompt_file, 'r', encoding='utf-8') as f:
                self.prompts = json.load(f)
                need_save = False
                # 检查是否包含所有系统级提示词，缺失则补充
                for p_id, p_data in self._get_default_prompts().items():
                    if p_id not in self.prompts:
                        need_save = True
                        self.prompts[p_id] = p_data
                        logger.warning(f"Prompt {p_id} missing in prompts.json, added with default values.")
                if need_save:
                    self._save_prompts_to_disk(self.prompts)
                
        except Exception as e:
            logger.error(f"Failed to load prompts.json: {e}")
            # 加载默认提示词
            self._ensure_default_prompts()
    
    def save_prompt(self, prompt_id: str, prompt_data: dict):
        """新增或更新提示词"""
        # 如果是修改系统提示词，保留其 is_system 属性防止被篡改
        if prompt_id in self.prompts and self.prompts[prompt_id].get('is_system'):
            prompt_data['is_system'] = True
            
        self.prompts[prompt_id] = prompt_data
        self._save_prompts_to_disk(self.prompts)
        return self.prompts

    def delete_prompt(self, prompt_id: str):
        """删除提示词 (拒绝删除系统级)"""
        if prompt_id not in self.prompts:
            raise ValueError("Prompt ID 不存在")
        if self.prompts[prompt_id].get('is_system'):
            raise ValueError("无法删除系统级核心提示词")
            
        del self.prompts[prompt_id]
        self._save_prompts_to_disk(self.prompts)
        return self.prompts

    def reset_system_prompts(self):
        """恢复所有系统级提示词到出厂设置 (保留用户自定义的)"""
        defaults = self._get_default_prompts()
        for p_id, p_data in defaults.items():
            self.prompts[p_id] = p_data
        self._save_prompts_to_disk(self.prompts)
        return self.prompts


    # ---------------------------------------------------------
    # 定义 AI 可以调用的后置工具箱 (Tools)
    # ---------------------------------------------------------
    
    def ai_diagnostic_chat(self, payload: dict, active_context, reader=None) -> list[dict[str, Any]] | dict[str, Any] | list[Any]:
        """
        处理前端的诊断请求，支持 Agentic 工具调用和多轮会话
        payload: { "history": [...], "diagnosis_context": {...}, "question": "..." }
        """
        tool_executor = AIToolExecutor(active_context, payload, reader)
        # 获取前端生成的话话 ID，用于向前端定向推送流数据
        session_id = payload.get("session_id", str(uuid.uuid4()))
        source_type = payload.get("log_source_type", "game")
        # 根据日志来源，选择不同的提示词任务
        task_key = "app_log_analysis" if source_type == 'app' else "game_log_analysis"
        prompt_config = self.prompts.get(task_key)
        if not prompt_config:
            raise ValueError(f"Prompt template '{task_key}' not found.")
        # 构建一个包含所有可用信息的【统一变量上下文】
        # 这样任何提示词模板都可以按需调用这些变量
        variables = {
            "source_type": source_type,
            "filename": payload.get("filename", ""),
            "target_lang": get_lang_by_code(settings.config.language),
            "tools_description": "" # 默认为空
        }
        # 动态生成工具列表和描述，并注入变量上下文
        tools = None
        tool_choice = None
        if source_type == 'game': # 只有游戏日志才需要工具
            # 获取前端启用的工具列表
            enabled_tools_list = payload.get("enabled_tools", [])
            # 动态构建 Tools 列表
            all_tools = tool_executor.get_tool_schemas()
            # 如果过滤后没有任何工具（纯分析模式），必须将 tools 设为 None，否则 LiteLLM 会报错
            if not enabled_tools_list:
                tools_description = "【警告】当前你被禁止使用任何外部工具，你只能基于我提供的日志摘要直接进行分析！"
            else:
                tools = tool_executor.get_tool_schemas(enabled_tools_list)
                tool_choice = "auto"
                tools_description = "当前你可以使用以下工具进行深度调查：\n" + "\n".join(
                    [f"- {t['function']['name']}: {t['function']['description']}" for t in tools]
                )
            variables["tools_description"] = tools_description
            variables["all_tools"] = all_tools
            variables["tools"] = tools
        
        diagnosis_context = payload.get("diagnosis_context", None)
        question = payload.get("question", "")
        
        user_content_parts = [ f"当前日志来源: {variables['source_type']}", f"当前文件名: {variables['filename']}" ]
        
        if diagnosis_context:
            user_content_parts.append(f"以下是核心错误日志摘要：\n```json\n{json.dumps(diagnosis_context, ensure_ascii=False)}\n```")
        if question:
            user_content_parts.append(f"用户的补充提问：{question}")
        
        variables["user_content"] = "\n\n".join(user_content_parts)

        # 使用 _safe_format 格式化提示词，生成最终的 messages
        system_prompt = self._safe_format(prompt_config.get('system', ''), variables)
        user_prompt = self._safe_format(prompt_config.get('user_template', ''), variables)
        
        # 组装对话流
        messages = [{"role": "system", "content": system_prompt}]
        
        # 将前端历史直接映射（前端需保证 role 和 content 格式正确）
        # 如果 history 中有之前生成的 JSON，尽量转成纯文本保留上下文
        for msg in payload.get("history", []):
            if msg.get("role") in ["user", "assistant"]:
                # 如果历史消息是对象，尝试转为文本保留
                content = msg.get("content", "")
                if isinstance(content, dict):
                    content = json.dumps(content, ensure_ascii=False)
                messages.append({"role": msg["role"], "content": str(content)})

        # 附加到当前问题
        messages.append({"role": "user", "content": user_prompt})

        llm_kwargs = self._get_litellm_kwargs()
        model_name = llm_kwargs.get("model", settings.config.ai.model)

        # 记录整个会话的累计 Token 和诊断轮次，供前端与调试日志使用。
        token_usage = {
            "estimated_prompt_tokens": 0,
            "estimated_completion_tokens": 0,
            "estimated_total_tokens": 0,
            "tool_rounds": 0,
            "forced_final_round": False,
            "model": model_name
        }

        logger.debug(
            f"[AI诊断] 会话开始 session_id={session_id} "
            f"history={len(payload.get('history', []))} has_context={bool(diagnosis_context)} "
            f"context_items={len(diagnosis_context.get('error_table_of_contents', [])) if isinstance(diagnosis_context, dict) else 0}"
        )

        # 4. Agentic 循环 (ReAct)
        # 先允许模型进行若干轮“查证”，如果一直不收敛，再强制进入最终总结轮。
        max_loops = 10
        loop_count = 0
        # 记录已执行过的工具及其参数的哈希值
        executed_tool_signatures = set()
        
        while loop_count < max_loops:
            loop_count += 1
            try:
                prompt_tokens_this_round = self._estimate_messages_tokens(messages, model_name)
                token_usage["estimated_prompt_tokens"] += prompt_tokens_this_round
                token_usage["estimated_total_tokens"] += prompt_tokens_this_round
                logger.debug(
                    f"[AI诊断] 进入工具轮 session_id={session_id} loop={loop_count}/{max_loops} "
                    f"messages={len(messages)} prompt_tokens≈{prompt_tokens_this_round}"
                )
                stream_result = self._run_diagnostic_completion_with_fallback(
                    messages=messages,
                    llm_kwargs=llm_kwargs,
                    session_id=session_id,
                    tools=tools,
                    tool_choice="auto"
                )
                completion_payload = (
                    json.dumps(stream_result["tool_calls"], ensure_ascii=False)
                    if stream_result["is_tool_call"] else stream_result["final_text"]
                )
                output_tk = self._estimate_text_tokens(completion_payload, model_name)
                token_usage["estimated_completion_tokens"] += output_tk
                token_usage["estimated_total_tokens"] += output_tk
                # 如果模型决定调用工具
                if stream_result["is_tool_call"]:
                    token_usage["tool_rounds"] += 1
                    formatted_tool_calls = stream_result["tool_calls"]
                    messages.append({"role": "assistant", "content": "", "tool_calls": formatted_tool_calls})

                    logger.debug(
                        f"[AI诊断] 触发工具轮 session_id={session_id} loop={loop_count} "
                        f"tool_count={len(formatted_tool_calls)}"
                    )

                    # 逐个执行工具，并向前端推送状态
                    for tc in formatted_tool_calls:
                        func_name = tc["function"]["name"]
                        func_args = tc["function"]["arguments"]
                        tool_start_at = time.perf_counter()
                        # 通知前端：开始调用工具
                        EventBus.emit('ai-tool-call', { 'session_id': session_id, 'tool_id': tc["id"], 'name': func_name, 'arguments': func_args})
                        # 防死锁检测
                        call_signature = f"{func_name}|{func_args}"
                        if call_signature in executed_tool_signatures:
                            # 强制拦截并返回系统警告给 AI
                            tool_result = json.dumps({
                                "error": "系统警告：你已经使用完全相同的参数调用过该工具！请停止重复调用，立即基于已有证据进行分析和总结！"
                            }, ensure_ascii=False)
                            logger.warning(f"[AI防死锁] 拦截重复调用: {call_signature}")
                        else:
                            executed_tool_signatures.add(call_signature)
                            # 正常执行工具
                            tool_result = tool_executor.execute(func_name, func_args)
                        
                        duration_ms = int((time.perf_counter() - tool_start_at) * 1000)

                        tool_ok = True
                        try:
                            parsed_tool_result = json.loads(tool_result)
                            if isinstance(parsed_tool_result, dict) and parsed_tool_result.get("error"):
                                tool_ok = False
                        except Exception:
                            parsed_tool_result = None

                        logger.debug(
                            f"[AI诊断] 工具完成 session_id={session_id} tool={func_name} "
                            f"ok={tool_ok} duration_ms={duration_ms} result_chars={len(tool_result or '')}"
                        )

                        # 通知前端：工具执行完毕
                        EventBus.emit('ai-tool-result', {
                            'session_id': session_id,
                            'tool_id': tc["id"],
                            'status': 'done' if tool_ok else 'error',
                            'duration_ms': duration_ms,
                            'summary': self._summarize_tool_result(func_name, tool_result),
                            'result': tool_result
                        })

                        messages.append({
                            "role": "tool", "tool_call_id": tc["id"], "name": func_name, "content": tool_result
                        })

                    continue

                # 如果没有工具调用，说明大模型完成了分析并输出了最后的内容
                final_response = self._parse_diagnostic_final_text(stream_result["final_text"], stream_result.get("reasoning_text", ""))
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

            except Exception as e:
                logger.error(f"AI Diagnostic Error: {str(e)}", exc_info=True)
                token_usage["estimated_total_tokens"] = (
                    token_usage["estimated_prompt_tokens"] + token_usage["estimated_completion_tokens"]
                )
                
                # 【关键改造】生成可展开的 Markdown 错误提示，前端自带解析器会完美渲染
                import traceback
                error_trace = traceback.format_exc()
                error_markdown = (
                    "⚠️ **AI 推理链路在本轮处理中发生严重中断。**\n\n"
                    "这通常是因为 API 中转站超时、模型不支持流式工具调用，或者网络连接被强制断开。\n\n"
                    "<details><summary>点击展开错误详情</summary>\n\n"
                    f"```text\n{str(e)}\n\n{error_trace}\n```\n"
                    "</details>"
                )
                
                return {
                    "analysis": error_markdown,
                    "actions": [],
                    "token_usage": token_usage
                }

        # 【关键改进】如果模型长时间沉迷工具调用，不再直接给“无法得出结论”，
        # 而是进入一次强制总结轮，禁止继续调工具，只基于已有证据收敛输出。
        logger.warning(f"[AI诊断] 工具轮达到上限，转入强制总结 session_id={session_id}")
        token_usage["forced_final_round"] = True
        forced_messages = messages + [{
            "role": "system",
            "content": (
                "你已经完成资料查阅。禁止继续调用任何工具。"
                "请直接基于当前证据给出最终诊断；如果证据仍不足，也要明确给出最可能的 1-3 个原因、"
                "证据依据，以及下一步建议用户如何验证。"
            )
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
                tools=tools,               # <-- 使用过滤后的 tools
                tool_choice=tool_choice    # <-- 动态 tool_choice
            )
            token_usage["estimated_completion_tokens"] += self._estimate_text_tokens(stream_result["final_text"], model_name)
            token_usage["estimated_total_tokens"] = (
                token_usage["estimated_prompt_tokens"] + token_usage["estimated_completion_tokens"]
            )

            final_response = self._parse_diagnostic_final_text(stream_result["final_text"], stream_result.get("reasoning_text", ""))
            if not final_response.get("analysis"):
                final_response["analysis"] = "AI 已完成查证，但没有生成有效总结文本。建议查看上方工具步骤详情，优先核对关键上下文和模组排序。"
            final_response["token_usage"] = token_usage

            logger.debug(
                f"[AI诊断] 强制总结完成 session_id={session_id} "
                f"analysis_chars={len(final_response.get('analysis', ''))} "
                f"total_tokens≈{token_usage['estimated_total_tokens']}"
            )
            return final_response
        except Exception as e:
            logger.error(f"AI Diagnostic Error: {str(e)}", exc_info=True)
            token_usage["estimated_total_tokens"] = (
                token_usage["estimated_prompt_tokens"] + token_usage["estimated_completion_tokens"]
            )
            
            # 【关键改造】生成可展开的 Markdown 错误提示，前端自带解析器会完美渲染
            import traceback
            error_trace = traceback.format_exc()
            error_markdown = (
                "⚠️ **AI 推理链路在本轮处理中发生严重中断。**\n\n"
                "这通常是因为 API 中转站超时、模型不支持流式工具调用，或者网络连接被强制断开。\n\n"
                "<details><summary>点击展开查看技术报错详情</summary>\n\n"
                f"```text\n{str(e)}\n\n{error_trace}\n```\n"
                "</details>"
            )
            
            return {
                "analysis": error_markdown,
                "actions": [],
                "token_usage": token_usage
            }

    
    
    
