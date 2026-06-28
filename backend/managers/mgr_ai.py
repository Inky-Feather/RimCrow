# backend/managers/mgr_ai.py
import json
import os
import requests
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import asdict

from backend.settings import settings
from backend.utils.logger import logger
from backend.utils.constants import get_lang_by_code


# =========================================================================
#  1. 抽象基类 (Provider Interface)
# =========================================================================

class LLMProvider(ABC):
    """
    LLM 提供商抽象基类。
    任何新的 AI 接口（如 Mistral, Ollama）只需继承此类并实现方法即可。
    """
    def __init__(self, config):
        self.config = config
        self.session = requests.Session()
        self.timeout = 60 # 增加超时时间，日志分析可能很慢

    @abstractmethod
    def chat(self, system_prompt: str, user_content: str) -> str:
        """发送对话请求并返回文本结果"""
        pass

    @abstractmethod
    def list_models(self) -> List[str]:
        """获取可用模型列表"""
        pass

    def _handle_error(self, response: requests.Response):
        """通用错误处理"""
        try:
            data = response.json()
            # 尝试提取各种常见错误格式
            error_msg = (
                data.get('error', {}).get('message') or 
                data.get('error') or 
                data.get('message') or 
                response.text
            )
        except:
            error_msg = response.text
        logger.error(f"AI Request Failed [{response.status_code}]: {error_msg}")
        raise Exception(f"API Error ({response.status_code}): {error_msg}")

# =========================================================================
#  2. 具体实现类 (Concrete Providers)
# =========================================================================

class OpenAIProvider(LLMProvider):
    """
    OpenAI 协议兼容提供商 (ChatGPT, DeepSeek, Moonshot, LocalAI 等)
    """
    def chat(self, system_prompt: str, user_content: str) -> str:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens
        }

        try:
            resp = self.session.post(url, json=payload, headers=headers, timeout=self.timeout)
            if resp.status_code != 200:
                self._handle_error(resp)
            
            data = resp.json()
            return data['choices'][0]['message']['content']
        except Exception as e:
            logger.error(f"OpenAI Chat Error: {e}")
            raise e

    def list_models(self) -> List[str]:
        # 兼容性处理：有些自定义端点可能没有 /models 接口
        url = f"{self.config.base_url.rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        
        try:
            resp = self.session.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                self._handle_error(resp)
            
            data = resp.json()
            # 标准 OpenAI 格式返回 { data: [ {id: "gpt-4"}, ... ] }
            return [item['id'] for item in data.get('data', [])]
        except Exception as e:
            logger.warning(f"Failed to fetch models: {e}")
            # 失败时返回当前配置的模型作为保底
            return [self.config.model]

class AnthropicProvider(LLMProvider):
    """
    Anthropic (Claude) 提供商
    """
    def chat(self, system_prompt: str, user_content: str) -> str:
        url = f"{self.config.base_url.rstrip('/')}/messages"
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": self.config.model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_content}],
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature
        }

        try:
            resp = self.session.post(url, json=payload, headers=headers, timeout=self.timeout)
            if resp.status_code != 200:
                self._handle_error(resp)
            
            data = resp.json()
            return data['content'][0]['text']
        except Exception as e:
            logger.error(f"Claude Chat Error: {e}")
            raise e

    def list_models(self) -> List[str]:
        # Claude 官方 API 暂无公开的 list_models 接口，通常需要硬编码或手动输入
        return [
            "claude-3-opus",
            "claude-3-sonnet",
            "claude-3-haiku"
        ]

