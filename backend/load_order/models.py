from dataclasses import dataclass, field


# 这些常量既用于后端内部判断，也会透传给前端显示来源类型。
FORMAT_MODSCONFIG = "modsconfig"
FORMAT_MODLIST = "modlist"
FORMAT_RML = "rml"
FORMAT_SAVEGAME = "savegame"
FORMAT_RIMSORT_JSON = "rimsort_json"
FORMAT_RIMPY_XML = "rimpy_xml"
FORMAT_PLAIN_TEXT = "plain_text"
FORMAT_WORKSHOP_IDS = "workshop_ids"
FORMAT_RIMCROW_JSON = "rimcrow_json"
FORMAT_SHARE_CODE = "share_code"


@dataclass(slots=True)
class ParsedLoadOrderData:
    """
    统一的解析结果。

    设计目标是把“各种输入格式”都压成同一个中间结构，
    这样 manager 层只需要关心“拿到了哪些 package_id / 名称 / 工坊 ID”，
    不必知道原始文件是 XML、JSON 还是纯文本。
    """

    format: str
    list_name: str
    package_ids: list[str] = field(default_factory=list)
    package_tokens: list[str] = field(default_factory=list)
    mod_names: list[str] = field(default_factory=list)
    workshop_ids: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
