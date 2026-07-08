from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pathspec


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCALE_PATH = ROOT / "frontend" / "src" / "locales" / "zh-CN.json"
BUILTIN_LOCALES_DIR = ROOT / "frontend" / "src" / "locales"
BUILTIN_COMMANDS_PATH = ROOT / "frontend" / "src" / "app" / "commands" / "builtinCommands.js"
GUIDE_STORE_PATH = ROOT / "frontend" / "src" / "features" / "guide" / "guideStore.js"
GUIDE_CONFIG_PATH = ROOT / "frontend" / "src" / "features" / "guide" / "guideConfig.js"
AI_ACTION_DEFINITIONS_PATH = ROOT / "backend" / "ai" / "def_actions.py"
AI_ENTRY_DEFINITIONS_PATH = ROOT / "backend" / "ai" / "def_entries.py"
AI_ATTACHMENT_DEFINITIONS_PATH = ROOT / "backend" / "ai" / "def_attachments.py"
AI_TOOL_DEFINITIONS_PATH = ROOT / "backend" / "ai" / "ai_tools.py"
SCAN_ROOTS = (
    ROOT / "backend",
    ROOT / "frontend" / "src",
)
JS_CALL_PATTERN = re.compile(
    r"(?<![\w$])t\s*\(\s*"
    r"(?P<key>['\"`])(?P<key_text>(?:\\.|(?!\1).)*?)\1\s*,\s*"
    r"(?P<default>['\"`])(?P<default_text>(?:\\.|(?!\3).)*?)\3",
    re.DOTALL,
)
BUILTIN_COMMAND_CATEGORY_PATTERN = re.compile(
    r"(?P<name>\w+):\s*\{\s*key:\s*(?P<key>['\"`])(?P<key_text>(?:\\.|(?!(?P=key)).)*?)(?P=key)\s*,\s*"
    r"defaultText:\s*(?P<default>['\"`])(?P<default_text>(?:\\.|(?!(?P=default)).)*?)(?P=default)\s*\}",
    re.DOTALL,
)
BUILTIN_COMMAND_TEXT_PATTERN = re.compile(
    r"id:\s*(?P<id>['\"`])(?P<id_text>(?:\\.|(?!(?P=id)).)*?)(?P=id)\s*,\s*"
    r"title:\s*(?P<title>['\"`])(?P<title_text>(?:\\.|(?!(?P=title)).)*?)(?P=title)\s*,\s*"
    r"category:\s*COMMAND_CATEGORIES\.(?P<category>\w+)\s*,\s*"
    r"description:\s*(?P<description>['\"`])(?P<description_text>(?:\\.|(?!(?P=description)).)*?)(?P=description)",
    re.DOTALL,
)
GUIDE_ENTRY_TEXT_PATTERN = re.compile(
    r"key:\s*(?P<key>['\"`])(?P<key_text>(?:\\.|(?!(?P=key)).)*?)(?P=key)\s*,\s*"
    r"title:\s*(?P<title>['\"`])(?P<title_text>(?:\\.|(?!(?P=title)).)*?)(?P=title)\s*,\s*"
    r"description:\s*(?P<description>['\"`])(?P<description_text>(?:\\.|(?!(?P=description)).)*?)(?P=description)",
    re.DOTALL,
)
GUIDE_STEPS_EXPORT_PATTERN = re.compile(
    r"export\s+const\s+(?P<name>\w+GuideSteps)\s*=\s*\[(?P<body>.*?)\n\];",
    re.DOTALL,
)
GUIDE_STEP_POPOVER_PATTERN = re.compile(
    r"popover:\s*\{.*?"
    r"title:\s*(?P<title>['\"`])(?P<title_text>(?:\\.|(?!(?P=title)).)*?)(?P=title)\s*,\s*"
    r"description:\s*(?P<description>['\"`])(?P<description_text>(?:\\.|(?!(?P=description)).)*?)(?P=description)",
    re.DOTALL,
)
COMMAND_ID_CAMEL_PATTERN = re.compile(r"([a-z0-9])([A-Z])")
PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z_][\w.-]*)\}")
LOCALE_MARKER_PATTERN = re.compile(r"(\[\[|\]\]|\^\^|!!|__|··)")
CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]")
I18N_CALL_LINE_PATTERN = re.compile(r"\b(?:t|tr|_tr|_plain_text|_html_text)\s*\(")
UNTRANSLATED_PREFIX = "[UNTRANSLATED] "
BARE_CHINESE_EXCLUDED_PARTS = {
    "frontend/src/locales/",
    "frontend/src/dev/",
    "backend/ai/ai_tools.py",
    "backend/ai/assistant_runtime.py",
    "backend/ai/def_output_contracts.py",
    "backend/ai/def_actions.py",
    "backend/ai/def_attachments.py",
    "backend/ai/def_entries.py",
}
BARE_CHINESE_EXCLUDED_FILES = {
    "backend/_version.py",
    "frontend/src/app/commands/builtinCommands.js",
    "frontend/src/features/guide/guideConfig.js",
    "frontend/src/features/guide/guideStore.js",
}
BARE_CHINESE_EXCLUDED_LINE_PREFIXES = (
    "#",
    "//",
    "/*",
    "*",
    "<!--",
)
BARE_CHINESE_LOG_MARKERS = (
    "logger.",
    "logging.",
    "console.",
    "print(",
    "_log_startup_perf(",
)
BARE_CHINESE_CONTEXT_SKIP_MARKERS = (
    "logger.",
    "ApiResponse.error(",
    "ApiResponse.warning(",
    "_log_startup_perf(",
    "mark_launch_failed(",
    "logStartupCheck(",
    "logMaintenanceCheck(",
)