class GoogleProvider(LLMProvider):
    """
    Google Gemini 提供商
    注意：Google API 鉴权通常在 URL 参数中
    BaseURL 示例: https://generativelanguage.googleapis.com/v1beta
    """
    def chat(self, system_prompt: str, user_content: str) -> str:
        # Gemini Pro 不直接支持 System Prompt 字段 (新版支持，但为了兼容旧版，这里将 System 拼接到 User)
        # 格式: POST /models/{model}:generateContent?key={api_key}
        url = f"{self.config.base_url.rstrip('/')}/models/{self.config.model}:generateContent"
        params = {"key": self.config.api_key}
        headers = {"Content-Type": "application/json"}
        
        full_content = f"System Context: {system_prompt}\n\nTask: {user_content}"
        
        payload = {
            "contents": [{"parts": [{"text": full_content}]}],
            "generationConfig": {
                "temperature": self.config.temperature,
                "maxOutputTokens": self.config.max_tokens
            }
        }

        try:
            resp = self.session.post(url, params=params, json=payload, headers=headers, timeout=self.timeout)
            if resp.status_code != 200:
                self._handle_error(resp)
            data = resp.json()
            # 解析 Gemini 响应结构
            try:
                return data['candidates'][0]['content']['parts'][0]['text']
            except (KeyError, IndexError):
                raise Exception(f"Unexpected response format: {data}")
        except Exception as e:
            logger.error(f"Gemini Chat Error: {e}")
            raise e

    def list_models(self) -> List[str]:
        url = f"{self.config.base_url.rstrip('/')}/models"
        params = {"key": self.config.api_key}
        try:
            resp = self.session.get(url, params=params, timeout=10)
            if resp.status_code != 200: self._handle_error(resp)
            data = resp.json()
            # Google 返回 name 如 "models/gemini-pro"去掉前缀
            models = []
            for m in data.get('models', []):
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    models.append(m['name'].replace('models/', ''))
            return models
        except Exception as e:
            logger.warning(f"Failed to fetch models: {e}")
            return ["gemini-pro", "gemini-1.5-pro-latest"]

