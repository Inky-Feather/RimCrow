# backend/managers/mgr_network.py
import os
import socket
import atexit
import platform
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from backend.settings import settings
from backend.utils.logger import logger

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 RimCrow"

class NetworkManager:
    def __init__(self):
        # 保存原始的 getaddrinfo，防止重复 patch 导致死循环
        self._original_getaddrinfo = socket.getaddrinfo
        self._is_socket_patched = False
        
        # 定义系统 Hosts 文件路径
        if platform.system() == "Windows":
            self.sys_hosts_path = r"C:\Windows\System32\drivers\etc\hosts"
        else:
            self.sys_hosts_path = "/etc/hosts"
            
        self.marker_start = "# --- RimCrow Hosts Start ---\n"
        self.marker_end = "# --- RimCrow Hosts End ---\n"

        # 注册退出时的清理函数
        atexit.register(self.restore_system_hosts)

        # 首次初始化
        self.apply()

    def apply(self):
        """
        供外部调用的刷新方法。
        当在 UI 或代码中修改了 settings 后，调用此方法即可立即生效。
        """
        self.apply_proxy_settings()
        
        cfg = settings.config.network
        # 假设 settings 里加了一个开关：是否写入系统 hosts
        if getattr(cfg, 'write_to_system_hosts', False):
            success = self.write_to_system_hosts()
            if not success:
                # 如果没权限写入系统，降级使用 Python 层的 Socket 劫持
                self.patch_socket_for_hosts()
        else:
            self.restore_system_hosts() # 清理可能残留的系统 Hosts
            self.patch_socket_for_hosts()

    def apply_proxy_settings(self):
        """应用代理设置到环境变量（支持动态覆盖）"""
        cfg = settings.config.network.proxy
        
        if cfg.enabled and cfg.host and cfg.port:
            auth = f"{cfg.username}:{cfg.password}@" if getattr(cfg, 'username', None) else ""
            proxy_url = f"{cfg.type}://{auth}{cfg.host}:{cfg.port}"
            os.environ['HTTP_PROXY'] = proxy_url
            os.environ['HTTPS_PROXY'] = proxy_url
            if getattr(cfg, 'bypass_list', None):
                os.environ['NO_PROXY'] = ",".join(cfg.bypass_list)
        else:
            os.environ.pop('HTTP_PROXY', None)
            os.environ.pop('HTTPS_PROXY', None)
            os.environ.pop('NO_PROXY', None)
    
    def get_proxy_url(self) -> str:
        """获取当前的代理 URL 字符串"""
        cfg = settings.config.network.proxy
        if cfg.enabled and cfg.host and cfg.port:
            auth = f"{cfg.username}:{cfg.password}@" if cfg.username else ""
            return f"{cfg.type}://{auth}{cfg.host}:{cfg.port}"
        return ""

    def get_proxy_env(self) -> dict:
        """获取用于 subprocess 的代理环境变量字典"""
        proxy_url = self.get_proxy_url()
        if not proxy_url: return {}
        env = {
            "HTTP_PROXY": proxy_url,
            "HTTPS_PROXY": proxy_url,
            "ALL_PROXY": proxy_url, # SteamCMD 有时也看这个
        }
        # 注入绕过列表
        if settings.config.network.proxy.bypass_list:
            env["NO_PROXY"] = ",".join(settings.config.network.proxy.bypass_list)
        return env

    # ====================== Hosts 配置 =======================
    def patch_socket_for_hosts(self):
        """Python 运行时 Socket 劫持（动态读取最新配置，无死循环风险）"""
        if self._is_socket_patched: return  # 已经劫持过了，不需要重新包一层

        def new_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            # 【关键修改】：每次发请求时，实时去 settings 里面拿最新的 hosts 配置
            current_hosts_map = settings.config.network.hosts
            if current_hosts_map and host in current_hosts_map:
                target_ip = current_hosts_map[host]
                return self._original_getaddrinfo(target_ip, port, family, type, proto, flags)
            
            return self._original_getaddrinfo(host, port, family, type, proto, flags)

        socket.getaddrinfo = new_getaddrinfo
        self._is_socket_patched = True

    # ---------------- 系统 Hosts 修改逻辑 ---------------
    def write_to_system_hosts(self) -> bool:
        """将 Hosts 写入操作系统。返回 True 表示成功，False 表示无权限"""
        hosts_map = settings.config.network.hosts
        if not hosts_map:
            self.restore_system_hosts()
            return True
        # 构建要写入的文本块
        block_lines = [self.marker_start]
        for domain, ip in hosts_map.items():
            block_lines.append(f"{ip}\t{domain}\n")
        block_lines.append(self.marker_end)
        custom_block = "".join(block_lines)
        try:
            # 1. 先读取现有内容
            with open(self.sys_hosts_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            # 2. 清理掉旧的的标记块
            content = self._remove_custom_block(content)
            # 3. 加上新的标记块（确保换行）
            if not content.endswith('\n'):
                content += '\n'
            content += custom_block
            # 4. 写回文件
            with open(self.sys_hosts_path, 'w', encoding='utf-8', errors='ignore') as f:
                f.write(content)
            return True

        except PermissionError:
            logger.warning("[警告] 无法写入系统 Hosts，请以管理员身份运行。已降级为内部劫持。")
            return False
        except Exception as e:
            logger.error(f"[错误] 修改系统 Hosts 失败: {e}")
            return False

    def restore_system_hosts(self):
        """恢复系统 Hosts（退出时自动调用）"""
        try:
            with open(self.sys_hosts_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            if self.marker_start in content:
                clean_content = self._remove_custom_block(content)
                with open(self.sys_hosts_path, 'w', encoding='utf-8', errors='ignore') as f:
                    f.write(clean_content)
        except PermissionError:
            pass # 没权限就算了，说明一开始也没写进去
        except FileNotFoundError:
            pass

    def _remove_custom_block(self, content: str) -> str:
        """从字符串中安全移除被 Marker 包裹的区域"""
        markers = (
            (self.marker_start, self.marker_end),
            ("# --- RimModManager Hosts Start ---\n", "# --- RimModManager Hosts End ---\n"),
        )
        for marker_start, marker_end in markers:
            start_idx = content.find(marker_start)
            end_idx = content.find(marker_end)
            if start_idx != -1 and end_idx != -1:
                end_idx += len(marker_end)
                content = content[:start_idx] + content[end_idx:]
        return content


def build_retry_session(*, total: int = 3, connect: int = 3, read: int = 3, redirect: int = 5, 
    backoff_factor: float = 1.0, status_forcelist: tuple[int, ...] = (429, 500, 502, 503, 504), 
    allowed_methods: tuple[str, ...] = ("GET", "HEAD"), pool_connections: int = 8, pool_maxsize: int = 8) -> requests.Session:
    
    session = requests.Session()
    retry = Retry(
        total=total,
        connect=connect,
        read=read,
        redirect=redirect,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=frozenset(allowed_methods),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=pool_connections, pool_maxsize=pool_maxsize)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def merge_headers(headers: dict[str, str] | None = None, *, user_agent: str = DEFAULT_USER_AGENT) -> dict[str, str]:
    merged = {"User-Agent": user_agent}
    if headers: merged.update(headers)
    return merged


# 实例化单例
network_mgr = NetworkManager()