def load_gitignore_spec() -> pathspec.PathSpec:
    patterns: list[str] = []
    gitignore = ROOT / ".gitignore"
    if gitignore.exists():
        patterns.extend(gitignore.read_text(encoding="utf-8").splitlines())
    # .gitignore 未必覆盖所有生成目录；这里补充只和扫描性能有关的硬排除。
    patterns.extend([
        ".git/",
        ".codegraph/",
        ".gitnexus/",
        ".venv/",
        "frontend/node_modules/",
        "frontend/dist/",
        "dist/",
        "build/",
        "data/",
        "cache/",
    ])
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def is_ignored(path: Path, spec: pathspec.PathSpec) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    return spec.match_file(rel)


def iter_source_files() -> Iterable[Path]:
    spec = load_gitignore_spec()
    for scan_root in SCAN_ROOTS:
        if not scan_root.exists():
            continue
        for path in scan_root.rglob("*"):
            if path.is_dir() or is_ignored(path, spec):
                continue
            if path.suffix in {".py", ".js", ".vue"}:
                yield path


def decode_js_string(raw: str, quote: str) -> str:
    if quote == "`" and "${" in raw:
        raise ValueError("模板字符串默认文本不能包含 ${...} 插值")
    if quote in {"'", '"'}:
        return ast.literal_eval(f"{quote}{raw}{quote}")
    # 只支持无插值模板字符串，足够覆盖 t('key', `默认文本`) 这类声明。
    body = raw.replace(r"\`", "`").replace('"', r"\"")
    return ast.literal_eval(f'"{body}"')


def command_id_to_locale_base(command_id: str) -> str:
    segments = []
    for segment in str(command_id or "").split("."):
        normalized = COMMAND_ID_CAMEL_PATTERN.sub(r"\1_\2", segment)
        normalized = re.sub(r"[\s-]+", "_", normalized).lower().strip("_")
        if normalized:
            segments.append(normalized)
    return ".".join(segments)


GUIDE_STEPS_EXPORT_KEYS = {
    "mainGuideSteps": "main",
    "workflowGuideSteps": "workflow",
    "modListGuideSteps": "modList",
    "searchGuideSteps": "search",
    "issueGuideSteps": "issues",
    "profileGuideSteps": "profile",
    "groupGuideSteps": "group",
    "backupGuideSteps": "backup",
    "workspaceGuideSteps": "workspace",
    "workshopBrowserGuideSteps": "workspaceWorkshop",
    "collectionGuideSteps": "workspaceCollection",
    "githubGuideSteps": "workspaceGithub",
    "ruleCenterGuideSteps": "rules",
    "conflictGuideSteps": "conflict",
    "aiConfigGuideSteps": "aiConfig",
    "textureOptGuideSteps": "textureOpt",
    "aiReviewGuideSteps": "aiReview",
    "logAnalysisGuideSteps": "logAnalysis",
}


def extract_builtin_command_messages(path: Path, source: str) -> dict[str, str]:
    if path != BUILTIN_COMMANDS_PATH:
        return {}
    messages: dict[str, str] = {}
    for match in BUILTIN_COMMAND_CATEGORY_PATTERN.finditer(source):
        key = decode_js_string(match.group("key_text"), match.group("key"))
        default_text = decode_js_string(match.group("default_text"), match.group("default"))
        if key.strip():
            messages[key.strip()] = default_text
    for match in BUILTIN_COMMAND_TEXT_PATTERN.finditer(source):
        command_id = decode_js_string(match.group("id_text"), match.group("id"))
        base_key = command_id_to_locale_base(command_id)
        if not base_key:
            continue
        messages[f"command.{base_key}.title"] = decode_js_string(match.group("title_text"), match.group("title"))
        messages[f"command.{base_key}.description"] = decode_js_string(
            match.group("description_text"),
            match.group("description"),
        )
    return messages


