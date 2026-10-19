import ast
import re
from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from packaging import version
from requests import RequestException

from backend.managers.mgr_network import build_retry_session
from backend.utils.tools import get_package_platform_match, get_current_package_platform_keywords, has_supported_update_package_name


class LanzouParser:
    UPDATE_FILENAME_PATTERN = re.compile(r"(?<!\d)v?(\d+\.\d+\.\d+)(?!\d)", re.I)
    ACW_ARG_ORDER = [0xf, 0x23, 0x1d, 0x18, 0x21, 0x10, 0x1, 0x26, 0xa, 0x9, 0x13, 0x1f, 0x28, 0x1b, 0x16, 0x17, 0x19, 0xd, 0x6, 0xb, 0x27, 0x12, 0x14, 0x8, 0xe, 0x15, 0x20, 0x1a, 0x2, 0x1e, 0x7, 0x4, 0x11, 0x5, 0x3, 0x1c, 0x22, 0x25, 0xc, 0x24]
    ACW_KEY = "3000176000856006061501533003690027800375"
    JS_TOKENS = re.compile(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|//[^\n]*|/\*.*?\*/|[{}\[\](),;:+\n]", re.S)
    MAX_CANDIDATES = 4
    MAX_PAGES = 100
    PAGE_SIZE = 50

    def __init__(self, session: Any = None, *, check_cancelled: Callable[[], None] | None = None):
        # 蓝奏云是直连来源，不继承应用或环境代理。
        self.session = session if session is not None else build_retry_session(route_manager=False, trust_env=False)
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })
        self.last_error = ""
        self._check_cancelled = check_cancelled

    def _get_with_acw_retry(self, url: str, **kwargs: Any) -> Any:
        kwargs.setdefault("timeout", (5, 30))
        for attempt in range(2):
            if self._check_cancelled:
                self._check_cancelled()
            res = self.session.get(url, **kwargs)
            if res.status_code >= 400:
                res.raise_for_status()
            # 部分页面未声明 HTTP 编码，但正文是 UTF-8。
            if getattr(res, "encoding", None) == "ISO-8859-1":
                res.encoding = "utf-8"
            cookie = self._extract_acw_cookie(res.text)
            if not cookie:
                return res
            if attempt == 0:
                url = getattr(res, "url", None) or url
                self.session.cookies.set("acw_sc__v2", cookie, domain=urlparse(url).hostname, path="/")
        raise ValueError("蓝奏云浏览器校验未通过，请稍后重试")

    @classmethod
    def _extract_acw_cookie(cls, html: str) -> str:
        if "acw_sc__v2" not in html:
            return ""
        match = re.search(r"\barg1\s*=\s*['\"]([0-9a-fA-F]{40})['\"]", html)
        if not match:
            raise ValueError("蓝奏云浏览器校验方式已变化")
        mixed = "".join(match.group(1)[order - 1] for order in cls.ACW_ARG_ORDER)
        return "".join(f"{int(mixed[i:i + 2], 16) ^ int(cls.ACW_KEY[i:i + 2], 16):02x}" for i in range(0, 40, 2))

    @staticmethod
    def _ensure_url_scheme(url: str) -> str:
        text = str(url or "").strip()
        if text.startswith("//"):
            text = f"https:{text}"
        elif text and not urlparse(text).scheme:
            text = f"https://{text}"
        parsed = urlparse(text)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or re.search(r"\s", text):
            raise ValueError("蓝奏云返回了无效的网页或下载地址")
        return text

    @classmethod
    def _split_js(cls, text: str, separators: str = ",") -> Iterator[str]:
        """只在字符串、注释和括号之外分段，不执行网页脚本。"""
        depth = 0
        start = 0
        for match in cls.JS_TOKENS.finditer(text):
            token = match.group()
            if token.startswith(("'", '"', "//", "/*")):
                continue
            if depth == 0 and token in separators:
                yield text[start:match.start()].strip()
                start = match.end()
            elif token in "{[(":
                depth += 1
            elif token in "}])":
                depth -= 1
                if depth < 0:
                    return
        yield text[start:].strip()

    @classmethod
    def _resolve_js(cls, expression: str, variables: dict[str, list[str]], seen: tuple[str, ...] = ()) -> list[Any]:
        """支持字面量、变量别名和加法；分支赋值只形成有上限的候选。"""
        # shortcut: 不解释任意 JS；签名改为运行时计算时需扩展专用解析策略。
        expression = expression.strip()
        if not expression or len(seen) >= 12:
            return []
        parts = list(cls._split_js(expression, "+"))
        if len(parts) > 1:
            values = cls._resolve_js(parts[0], variables, seen)
            for part in parts[1:]:
                right = cls._resolve_js(part, variables, seen)
                values = [(str(a) + str(b) if isinstance(a, str) or isinstance(b, str) else a + b)
                          for a in values for b in right][:cls.MAX_CANDIDATES]
            return values
        if re.fullmatch(r"[a-zA-Z_$][\w$]*", expression):
            if expression in {"true", "false", "null"}:
                return [{"true": True, "false": False, "null": ""}[expression]]
            if expression in seen:
                return []
            values = []
            for assigned in variables.get(expression, []):
                for value in cls._resolve_js(assigned, variables, (*seen, expression)):
                    if value not in values:
                        values.append(value)
                if len(values) >= cls.MAX_CANDIDATES:
                    break
            return values[:cls.MAX_CANDIDATES]
        try:
            value = ast.literal_eval(expression.replace(r"\/", "/"))
        except (ValueError, SyntaxError):
            return []
        return [value] if type(value) in {str, int, float, bool} else []

    @classmethod
    def _extract_requests(cls, html: str, page_url: str, kind: str, overrides: dict[str, Any] | None = None) -> list[tuple[str, dict[str, Any]]]:
        """从同一个 Ajax 声明提取 URL 与数据，不猜接口地址或补造参数。"""
        scripts = BeautifulSoup(html, "html.parser").find_all("script")
        script = "\n".join(item.get_text() for item in scripts) if scripts else html
        script = cls.JS_TOKENS.sub(lambda m: " " if m.group().startswith(("//", "/*")) else m.group(), script)
        # 保持位置不变地遮住字符串，避免把字符串内容误认成赋值或请求声明。
        code = cls.JS_TOKENS.sub(lambda m: " " * len(m.group()) if m.group().startswith(("'", '"')) else m.group(), script)
        variables: dict[str, list[str]] = {}
        for match in re.finditer(r"(?<![\w$.])([a-zA-Z_$][\w$]*)\s*=(?!=)", code):
            value = next(cls._split_js(script[match.end():], ",;\n"), "")
            variables.setdefault(match.group(1), []).append(value)
        requests = []
        for match in re.finditer(r"(?:\$|jQuery)\s*\.\s*ajax\s*\(\s*(?=\{)", code):
            options = next(cls._split_js(script[match.end():], ")"), "")
            fields = {}
            for part in cls._split_js(options[1:-1]):
                pair = list(cls._split_js(part, ":"))
                if len(pair) >= 2:
                    fields[pair[0].strip("'\"")] = ":".join(pair[1:])
            data = fields.get("data", "").strip()
            if not data.startswith("{") or not data.endswith("}"):
                continue
            payloads = [{}]
            for part in cls._split_js(data[1:-1]):
                pair = list(cls._split_js(part, ":"))
                if len(pair) < 2:
                    continue
                key = pair[0].strip("'\"")
                if overrides and key in overrides:
                    values = [overrides[key]]
                else:
                    values = cls._resolve_js(":".join(pair[1:]), variables)
                if not values:
                    break
                payloads = [{**payload, key: value} for payload in payloads for value in values][:cls.MAX_CANDIDATES]
            else:
                payloads = [payload for payload in payloads if
                            ({"fid", "t", "k"}.issubset(payload) if kind == "folder" else payload.get("action") == "downprocess")]
                if not payloads:
                    continue
                for endpoint in cls._resolve_js(fields.get("url", ""), variables):
                    if not isinstance(endpoint, str) or not endpoint:
                        continue
                    try:
                        endpoint = cls._ensure_url_scheme(urljoin(page_url, str(endpoint)))
                    except ValueError:
                        continue
                    for payload in payloads:
                        candidate = (endpoint, payload)
                        if candidate not in requests:
                            requests.append(candidate)
            if len(requests) >= cls.MAX_CANDIDATES:
                break
        if not requests:
            raise ValueError("无法识别蓝奏云页面中的请求参数，页面格式可能已变化")
        return requests[:cls.MAX_CANDIDATES]

    def _post_request(self, candidates: list[tuple[str, dict[str, Any]]], page_url: str, kind: str) -> dict[str, Any]:
        parsed = urlparse(page_url)
        headers = {"Referer": page_url, "Origin": f"{parsed.scheme}://{parsed.netloc}", "X-Requested-With": "XMLHttpRequest"}
        errors = []
        for endpoint, payload in candidates:
            if self._check_cancelled:
                self._check_cancelled()
            try:
                payload = {key: str(value).lower() if isinstance(value, bool) else value for key, value in payload.items()}
                res = self.session.post(endpoint, data=payload, headers=headers, timeout=(5, 30))
                if res.status_code >= 400:
                    res.raise_for_status()
                data = res.json()
                if not isinstance(data, dict) or "zt" not in data:
                    raise ValueError("蓝奏云接口未返回有效的结果")
                status = str(data["zt"])
                if status == "2" and kind == "folder":
                    return data
                if status != "1":
                    raise ValueError(f"蓝奏云拒绝请求：{str(data.get('info') or data['zt'])[:160]}")
                if kind == "folder":
                    files = data.get("text")
                    if not isinstance(files, list) or any(not isinstance(item, dict) or not item.get("id") for item in files):
                        raise ValueError("蓝奏云返回的文件列表格式无效")
                elif not isinstance(data.get("dom"), str) or not data["dom"] or not isinstance(data.get("url"), str) or data["url"] in {"", "0"}:
                    raise ValueError("蓝奏云未返回有效的下载地址")
                return data
            except (RequestException, ValueError) as exc:
                # 不记录完整 URL 和参数，避免将签名、提取码写入日志。
                reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
                errors.append(f"{urlparse(endpoint).netloc}: {reason}")
        raise ValueError("蓝奏云请求失败：" + "; ".join(errors))

    def get_all_files(self, folder_url: str, password: str = "") -> dict[str, Any] | None:
        """读取完整文件列表后选择更新包；分页失败时不返回不完整的最新版。"""
        self.last_error = ""
        try:
            folder_url = self._ensure_url_scheme(folder_url)
            res = self._get_with_acw_retry(folder_url)
            page_url = getattr(res, "url", None) or folder_url
            candidates = self._extract_requests(res.text, page_url, "folder", {"pwd": password, "pg": 1})
            all_files = []
            seen = set()
            for page in range(1, self.MAX_PAGES + 1):
                current = [(url, {**payload, "pg": page}) for url, payload in candidates]
                data = self._post_request(current, page_url, "folder")
                if str(data["zt"]) == "2":
                    break
                files = data["text"]
                if not files:
                    break
                previous_count = len(seen)
                for item in files:
                    file_id = urlparse(str(item["id"])).path
                    if file_id in seen:
                        continue
                    seen.add(file_id)
                    all_files.append(self._build_file_info(item))
                if len(seen) == previous_count:
                    raise ValueError("蓝奏云分页未向后推进，无法确认完整文件列表")
                # 列表接口短页即结束；继续请求会被部分节点判为过期。
                if len(files) < self.PAGE_SIZE:
                    break
            else:
                raise ValueError("蓝奏云文件列表超过分页上限，无法确认最新版本")
            if not all_files:
                raise ValueError("文件夹内无文件")
            all_files.sort(key=self._file_sort_key, reverse=True)
            latest = self._select_latest_update_file(all_files)
            if latest:
                detail = self.get_file(urljoin(page_url, "/" + str(latest["id"])))
                if not detail:
                    raise ValueError(self.last_error or "无法获取最新版本的下载地址")
                latest.update(detail)
            return {"files": all_files, "latest": latest}
        except (RequestException, ValueError) as exc:
            self.last_error = f"获取蓝奏云文件列表失败：{exc}"
            return None

    def _build_file_info(self, raw_file):
        name = str(raw_file.get('name_all') or '').strip()
        package_info = self._parse_update_filename(name)
        return {
            "id": raw_file.get('id'),
            "filename": name,
            "size": raw_file.get('size'),
            "time": raw_file.get('time'),
            "version": package_info["version"] if package_info else "0.0.0",
            "is_update_package": bool(package_info),
            "platform_compatible": package_info["platform_compatible"] if package_info else False,
            "platform_matched": package_info["platform_matched"] if package_info else False,
        }

    def _parse_update_filename(self, filename):
        lower_name = str(filename or "").strip().lower()
        if not lower_name.endswith(".zip"):
            return None
        if not has_supported_update_package_name(lower_name):
            return None

        version_match = self.UPDATE_FILENAME_PATTERN.search(lower_name)
        if not version_match:
            return None
        version_text = version_match.group(1)
        try:
            version.parse(version_text)
        except Exception:
            return None

        current_keywords, _ = get_current_package_platform_keywords()
        matches_current_platform, has_known_platform = get_package_platform_match(lower_name)
        if current_keywords and has_known_platform and not matches_current_platform:
            return None

        return {
            "version": version_text,
            "platform_compatible": True,
            "platform_matched": matches_current_platform,
        }

    def _select_latest_update_file(self, all_files):
        candidates = [item for item in all_files if item.get("is_update_package") and item.get("platform_compatible")]
        if not candidates:
            return None
        return max(candidates, key=self._file_sort_key)

    @staticmethod
    def _file_sort_key(file_info):
        try:
            parsed_version = version.parse(str(file_info.get("version") or "0.0.0"))
        except Exception:
            parsed_version = version.parse("0.0.0")
        return (parsed_version, 1 if file_info.get("platform_matched") else 0)

    def get_file(self, url: str) -> dict[str, str] | None:
        """读取文件说明，优先解析下载 iframe，逐个尝试其余候选页。"""
        self.last_error = ""
        try:
            url = self._ensure_url_scheme(url)
            res = self._get_with_acw_retry(url)
            page_url = getattr(res, "url", None) or url
            soup = BeautifulSoup(res.text, "html.parser")
            description = soup.select_one(".n_box_des, .n_file_des, #file-description")
            if description is None:
                label = soup.find(string=re.compile(r"文件描述[:：]"))
                if label:
                    description = BeautifulSoup("".join(str(item) for item in label.parent.next_siblings), "html.parser")
            note = ""
            if description is not None:
                for br in description.find_all("br"):
                    br.replace_with("\n")
                note = re.sub(r"^\s*文件描述[:：]\s*", "", description.get_text()).strip()
            frames = soup.find_all("iframe", src=True)
            frames.sort(key=lambda frame: "ifr2" not in frame.get("class", []))
            urls = list(dict.fromkeys(urljoin(page_url, frame["src"].strip()) for frame in frames if frame["src"].strip()))
            # 页面也可能直接声明下载请求，不再要求必须存在 iframe。
            if not urls:
                urls = [page_url]
            for frame_url in urls[:self.MAX_CANDIDATES]:
                try:
                    frame_url = self._ensure_url_scheme(frame_url)
                except ValueError as exc:
                    self.last_error = str(exc)
                    continue
                download_url = self._get_direct_link_from_ifr(frame_url, page_url)
                if download_url:
                    self.last_error = ""
                    return {"note": note, "download_url": download_url}
            return None
        except (RequestException, ValueError) as exc:
            self.last_error = f"获取蓝奏云文件详情失败：{exc}"
            return None

    def _get_direct_link_from_ifr(self, ifr_url: str, referer: str = "") -> str | None:
        try:
            res = self._get_with_acw_retry(ifr_url, headers={"Referer": referer or ifr_url})
            page_url = getattr(res, "url", None) or ifr_url
            candidates = self._extract_requests(res.text, page_url, "download")
            errors = []
            for candidate in candidates:
                try:
                    data = self._post_request([candidate], page_url, "download")
                    domain = self._ensure_url_scheme(data["dom"])
                    raw_url = self._ensure_url_scheme(domain.rstrip("/") + "/file/" + data["url"].strip().lstrip("/"))
                    return self._resolve_download_url(raw_url, page_url)
                except (RequestException, ValueError) as exc:
                    errors.append(str(exc))
            raise ValueError("; ".join(errors))
        except (RequestException, ValueError) as exc:
            self.last_error = f"解析蓝奏云下载地址失败：{exc}"
            return None

    def _resolve_download_url(self, url: str, referer: str) -> str:
        """跟随跳转并处理下载节点校验，流式探测不读取安装包正文。"""
        challenged = set()
        for _ in range(8):
            res = self.session.get(url, allow_redirects=False, stream=True, headers={"Referer": referer}, timeout=(5, 20))
            try:
                if res.status_code >= 400:
                    res.raise_for_status()
                if res.status_code in {301, 302, 303, 307, 308} and res.headers.get("Location"):
                    url = self._ensure_url_scheme(urljoin(url, res.headers["Location"]))
                    continue
                if "text/html" in res.headers.get("Content-Type", "").lower():
                    # 校验页大小受限，不能将网页误报为成功的下载地址。
                    body = bytearray()
                    for chunk in res.iter_content(4096):
                        body.extend(chunk)
                        if len(body) > 65536:
                            raise ValueError("蓝奏云下载节点返回了网页而非文件")
                    cookie = self._extract_acw_cookie(body.decode("utf-8", errors="replace"))
                    host = urlparse(url).hostname
                    if not cookie or host in challenged:
                        raise ValueError("蓝奏云下载节点校验未通过")
                    challenged.add(host)
                    self.session.cookies.set("acw_sc__v2", cookie, domain=host, path="/")
                    continue
                if res.status_code not in {200, 206}:
                    raise ValueError(f"蓝奏云下载节点返回了异常状态：{res.status_code}")
                return url
            finally:
                res.close()
        raise ValueError("蓝奏云下载跳转次数过多")
