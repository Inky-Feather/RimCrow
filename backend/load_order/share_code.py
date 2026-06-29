import base64
import json
import zlib

from backend.utils.tools import normalize_package_id, normalize_workshop_id
from .models import FORMAT_SHARE_CODE, ParsedLoadOrderData


SHARE_CODE_PREFIX = "RC-"
LEGACY_SHARE_CODE_PREFIX = "RMM1-"


def _encode_mod_entry(package_id: str, workshop_id: str = "", name: str = ""):
    normalized_package_id = normalize_package_id(package_id)
    if not normalized_package_id: return None

    normalized_workshop_id = normalize_workshop_id(workshop_id)
    clean_name = str(name or "").strip()

    # 最短情况只写包名；有额外元数据时再逐步展开为数组。
    if not normalized_workshop_id and not clean_name:
        return normalized_package_id
    if not clean_name:
        return [normalized_package_id, normalized_workshop_id]
    return [normalized_package_id, normalized_workshop_id, clean_name]


def _decode_mod_entry(item) -> tuple[str, str, str]:
    if isinstance(item, str):
        return normalize_package_id(item), "", ""

    if not isinstance(item, list) or not item:
        raise ValueError("分享码里的模组条目格式无效")

    package_id = normalize_package_id(item[0] if len(item) > 0 else "")
    workshop_id = normalize_workshop_id(item[1] if len(item) > 1 else "")
    name = str(item[2] if len(item) > 2 else "").strip()
    return package_id, workshop_id, name


def _urlsafe_b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _urlsafe_b64decode(text: str) -> bytes:
    clean_text = str(text or "").strip()
    padding = "=" * ((4 - len(clean_text) % 4) % 4)
    return base64.urlsafe_b64decode(clean_text + padding)


def _compress_payload(payload: list) -> bytes:
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return zlib.compress(payload_json, level=9)


def _decompress_payload(raw: bytes):
    payload_json = zlib.decompress(raw).decode("utf-8")
    return json.loads(payload_json)


def _checksum_hex(raw: bytes) -> str:
    return f"{zlib.crc32(raw) & 0xFFFFFFFF:08X}"


def build_share_code(
    package_ids: list[str],
    mod_names: list[str] | None = None,
    workshop_ids: list[str] | None = None,
    list_name: str = "",
    game_version: str = "",
) -> str:
    mod_names = mod_names or []
    workshop_ids = workshop_ids or []
    mod_entries: list = []

    for index, package_id in enumerate(package_ids or []):
        encoded_item = _encode_mod_entry(
            package_id=package_id,
            workshop_id=workshop_ids[index] if index < len(workshop_ids) else "",
            name=mod_names[index] if index < len(mod_names) else "",
        )
        if encoded_item is not None:
            mod_entries.append(encoded_item)

    if not mod_entries:
        raise ValueError("当前没有可生成分享码的模组条目")

    # v1 payload 采用位置固定的数组，压缩率和解码稳定性都比冗长 key 更好。
    payload = [
        1,
        str(list_name or "").strip(),
        str(game_version or "").strip(),
        mod_entries,
    ]
    compressed = _compress_payload(payload)
    checksum = _checksum_hex(compressed)
    return f"{SHARE_CODE_PREFIX}{checksum}-{_urlsafe_b64encode(compressed)}"


def _split_share_code(share_code: str) -> tuple[str, str, str]:
    normalized_code = "".join(str(share_code or "").split())
    if normalized_code.lower().startswith("share://"):
        normalized_code = normalized_code[8:].replace("/", "-", 1)

    if normalized_code.startswith(SHARE_CODE_PREFIX):
        checksum, separator, payload_text = normalized_code[len(SHARE_CODE_PREFIX):].partition("-")
        return SHARE_CODE_PREFIX, checksum, payload_text if separator else ""

    if normalized_code.startswith(LEGACY_SHARE_CODE_PREFIX):
        checksum, separator, payload_text = normalized_code[len(LEGACY_SHARE_CODE_PREFIX):].partition("-")
        return LEGACY_SHARE_CODE_PREFIX, checksum, payload_text if separator else ""

    raise ValueError("分享码前缀无效，当前支持 RC- 或旧版 RMM1 分享码")


def parse_share_code(share_code: str) -> ParsedLoadOrderData:
    _, checksum, payload_text = _split_share_code(share_code)
    if not checksum or not payload_text:
        raise ValueError("分享码结构无效")

    compressed = _urlsafe_b64decode(payload_text)
    if _checksum_hex(compressed) != checksum.upper():
        raise ValueError("分享码校验失败，可能已损坏或复制不完整")

    payload = _decompress_payload(compressed)
    if not isinstance(payload, list) or len(payload) < 4:
        raise ValueError("分享码载荷无效")

    payload_version = payload[0]
    if payload_version != 1:
        raise ValueError(f"不支持的分享码版本: {payload_version}")

    list_name = str(payload[1] or "").strip() or "Shared Load Order"
    mod_items = payload[3]
    if not isinstance(mod_items, list):
        raise ValueError("分享码模组列表无效")

    package_ids: list[str] = []
    mod_names: list[str] = []
    workshop_ids: list[str] = []
    seen_package_ids: set[str] = set()

    for item in mod_items:
        package_id, workshop_id, name = _decode_mod_entry(item)
        if not package_id or package_id in seen_package_ids:
            continue
        seen_package_ids.add(package_id)
        package_ids.append(package_id)
        mod_names.append(name)
        workshop_ids.append(workshop_id)

    if not package_ids:
        raise ValueError("分享码中没有可用的模组条目")

    return ParsedLoadOrderData(
        format=FORMAT_SHARE_CODE,
        list_name=list_name,
        package_ids=package_ids,
        mod_names=mod_names,
        workshop_ids=workshop_ids,
    )


def describe_share_code(share_code: str) -> str:
    try:
        prefix, checksum, _ = _split_share_code(share_code)
    except ValueError:
        return "share://invalid"
    if not checksum: return "share://invalid"
    return f"share://{prefix.rstrip('-')}/{checksum.upper()}"