def extract_guide_messages(path: Path, source: str) -> dict[str, str]:
    messages: dict[str, str] = {}
    if path == GUIDE_STORE_PATH:
        for match in GUIDE_ENTRY_TEXT_PATTERN.finditer(source):
            guide_key = decode_js_string(match.group("key_text"), match.group("key"))
            if not guide_key.strip():
                continue
            messages[f"guide.entries.{guide_key}.title"] = decode_js_string(match.group("title_text"), match.group("title"))
            messages[f"guide.entries.{guide_key}.description"] = decode_js_string(
                match.group("description_text"),
                match.group("description"),
            )
    if path == GUIDE_CONFIG_PATH:
        for match in GUIDE_STEPS_EXPORT_PATTERN.finditer(source):
            guide_key = GUIDE_STEPS_EXPORT_KEYS.get(match.group("name"))
            if not guide_key:
                continue
            for index, popover_match in enumerate(GUIDE_STEP_POPOVER_PATTERN.finditer(match.group("body"))):
                messages[f"guide.steps.{guide_key}.{index}.title"] = decode_js_string(
                    popover_match.group("title_text"),
                    popover_match.group("title"),
                )
                messages[f"guide.steps.{guide_key}.{index}.description"] = decode_js_string(
                    popover_match.group("description_text"),
                    popover_match.group("description"),
                )
    return messages


def extract_js_messages(path: Path) -> dict[str, str]:
    source = path.read_text(encoding="utf-8")
    messages: dict[str, str] = {}
    for match in JS_CALL_PATTERN.finditer(source):
        key = decode_js_string(match.group("key_text"), match.group("key"))
        default_text = decode_js_string(match.group("default_text"), match.group("default"))
        if key.strip():
            messages[key.strip()] = default_text
    messages.update(extract_builtin_command_messages(path, source))
    messages.update(extract_guide_messages(path, source))
    return messages


def literal_string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def is_tr_call(node: ast.Call) -> bool:
    return (
        isinstance(node.func, ast.Name) and node.func.id in {"tr", "_tr"}
        or isinstance(node.func, ast.Attribute) and node.func.attr == "tr"
    )


def api_message_key_from_code(namespace: str, code: str = "") -> str:
    normalized = re.sub(r"[^a-z0-9.]+", "_", str(code or "").strip().lower()).strip("._")
    if not normalized or normalized in {"app.unknown_error", "app.warning"}:
        return ""
    return f"api.{namespace}.{normalized}"


def extract_api_response_messages(tree: ast.AST) -> dict[str, str]:
    messages: dict[str, str] = {}
    namespaces = {"error": "errors", "warning": "warnings"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "ApiResponse"
            and func.attr in namespaces
        ):
            continue
        keywords = call_keywords(node)
        # user_message 已经由 tr() 或调用方显式 key 管理；这里只兜住未来新增的简洁字面量调用。
        if "user_message" in keywords or "message_key" in keywords:
            continue
        default_text = literal_string(node.args[0]) if node.args else None
        code = literal_string(keywords["code"]) if "code" in keywords else None
        key = api_message_key_from_code(namespaces[func.attr], code or "")
        if key and default_text:
            messages[key] = default_text
    return messages


def extract_python_messages(path: Path) -> dict[str, str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    messages: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not is_tr_call(node) or len(node.args) < 2:
            continue
        key = literal_string(node.args[0])
        default_text = literal_string(node.args[1])
        if key and default_text is not None:
            messages[key.strip()] = default_text
    messages.update(extract_api_response_messages(tree))
    messages.update(extract_ai_action_messages(path, tree))
    messages.update(extract_ai_entry_messages(path, tree))
    messages.update(extract_ai_attachment_messages(path, tree))
    messages.update(extract_ai_tool_messages(path, tree))
    return messages


AI_ACTION_FIELDS = {
    "label",
    "description",
    "execute_label",
    "unsupported_message",
    "execution_failed_message",
}
AI_ACTION_VARIANT_FIELDS = {
    "label",
    "title",
    "description",
    "preview_template",
    "execute_label",
    "missing_payload_message",
    "success_message",
    "confirm_title",
    "confirm_message",
    "confirm_confirm_text",
    "post_success_title",
    "post_success_message",
    "post_success_confirm_text",
    "blocked_message",
}


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def call_keywords(node: ast.Call) -> dict[str, ast.AST]:
    return {kw.arg: kw.value for kw in node.keywords if kw.arg}


def module_constants(tree: ast.AST) -> dict[str, Any]:
    constants: dict[str, Any] = {}
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.Assign):
            continue
        try:
            value = ast.literal_eval(node.value)
        except Exception:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                constants[target.id] = value
    return constants