# =========================================================================
#  3. 业务管理器 (Manager)
# =========================================================================

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
        
        # 加载提示词库
        self.prompts = {}
        self.prompt_file = os.path.join(os.getcwd(), 'data', 'prompts.json')
        
        # 1. 确保目录存在
        os.makedirs(os.path.dirname(self.prompt_file), exist_ok=True)
        
        # 2. 检查并生成默认配置
        self._ensure_default_prompts()
        
        # 3. 加载
        self.reload_prompts()
        
        logger.info("AI Manager initialized.")

    def _ensure_default_prompts(self):
        """如果配置文件不存在，生成默认的 Prompts"""
        if os.path.exists(self.prompt_file):
            return

        logger.info("Generating default prompts.json...")
        
        default_data = {
            "chat": {
                "name": "自由对话 (Chat)",
                "description": "普通的对话模式",
                "system": "你是一个乐于助人的RimWorld游戏专家，你的回答应该总是使用{target_lang}。",
                "user_template": "{message}"
            },
            "log_analysis": {
                "name": "日志分析 (Log Analysis)",
                "description": "分析游戏日志中的错误、红字和堆栈信息",
                "system": "你是一个Unity3D和RimWorld模组开发专家。你的任务是分析用户的游戏日志片段。\n请找出导致错误、崩溃或红字的具体Mod名称、XML Def或缺失文件。\n如果涉及Mod冲突，请明确指出冲突双方。\n请使用{target_lang}回答，并保持专业且易懂。",
                "user_template": "请分析以下日志片段，并给出修复建议：\n\n{log_content}"
            },
            "mod_info_translation": {
                "name": "模组信息翻译 (Translation)",
                "description": "翻译Mod的名称和简介",
                "system": "你是一个专业的RimWorld模组本地化专家。你的任务是将Mod的名称和描述翻译为{target_lang}。\n请保留所有XML标签（如 <color=#xxx>）、特殊占位符和Markdown格式。\n请以JSON格式返回结果，包含两个字段：'name' (译名) 和 'description' (翻译后的描述)。不要包含Markdown代码块标记(```json)。",
                "user_template": "Original Name: {name}\nOriginal Description:\n{description}"
            },
            "alias_generation": {
                "name": "智能别名与通俗备注 (Colloquial Alias)",
                "description": "生成新手也能瞬间秒懂的俗名和生活化备注",
                "system": "你是一个深耕 RimWorld 社区多年的老玩家，也是一位极具亲和力的模组讲解员。你的任务是把复杂的模组信息翻译成**连完全不懂电脑的新手玩家**都能瞬间听懂的话。\n\n**1. 别名 (alias_name) 准则：**\n- 必须原样保留名称中的元数据（如果有），如 `[作者名]`、`(版本如：Continued)` 等，严禁改动这些括号内容。\n- 核心名称要像玩家在群里聊天一样自然，直接称呼功能或物品，表述模糊的可以用“XX补丁”、“XX扩展”、“XX增强”等直观词汇。\n\n**2. 备注 (notes) 准则 (核心修改)：**\n- **禁止使用专业术语**：严禁出现“注入”、“XML”、“Def”、“程序集”、“算法”等词汇。如果一定要解释技术，请用生活中的例子打比方（比如：它像胶水一样把两个原本不合的模组粘在一起）。\n- **功能导向**：直接告诉玩家“装了这个之后，你的游戏里会多出什么”或者“它帮你解决了哪个让你头疼的问题”。\n- **语言风格**：通俗易懂，极致白话。字数控制在 100-200 字之间。 **排版建议**：用客观但亲切的语气描述，不要像说明书，要像老大哥带新手。\n\n请以 JSON 格式返回结果，包含两个字段：'alias_name' (别名) 和 'notes' (备注)。不要包含 Markdown 代码块标签。",
                "user_template": "模组原名: {name}\n模组简介:\n{description}"
            }
        }
        
        try:
            with open(self.prompt_file, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to create default prompts: {e}")

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

    def get_provider(self, override_config: dict = None) -> LLMProvider: # type: ignore
        """
        工厂方法：根据配置实例化对应的 Provider
        :param override_config: 临时覆盖的配置 (用于测试连接)
        """
        from backend.settings import AIConfig
        
        # 1. 准备配置对象，如果是字典（从 JSON 直接加载的情况），则转换为 AIConfig 对象
        raw_cfg = settings.config.ai
        if isinstance(raw_cfg, dict):
            cfg = AIConfig(**raw_cfg)
        else:
            cfg = raw_cfg
        if override_config:
            # 创建一个临时配置对象，不修改全局设置
            # 用 Object 模拟 dataclass 或者创建新实例
            # 浅拷贝当前配置并更新
            current_dict = asdict(cfg)
            current_dict.update(override_config)
            cfg = AIConfig(**current_dict)

        # 2. 选择 Provider
        ptype = cfg.provider.lower()
        if ptype == "openai": return OpenAIProvider(cfg)
        elif ptype == "anthropic": return AnthropicProvider(cfg)
        elif ptype == "google": return GoogleProvider(cfg)
        else: raise ValueError(f"Unsupported provider: {ptype}")

    def execute_task(self, task_key: str, variables: Dict[str, Any]) -> str:
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
            current_lang_code = settings.config.language
            # 转换为自然语言 (如 'Simplified Chinese')
            variables['target_lang'] = get_lang_by_code(current_lang_code)

        prompt_config = self.prompts[task_key]
        system_tmpl = prompt_config.get('system', '')
        user_tmpl = prompt_config.get('user_template', '')
        
        # 2. 格式化 System Prompt (注入语言设置)
        # 使用 safe format 避免因为模板里有 {} 但变量里没有而报错？
        # 这里直接 format，假设 prompts.json 的占位符都是可控的
        try:
            # 允许 system prompt 使用变量 (主要是 target_lang)
            system_prompt = system_tmpl.format(**variables)
            # 允许 user prompt 使用变量 (content, name, description 等)
            user_content = user_tmpl.format(**variables)
        except KeyError as e:
            raise ValueError(f"Missing variable for template: {e}")

        # 3. 执行
        provider = self.get_provider()
        return provider.chat(system_prompt, user_content)

    def fetch_available_models(self, config_dict: dict) -> List[str]:
        '''获取可用模型列表'''
        provider = self.get_provider(override_config=config_dict)
        return provider.list_models()
    