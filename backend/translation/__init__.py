"""通用翻译能力。

这里不绑定工坊、本地 Mod 或其它业务存储；调用方只需要把内容整理成
TranslationDocument，再把结果保存到自己的数据结构里。
"""

from backend.translation.service import DEFAULT_TRANSLATION_PROVIDER, TranslationManager

__all__ = ["DEFAULT_TRANSLATION_PROVIDER", "TranslationManager"]