def static_string(node: ast.AST | None, constants: Mapping[str, Any] | None = None) -> str | None:
    if node is None:
        return None
    literal = literal_string(node)
    if literal is not None:
        return literal
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value_node in node.values:
            if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                parts.append(value_node.value)
            elif isinstance(value_node, ast.FormattedValue) and isinstance(value_node.value, ast.Name):
                const_value = (constants or {}).get(value_node.value.id)
                if const_value is None:
                    return None
                parts.append(str(const_value))
            else:
                return None
        return "".join(parts)
    return None


def iter_literal_dict_items(node: ast.AST | None) -> Iterable[tuple[str, ast.AST]]:
    if not isinstance(node, ast.Dict):
        return []
    items: list[tuple[str, ast.AST]] = []
    for key_node, value_node in zip(node.keys, node.values):
        key = literal_string(key_node) if key_node else None
        if key:
            items.append((key, value_node))
    return items


def unwrap_model_dump_call(node: ast.AST) -> ast.AST:
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "model_dump"
        and isinstance(node.func.value, ast.Call)
    ):
        return node.func.value
    return node


def extract_ai_action_messages(path: Path, tree: ast.AST) -> dict[str, str]:
    if path != AI_ACTION_DEFINITIONS_PATH:
        return {}
    messages: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key_node, value_node in zip(node.keys, node.values):
            action_type = literal_string(key_node) if key_node else None
            value_node = unwrap_model_dump_call(value_node)
            if not action_type or not isinstance(value_node, ast.Call) or call_name(value_node.func) != "ActionDefinition":
                continue
            action_base = f"ai.actions.{action_type}"
            keywords = call_keywords(value_node)
            for field in AI_ACTION_FIELDS:
                default_text = static_string(keywords.get(field))
                if default_text is not None:
                    messages[f"{action_base}.{field}"] = default_text
            variants_node = keywords.get("variants")
            if not isinstance(variants_node, ast.Dict):
                continue
            for variant_key_node, variant_value_node in zip(variants_node.keys, variants_node.values):
                variant = literal_string(variant_key_node) if variant_key_node else None
                if not variant or not isinstance(variant_value_node, ast.Call) or call_name(variant_value_node.func) != "ActionVariantDefinition":
                    continue
                variant_base = f"{action_base}.variants.{variant}"
                variant_keywords = call_keywords(variant_value_node)
                for field in AI_ACTION_VARIANT_FIELDS:
                    default_text = static_string(variant_keywords.get(field))
                    if default_text is not None:
                        messages[f"{variant_base}.{field}"] = default_text
    return messages


def extract_prompt_definition_messages(prompt_id: str, node: ast.AST, messages: dict[str, str]) -> None:
    call = unwrap_model_dump_call(node)
    if isinstance(call, ast.Call) and call_name(call.func) == "_with_prompt_meta" and call.args:
        payload = call.args[0]
    else:
        payload = call
    if not isinstance(payload, ast.Dict):
        return
    fields = dict(iter_literal_dict_items(payload))
    for field in ("name", "description"):
        default_text = static_string(fields.get(field))
        if default_text is not None:
            messages[f"ai.prompts.{prompt_id}.{field}"] = default_text


def ai_entry_locale_id(group: str, entry_id: str) -> str:
    """去掉定义 ID 中和分组重复的业务前缀，避免生成 assistants.assistant.* 这类冗余路径。"""
    prefixes = {
        "assistants": "assistant.",
        "tasks": "task.",
    }
    prefix = prefixes.get(group, "")
    return entry_id.removeprefix(prefix) if prefix else entry_id


def extract_entry_definition_messages(group: str, entry_id: str, node: ast.AST, messages: dict[str, str]) -> None:
    call = unwrap_model_dump_call(node)
    if not isinstance(call, ast.Call):
        return
    locale_id = ai_entry_locale_id(group, entry_id)
    keywords = call_keywords(call)
    for field in ("name", "description"):
        default_text = static_string(keywords.get(field))
        if default_text is not None:
            messages[f"ai.definitions.{group}.{locale_id}.{field}"] = default_text


