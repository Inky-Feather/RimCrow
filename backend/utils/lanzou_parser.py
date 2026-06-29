import requests
import re
from packaging import version
from urllib.parse import urljoin, urlparse

# --- 模块测试准备 ---
if __name__ == "__main__":
    import sys
    from pathlib import Path
    # Path(__file__).resolve() 获取当前文件的绝对路径
    # .parents[2] 表示向上跳 3 级 (文件->scanner->backend->项目根目录)
    project_root = Path(__file__).resolve().parents[2]
    # 调试打印，确保路径正确
    print(f"Project Root: {project_root}")
    # sys.path 需要字符串类型，所以要用 str() 转换一下
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from backend.utils.tools import get_package_platform_match, get_current_package_platform_keywords, has_supported_update_package_name

class LanzouParser:
    UPDATE_FILENAME_PATTERN = re.compile(r"(?<!\d)v?(\d+\.\d+\.\d+)(?!\d)", re.I)
    ACW_ARG_ORDER = [0xf, 0x23, 0x1d, 0x18, 0x21, 0x10, 0x1, 0x26, 0xa, 0x9, 0x13, 0x1f, 0x28, 0x1b, 0x16, 0x17, 0x19, 0xd, 0x6, 0xb, 0x27, 0x12, 0x14, 0x8, 0xe, 0x15, 0x20, 0x1a, 0x2, 0x1e, 0x7, 0x4, 0x11, 0x5, 0x3, 0x1c, 0x22, 0x25, 0xc, 0x24]
    ACW_KEY = "3000176000856006061501533003690027800375"

    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False  # 禁用环境变量代理
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'X-Requested-With': 'XMLHttpRequest',
        })
        self.last_error = ""

    def log_step(self, step, msg):
        print(f"[Lanzou] {step} >> {msg}")

    def _get_with_acw_retry(self, url, **kwargs):
        res = self.session.get(url, **kwargs)
        cookie_value = self._extract_acw_cookie(res.text)
        if not cookie_value:
            return res
        domain = urlparse(url).hostname
        cookie_kwargs = {"path": "/"}
        if domain:
            cookie_kwargs["domain"] = domain
        self.session.cookies.set("acw_sc__v2", cookie_value, **cookie_kwargs)
        self.log_step("ACW", "蓝奏云要求浏览器校验，已计算校验 Cookie 后重试")
        return self.session.get(url, **kwargs)

    @classmethod
    def _extract_acw_cookie(cls, html):
        if "acw_sc__v2" not in str(html or ""):
            return ""
        match = re.search(r"var\s+arg1\s*=\s*'([0-9a-fA-F]{40})'", html)
        if not match:
            return ""
        arg1 = match.group(1)
        reordered = [""] * len(cls.ACW_ARG_ORDER)
        for idx, order in enumerate(cls.ACW_ARG_ORDER):
            reordered[idx] = arg1[order - 1]
        mixed = "".join(reordered)
        result = []
        for idx in range(0, min(len(mixed), len(cls.ACW_KEY)), 2):
            value = int(mixed[idx:idx + 2], 16) ^ int(cls.ACW_KEY[idx:idx + 2], 16)
            result.append(f"{value:02x}")
        return "".join(result)

    @staticmethod
    def _ensure_url_scheme(url):
        text = str(url or "").strip()
        if not text:
            return ""
        if text.startswith("//"):
            return f"https:{text}"
        if not urlparse(text).scheme:
            return f"https://{text.lstrip('/')}"
        return text

    def get_all_files(self, folder_url, password=""):
        """
        获取文件夹内所有文件及其版本信息
        返回格式: { "files": [...], "latest": { ... } }
        """
        try:
            self.log_step("INIT", f"正在检索文件夹列表: {folder_url}")
            domain = folder_url.split('/')[2]
            res = self._get_with_acw_retry(folder_url)
            html = res.text

            # 1. 提取文件夹权限参数
            fid = re.search(r"'fid':(\d+)", html)
            if not fid:
                self.last_error = "无法提取文件夹ID"
                return None
            fid = fid.group(1)
            data_block = re.search(r"data\s*:\s*\{([^}]+)\}", html)
            if not data_block:
                self.last_error = "无法提取数据块"
                return None
            data_block = data_block.group(1)
            t_var = re.search(r"'t':\s*([\w]+)", data_block)
            if not t_var:
                self.last_error = "无法提取 t_var"
                return None
            t_var = t_var.group(1)
            k_var = re.search(r"'k':\s*([\w]+)", data_block)
            if not k_var:
                self.last_error = "无法提取 k_var"
                return None
            k_var = k_var.group(1)
            t_val = re.search(rf"var\s+{t_var}\s*=\s*'([^']+)'", html)
            if not t_val:
                self.last_error = "无法提取 t_val"
                return None
            t_val = t_val.group(1)
            k_val = re.search(rf"var\s+{k_var}\s*=\s*'([^']+)'", html)
            if not k_val:
                self.last_error = "无法提取 k_val"
                return None
            k_val = k_val.group(1)

            # 2. 获取原始文件列表
            ajax_url = f"https://{domain}/filemoreajax.php"
            post_data = {'lx': 2, 'fid': fid, 'pg': 1, 'rep': 0, 'up': 1, 'ls': 1, 't': t_val, 'k': k_val, 'pwd': password}
            res_list = self.session.post(ajax_url, data=post_data)
            list_json = res_list.json()

            if list_json.get('zt') != 1:
                self.last_error = f"蓝奏云返回错误: {list_json.get('info')}"
                return None

            # 3. 处理并格式化文件列表
            all_files = []
            for f in list_json['text']:
                all_files.append(self._build_file_info(f))

            if not all_files:
                self.last_error = "文件夹内无文件"
                return None

            # 4. 识别当前系统可用的最新版本。新版包名带系统标识，旧版包名不带系统标识，两者都兼容。
            all_files.sort(key=self._file_sort_key, reverse=True)
            latest_file = self._select_latest_update_file(all_files)
            if not latest_file:
                self.last_error = "未找到适合当前系统的更新包"
                return {"files": all_files, "latest": None}

            # 5. 对最新版进行“深度解析”获取直链和更新日志
            self.log_step("LATEST", f"发现最新版本: v{latest_file['version']}，正在解析详情...")
            depth_info = self.get_file(f"https://{domain}/{latest_file['id']}")
            
            if depth_info:
                latest_file.update(depth_info)
                self.log_step("LATEST", f"最新版本描述: {depth_info['note']}")
                self.log_step("LATEST", f"最新版本下载直链: {depth_info['download_url']}")
            else:
                self.log_step("LATEST", f"最新版本详情解析失败: {self.last_error}")
                
            return {
                "files": all_files,
                "latest": latest_file
            }

        except Exception as e:
            self.last_error = f"获取版本列表失败: {str(e)}"
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

    def get_file(self, url):
        """
        深度解析：访问文件详情页，获取 fid、Changelog 并换取直链
        return: {
            'note': str,  # 文件描述 (Changelog)
            'download_url': str  # 下载直链
        }
        """
        try:
            domain = url.split('/')[2]
            res = self._get_with_acw_retry(url)
            html = res.text

            # 提取文件描述 (Changelog)
            desc_match = re.search(r'class="p7">文件描述：</span><br>\s*(.*?)\s*</td>', html, re.S)
            note = desc_match.group(1).replace('<br>', '\n').strip() if desc_match else ""

            # 提取跳转参数 fid
            fid_match = re.search(r'var\s+fid\s*=\s*(\d+);', html)
            fid = fid_match.group(1) if fid_match else ""

            # 提取 iframe 引导页路径
            ifr_path = re.search(r'src="(/fn\?[^"]+)"', html)
            if not ifr_path:
                self.last_error = "无法提取 iframe 引导页路径"
                return None
            ifr_path = ifr_path.group(1)
            ifr_url = f"https://{domain}{ifr_path}"
            
            # 获取下载直链
            download_url = self._get_direct_link_from_ifr(ifr_url, fid)
            if not download_url:
                self.last_error = "无法获取下载直链"
                return None

            return {
                'note': note,
                'download_url': download_url
            }
        except Exception as e:
            self.log_step("ERROR", f"深度解析详情页异常: {e}")
            return None

    def _get_direct_link_from_ifr(self, ifr_url, fid):
        """增强版直链换取逻辑"""
        try:
            domain = ifr_url.split('/')[2]
            # 必须带上 Referer，模仿用户从详情页点击
            res = self._get_with_acw_retry(ifr_url, headers={'Referer': f"https://{domain}/{fid}"})
            html = res.text

            # 1. 提取所有变量 (更加宽泛的匹配)
            js_vars = {}
            for n, v in re.findall(r"var\s+([\w]+)\s*=\s*'([^']*)'", html):
                js_vars[n] = v
            for n, v in re.findall(r"var\s+([\w]+)\s*=\s*(\d+)", html):
                js_vars[n] = v

            data_match = re.search(r"data\s*:\s*\{([^}]+)\}", html, re.S)
            if not data_match:
                return None
            data_content = data_match.group(1)
            
            def find_val(key):
                # 匹配 'sign': varname 或 sign: varname
                m = re.search(rf"['\"]?{key}['\"]?\s*:\s*([\w]+)", data_content)
                return js_vars.get(m.group(1), "") if m else ""

            # 2. 构造加密参数 (蓝奏云经常变动参数名，这里做兼容)
            sign = find_val('sign')
            ajaxdata = find_val('websignkey') or find_val('signs') or find_val('websign')
            kdns = find_val('kd') or 1

            post_url = f"https://{domain}/ajaxm.php?file={fid}"
            payload = {
                'action': 'downprocess',
                'websignkey': ajaxdata, 
                'signs': ajaxdata, # 兼容
                'sign': sign, 
                'websign': '', 
                'kd': kdns, 
                'ves': 1
            }

            # 3. 核心修正：模拟浏览器的高级请求头
            headers = {
                'Referer': ifr_url,
                'Origin': f'https://{domain}',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json, text/javascript, */*',
            }

            res_final = self.session.post(post_url, data=payload, headers=headers)
            res_json = res_final.json()

            if res_json.get('zt') == 1:
                # 此时 res_json['dom'] 可能已经是 zip1.webgetstore.com 这种
                raw_url = self._ensure_url_scheme(f"{res_json['dom']}/file/{res_json['url']}")
                
                # 4. 重要：不要用 HEAD，改用 GET 配合 allow_redirects=False
                # 这样可以精准拿到 302 的 Location 头部，且不会被 CDN 拦截
                try:
                    # 模拟真实点击跳转
                    r = self.session.get(raw_url, allow_redirects=False, headers={'Referer': ifr_url})
                    if r.status_code == 302:
                        return urljoin(raw_url, r.headers.get('Location') or "")
                    return raw_url # 如果没重定向，这本身就是直链
                except Exception:
                    return raw_url
            
            return None
        except Exception as e:
            self.log_step("ERROR", f"直链解析出错: {e}")
            return None

# --- 测试运行 ---
if __name__ == "__main__":
    lp = LanzouParser()
    data = lp.get_all_files("https://wwbns.lanzouu.com/b00mq4tqgf", "aite")
    
    if data:
        print("\n" + "="*50)
        print(f"文件夹内共有 {len(data['files'])} 个文件")
        print(data)
        print(f"最新版本: v{data['latest']['version']}")
        print(f"更新日志: {data['latest']['note']}")
        print(f"最新下载直链: {data['latest']['download_url']}")
        print("="*50)
        
        print("\n历史版本列表:")
        for f in data['files']:
            print(f"- {f['filename']} ({f['size']}) | 发布于: {f['time']}")
    else:
        print(f"错误: {lp.last_error}")
