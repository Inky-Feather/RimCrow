# backend/managers/mgr_ai.py
import json
import os
import re
import time
import asyncio
from typing import List, Dict, Any
from dataclasses import asdict

# 引入 LiteLLM 的异步和同步方法
import litellm
from litellm import completion, acompletion
from litellm.exceptions import RateLimitError, ServiceUnavailableError
import requests
from json_repair import repair_json

from backend.settings import settings
from backend.utils.logger import logger
from backend.utils.constants import get_lang_by_code
from backend.utils.event_bus import EventBus

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
        self.prompt_file = os.path.join(os.getcwd(), 'data', 'prompts.json')
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
                {"value": "openai_compatible", "label": "OpenAI 兼容协议 (vLLM/中转/LM Studio)"},
                {"value": "ollama", "label": "Ollama 本地协议"},
                {"value": "gemini_compatible", "label": "Google Gemini 兼容协议 (中转/代理)"}
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
            return litellm.models_by_provider.get(provider, [])
            
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
                return cached_models
                
        # 缓存未命中，发起请求
        models = self._fetch_custom_models(provider, base_url, api_key)
        
        # 写入缓存
        if models: # 只有获取成功才缓存，防止缓存错误的空结果
            self._model_cache[cache_key] = (time.time(), models)
            
        return models

    def _fetch_custom_models(self, provider: str, base_url: str, api_key: str) -> List[str]:
        """(内部方法) 发送网络请求探测代理/本地服务的模型列表"""
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        try:
            # Ollama 格式探测
            if provider == 'ollama':
                resp = requests.get(f"{base_url}/api/tags", timeout=10)
                if resp.status_code == 200:
                    return [m['name'] for m in resp.json().get('models', [])]
            elif provider == 'gemini_compatible':
                # Gemini 协议通常在 URL 中带 key，或者从 Header 取
                resp = requests.get(f"{base_url}/v1/models", params={"key": api_key}, timeout=10)
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
                        resp = requests.get(f"{base_url}{endpoint}", headers=headers, timeout=10)
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
            "stream": False,    # 显式禁用流式传输
            # 伪装成正常的 Chrome 浏览器，穿透绝大多数中转站的 Cloudflare 盾
            "extra_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json",
            }
        }

        # 2. 路由分支
        if cfg.api_type == 'official':
            # 官方原生模式
            # 如果模型名称未自带提供商前缀（如 gpt-4o 没有 openai/ 前缀），LiteLLM 也能自动识别，但为了极致安全，我们显式传入 custom_llm_provider
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
            elif cfg.provider == 'gemini_compatible':
                # 强制使用 gemini/ 前缀路由，LiteLLM 将采用 Google 协议格式
                kwargs["model"] = f"gemini/{cfg.model}"
            else:
                # openai_compatible 
                # 这里加上 openai/ 前缀是 LiteLLM 的终极奥义，它会强制按 OpenAI 官方数据结构请求你的目标 base_url
                kwargs["model"] = f"openai/{cfg.model}"

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

    def _safe_format(self, template: str, variables: dict) -> str:
        """
        安全格式化工具：只替换模板中存在的变量，忽略其他大括号。
        解决 JSON 示例与 Python .format() 的冲突。
        """
        import re
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
            # 这里必须把 chunk 自身也传给 zip，因为我们需要知道发出去的是谁
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
        
        # 返回你指定的结构化数据
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
            "log_analysis": {
                "name": "日志分析",
                "description": "分析游戏日志中的错误、红字和堆栈信息",
                "system": "你是一个Unity3D和RimWorld模组开发专家。你的任务是分析用户的游戏日志片段。\n请找出导致错误、崩溃或红字的具体Mod名称、XML Def或缺失文件。\n如果涉及Mod冲突，请明确指出冲突双方。\n请使用{target_lang}回答，并保持专业且易懂。",
                "user_template": "请分析以下日志片段，并给出修复建议：\n\n{log_content}"
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
            }
        }
    
    def _ensure_default_prompts(self):
        """如果配置文件不存在，生成默认的 Prompts"""
        if os.path.exists(self.prompt_file):
            return
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
        if os.path.exists(self.prompt_file):
            try:
                with open(self.prompt_file, 'r', encoding='utf-8') as f:
                    self.prompts = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load prompts.json: {e}")
                # 加载默认
                self.prompts = {}
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