def extract_prompt_category_messages(category_id: str, node: ast.AST, messages: dict[str, str]) -> None:
    call = unwrap_model_dump_call(node)
    if not isinstance(call, ast.Call) or call_name(call.func) != "PromptCategoryDefinition":
        return
    base_key = f"ai.definitions.categories.{category_id}"
    keywords = call_keywords(call)
    for field in ("label", "description"):
        default_text = static_string(keywords.get(field))
        if default_text is not None:
            messages[f"{base_key}.{field}"] = default_text
    variables_node = keywords.get("base_variables")
    if not isinstance(variables_node, ast.List):
        return
    for variable_node in variables_node.elts:
        if not isinstance(variable_node, ast.Call) or call_name(variable_node.func) != "PromptVariableDefinition":
            continue
        variable_keywords = call_keywords(variable_node)
        variable_key = static_string(variable_keywords.get("key"))
        if not variable_key:
            continue
        for field in ("label", "description"):
            default_text = static_string(variable_keywords.get(field))
            if default_text is not None:
                messages[f"{base_key}.base_variables.{variable_key}.{field}"] = default_text


def extract_ai_entry_messages(path: Path, tree: ast.AST) -> dict[str, str]:
    if path != AI_ENTRY_DEFINITIONS_PATH:
        return {}
    messages: dict[str, str] = {}
    function_groups = {
        "get_default_ai_prompts": "prompts",
        "get_default_assistant_definitions": "assistants",
        "get_default_task_definitions": "tasks",
        "get_prompt_category_definitions": "categories",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name not in function_groups:
            continue
        group = function_groups[node.name]
        for child in ast.walk(node):
            if not isinstance(child, ast.Return):
                continue
            for item_id, item_node in iter_literal_dict_items(child.value):
                if group == "prompts":
                    extract_prompt_definition_messages(item_id, item_node, messages)
                elif group == "categories":
                    extract_prompt_category_messages(item_id, item_node, messages)
                else:
                    extract_entry_definition_messages(group, item_id, item_node, messages)
    return messages


def extract_prompt_variable_messages(base_key: str, list_node: ast.AST | None, messages: dict[str, str]) -> None:
    if not isinstance(list_node, ast.List):
        return
    for variable_node in list_node.elts:
        if not isinstance(variable_node, ast.Call) or call_name(variable_node.func) != "PromptVariableDefinition":
            continue
        keywords = call_keywords(variable_node)
        variable_key = static_string(keywords.get("key"))
        if not variable_key:
            continue
        for field in ("label", "description"):
            default_text = static_string(keywords.get(field))
            if default_text is not None:
                messages[f"{base_key}.prompt_variables.{variable_key}.{field}"] = default_text


def extract_projection_option_messages(base_key: str, list_node: ast.AST | None, messages: dict[str, str]) -> None:
    if not isinstance(list_node, ast.List):
        return
    for field_node in list_node.elts:
        if not isinstance(field_node, ast.Call) or call_name(field_node.func) != "AttachmentProjectionFieldDefinition":
            continue
        keywords = call_keywords(field_node)
        path_key = static_string(keywords.get("path"))
        if not path_key:
            continue
        for field in ("label", "description"):
            default_text = static_string(keywords.get(field))
            if default_text is not None:
                messages[f"{base_key}.projection_options.{path_key}.{field}"] = default_text


def extract_ai_attachment_messages(path: Path, tree: ast.AST) -> dict[str, str]:
    if path != AI_ATTACHMENT_DEFINITIONS_PATH:
        return {}
    messages: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "get_attachment_definitions":
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Return):
                continue
            for kind, item_node in iter_literal_dict_items(child.value):
                call = unwrap_model_dump_call(item_node)
                if not isinstance(call, ast.Call) or call_name(call.func) != "AttachmentDefinition":
                    continue
                base_key = f"ai.definitions.attachments.{kind}"
                keywords = call_keywords(call)
                for field in ("label", "description"):
                    default_text = static_string(keywords.get(field))
                    if default_text is not None:
                        messages[f"{base_key}.{field}"] = default_text
                extract_prompt_variable_messages(base_key, keywords.get("prompt_variables"), messages)
                extract_projection_option_messages(base_key, keywords.get("projection_options"), messages)
    return messages


def extract_ai_tool_messages(path: Path, tree: ast.AST) -> dict[str, str]:
    if path != AI_TOOL_DEFINITIONS_PATH:
        return {}
    messages: dict[str, str] = {}
    constants = module_constants(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for tool_id, item_node in iter_literal_dict_items(node):
            call = unwrap_model_dump_call(item_node)
            if not isinstance(call, ast.Call) or call_name(call.func) != "ToolDefinition":
                continue
            base_key = f"ai.tools.{tool_id}"
            keywords = call_keywords(call)
            label = static_string(keywords.get("label"), constants)
            description = static_string(keywords.get("ui_description"), constants)
            if label is not None:
                messages[f"{base_key}.label"] = label
            if description is not None:
                messages[f"{base_key}.description"] = description
    return messages


def merge_extracted_messages() -> dict[str, str]:
    extracted: dict[str, str] = {}
    origins: dict[str, Path] = {}
    conflicts: list[str] = []
    for path in iter_source_files():
        file_messages = extract_python_messages(path) if path.suffix == ".py" else extract_js_messages(path)
        for key, default_text in file_messages.items():
            if key in extracted and extracted[key] != default_text:
                conflicts.append(
                    f"{key}: {origins[key].relative_to(ROOT).as_posix()}={extracted[key]!r}, "
                    f"{path.relative_to(ROOT).as_posix()}={default_text!r}"
                )
                continue
            extracted[key] = default_text
            origins[key] = path
    if conflicts:
        joined = "\n".join(conflicts)
        raise SystemExit(f"发现相同 i18n key 对应不同默认中文，请先统一：\n{joined}")
    return extracted


def load_locale(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def set_nested(payload: dict[str, Any], dotted_key: str, value: str) -> None:
    parts = [part for part in dotted_key.split(".") if part]
    if not parts:
        return
    current = payload
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def extract_placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER_PATTERN.findall(str(text or "")))


def extract_locale_markers(text: str) -> list[str]:
    return LOCALE_MARKER_PATTERN.findall(str(text or ""))


def flatten_string_values(payload: Mapping[str, Any], prefix: str = "") -> dict[str, str]:
    values: dict[str, str] = {}
    for key, value in payload.items():
        if key == "_meta":
            continue
        dotted = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, str):
            values[dotted] = value
        elif isinstance(value, Mapping):
            values.update(flatten_string_values(value, dotted))
    return values


def flatten_structure_paths(payload: Mapping[str, Any], prefix: str = "") -> list[str]:
    paths: list[str] = []
    for key, value in payload.items():
        if key == "_meta":
            continue
        dotted = f"{prefix}.{key}" if prefix else str(key)
        paths.append(dotted)
        if isinstance(value, Mapping):
            paths.extend(flatten_structure_paths(value, dotted))
    return paths


def check_builtin_locale_keys(
    extracted: Mapping[str, str],
    expected_structure_order: list[str] | None = None,
    default_values: Mapping[str, str] | None = None,
) -> list[str]:
    expected = set(extracted)
    expected_structure_order = expected_structure_order or list(extracted)
    default_values = default_values or extracted
    errors: list[str] = []
    seen_languages: dict[str, Path] = {}
    for path in sorted(BUILTIN_LOCALES_DIR.glob("*.json")):
        locale_payload = load_locale(path)
        meta = locale_payload.get("_meta") if isinstance(locale_payload, Mapping) else {}
        if not isinstance(meta, Mapping):
            errors.append(f"{path.relative_to(ROOT).as_posix()} 缺少 _meta")
        else:
            meta_type = str(meta.get("type") or "").strip()
            language = str(meta.get("language") or "").strip()
            label = str(meta.get("label") or "").strip()
            name = str(meta.get("name") or "").strip()
            if meta_type != "builtin_locale":
                errors.append(f"{path.relative_to(ROOT).as_posix()} _meta.type 应为 'builtin_locale'，实际为 {meta_type!r}")
            if not language:
                errors.append(f"{path.relative_to(ROOT).as_posix()} _meta.language 不能为空")
            elif language in seen_languages:
                errors.append(f"{path.relative_to(ROOT).as_posix()} _meta.language 与 {seen_languages[language].relative_to(ROOT).as_posix()} 重复: {language}")
            else:
                seen_languages[language] = path
            if not label:
                errors.append(f"{path.relative_to(ROOT).as_posix()} _meta.label 不能为空")
            if not name:
                errors.append(f"{path.relative_to(ROOT).as_posix()} _meta.name 不能为空")
        if path.name == DEFAULT_LOCALE_PATH.name:
            continue
        actual_values = flatten_string_values(locale_payload)
        actual_structure_order = flatten_structure_paths(locale_payload)
        actual = set(actual_values)
        actual_structure = set(actual_structure_order)
        expected_structure = set(expected_structure_order)
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        missing_structure = sorted(expected_structure - actual_structure)
        extra_structure = sorted(actual_structure - expected_structure)
        if missing:
            errors.append(f"{path.relative_to(ROOT).as_posix()} 缺少 key: {', '.join(missing[:20])}{' ...' if len(missing) > 20 else ''}")
        if extra:
            errors.append(f"{path.relative_to(ROOT).as_posix()} 存在未使用 key: {', '.join(extra[:20])}{' ...' if len(extra) > 20 else ''}")
        if missing_structure:
            errors.append(f"{path.relative_to(ROOT).as_posix()} 缺少结构节点: {', '.join(missing_structure[:20])}{' ...' if len(missing_structure) > 20 else ''}")
        if extra_structure:
            errors.append(f"{path.relative_to(ROOT).as_posix()} 存在多余结构节点: {', '.join(extra_structure[:20])}{' ...' if len(extra_structure) > 20 else ''}")
        if not missing_structure and not extra_structure and actual_structure_order != expected_structure_order:
            errors.append(f"{path.relative_to(ROOT).as_posix()} 结构顺序未与 {DEFAULT_LOCALE_PATH.relative_to(ROOT).as_posix()} 对齐")
        for key in sorted(expected & actual):
            default_params = extract_placeholders(extracted[key])
            locale_params = extract_placeholders(actual_values[key])
            if default_params != locale_params:
                errors.append(
                    f"{path.relative_to(ROOT).as_posix()} 参数不一致: {key} "
                    f"默认={sorted(default_params)} 翻译={sorted(locale_params)}"
                )
            default_markers = extract_locale_markers(default_values.get(key, extracted[key]))
            locale_markers = extract_locale_markers(actual_values[key])
            if default_markers != locale_markers:
                errors.append(
                    f"{path.relative_to(ROOT).as_posix()} 格式标记不一致: {key} "
                    f"默认={default_markers} 翻译={locale_markers}"
                )
    return errors


def copy_locale_meta(existing: Mapping[str, Any]) -> dict[str, Any]:
    meta = existing.get("_meta") if isinstance(existing, Mapping) else {}
    return {"_meta": dict(meta)} if isinstance(meta, Mapping) else {}


def build_locale_payload(existing: Mapping[str, Any], extracted: Mapping[str, str]) -> dict[str, Any]:
    payload = copy_locale_meta(existing)
    for key in sorted(extracted):
        set_nested(payload, key, extracted[key])
    return payload


def align_locale_structure(reference: Mapping[str, Any], target: Mapping[str, Any]) -> dict[str, Any]:
    output = copy_locale_meta(target)
    for key, reference_value in reference.items():
        if key == "_meta":
            continue
        target_has_key = key in target
        target_value = target.get(key)
        if isinstance(reference_value, Mapping):
            output[key] = align_locale_structure(
                reference_value,
                target_value if isinstance(target_value, Mapping) else {},
            )
        elif target_has_key:
            output[key] = target_value
    for key, value in target.items():
        if key not in output and key != "_meta":
            output[key] = value
    return output


def untranslated_fallback(source_text: str) -> str:
    text = str(source_text or "")
    return f"{UNTRANSLATED_PREFIX}{text}" if CHINESE_PATTERN.search(text) else text


def build_translated_locale_payload(
    existing: Mapping[str, Any],
    previous_default: Mapping[str, str],
    extracted: Mapping[str, str],
    reference_payload: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], int]:
    existing_values = flatten_string_values(existing)
    payload = copy_locale_meta(existing)
    reset_count = 0
    ordered_keys = [key for key in previous_default if key in extracted]
    written_keys = set(ordered_keys)
    ordered_keys.extend(key for key in sorted(extracted) if key not in written_keys)
    for key in ordered_keys:
        source_text = extracted[key]
        translated = existing_values.get(key)
        source_changed = previous_default.get(key) != source_text
        params_changed = translated is not None and extract_placeholders(translated) != extract_placeholders(source_text)
        if translated is None or source_changed or params_changed:
            translated = untranslated_fallback(source_text)
            reset_count += 1
        elif translated == source_text and CHINESE_PATTERN.search(source_text):
            translated = untranslated_fallback(source_text)
            reset_count += 1
        set_nested(payload, key, translated)
    if reference_payload is not None:
        payload = align_locale_structure(reference_payload, payload)
    return payload, reset_count


def sync_builtin_locales(previous_default: Mapping[str, str], extracted: Mapping[str, str], reference_payload: Mapping[str, Any]) -> list[str]:
    results: list[str] = []
    for path in sorted(BUILTIN_LOCALES_DIR.glob("*.json")):
        if path.name == DEFAULT_LOCALE_PATH.name:
            continue
        payload, reset_count = build_translated_locale_payload(load_locale(path), previous_default, extracted, reference_payload)
        write_json(path, payload)
        results.append(f"{path.relative_to(ROOT).as_posix()}：同步 {len(extracted)} 条，重置 {reset_count} 条")
    return results


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def strip_inline_comment(line: str, suffix: str) -> str:
    """剥掉行内注释，避免把配置注释当作界面文案。"""
    markers = ("#",) if suffix == ".py" else ("//",)
    quote = ""
    escaped = False
    index = 0
    while index < len(line):
        char = line[index]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif quote:
            if char == quote:
                quote = ""
        elif char in {"'", '"', "`"}:
            quote = char
        elif any(line.startswith(marker, index) for marker in markers):
            return line[:index]
        index += 1
    return line


def paren_delta(line: str) -> int:
    return line.count("(") - line.count(")")


def is_bare_chinese_candidate(path: Path, line: str) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if rel in BARE_CHINESE_EXCLUDED_FILES:
        return False
    if any(part in rel for part in BARE_CHINESE_EXCLUDED_PARTS):
        return False
    stripped = line.strip()
    if not stripped or stripped.startswith(BARE_CHINESE_EXCLUDED_LINE_PREFIXES):
        return False
    code_line = strip_inline_comment(line, path.suffix).strip()
    if not code_line or not CHINESE_PATTERN.search(code_line):
        return False
    if I18N_CALL_LINE_PATTERN.search(code_line):
        return False
    if "record_timeline(" in code_line:
        return False
    if "text.startswith(" in code_line or "text ==" in code_line:
        return False
    if any(marker in code_line for marker in BARE_CHINESE_LOG_MARKERS):
        return False
    if path.suffix in {".py", ".js"} and not any(quote in code_line for quote in ("'", '"', "`")):
        return False
    return True


def report_bare_chinese(limit: int) -> int:
    hits: list[str] = []
    for path in iter_source_files():
        in_python_docstring = False
        in_block_comment = False
        skip_call_depth = 0
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if skip_call_depth > 0:
                skip_call_depth = max(0, skip_call_depth + paren_delta(line))
                continue
            if any(marker in line for marker in BARE_CHINESE_CONTEXT_SKIP_MARKERS):
                skip_call_depth = max(0, paren_delta(line))
                continue
            if in_block_comment:
                if "*/" in stripped or "-->" in stripped:
                    in_block_comment = False
                continue
            if stripped.startswith(("/*", "<!--")):
                if not ("*/" in stripped or "-->" in stripped):
                    in_block_comment = True
                continue
            if path.suffix == ".py":
                if (stripped.startswith('"""') and stripped.endswith('"""') and len(stripped) > 3) or (stripped.startswith("'''") and stripped.endswith("'''") and len(stripped) > 3):
                    continue
                delimiter_count = line.count('"""') + line.count("'''")
                if in_python_docstring:
                    if delimiter_count % 2 == 1:
                        in_python_docstring = False
                    continue
                if delimiter_count % 2 == 1:
                    in_python_docstring = True
                    continue
            if is_bare_chinese_candidate(path, line):
                hits.append(f"{path.relative_to(ROOT).as_posix()}:{lineno}: {line.strip()}")
                if len(hits) >= limit:
                    break
        if len(hits) >= limit:
            break
    if not hits:
        print("未发现疑似裸中文。")
        return 0
    print(f"疑似裸中文 {len(hits)} 条（最多显示 {limit} 条，注释/日志/Prompt 已粗略过滤）：")
    print("\n".join(hits))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="扫描 t/tr 调用并增量生成默认中文语言包。")
    parser.add_argument("--check", action="store_true", help="只检查 zh-CN.json 是否已同步，不写入文件。")
    parser.add_argument("--report-bare-chinese", action="store_true", help="报告疑似未接入 i18n 的裸中文，不阻断构建。")
    parser.add_argument("--report-limit", type=int, default=120, help="裸中文报告最多显示条数。")
    parser.add_argument("--locale-file", type=Path, default=DEFAULT_LOCALE_PATH, help="默认中文语言包路径。")
    args = parser.parse_args()

    if args.report_bare_chinese:
        return report_bare_chinese(max(args.report_limit, 1))

    locale_path = args.locale_file if args.locale_file.is_absolute() else ROOT / args.locale_file
    extracted = merge_extracted_messages()
    current_locale = load_locale(locale_path)
    previous_default = flatten_string_values(current_locale)
    next_payload = build_locale_payload(current_locale, extracted)
    next_text = json.dumps(next_payload, ensure_ascii=False, indent=2) + "\n"
    current_text = locale_path.read_text(encoding="utf-8") if locale_path.exists() else ""
    if args.check:
        if current_text != next_text:
            print(f"{locale_path.relative_to(ROOT).as_posix()} 未同步，请运行：uv run python scripts/extract_i18n_messages.py", file=sys.stderr)
            return 1
        next_values = flatten_string_values(next_payload)
        locale_errors = check_builtin_locale_keys(extracted, flatten_structure_paths(next_payload), next_values)
        if locale_errors:
            print("\n".join(locale_errors), file=sys.stderr)
            return 1
        print(f"i18n 默认语言包已同步，共 {len(extracted)} 条。")
        return 0
    write_json(locale_path, next_payload)
    synced_locales = sync_builtin_locales(previous_default, extracted, next_payload) if locale_path.resolve() == DEFAULT_LOCALE_PATH.resolve() else []
    print(f"已更新 {locale_path.relative_to(ROOT).as_posix()}，共 {len(extracted)} 条。")
    for item in synced_locales:
        print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
