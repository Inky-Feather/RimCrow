# backend/managers/mgr_network.py
import os
import socket
from backend.settings import settings

class NetworkManager:
    def __init__(self):
        self.apply_proxy_settings()
        self.patch_socket_for_hosts()

    def apply_proxy_settings(self):
        """应用代理设置到环境变量"""
        cfg = settings.config.network.proxy
        
        if cfg.enabled and cfg.host and cfg.port:
            auth = f"{cfg.username}:{cfg.password}@" if cfg.username else ""
            proxy_url = f"{cfg.type}://{auth}{cfg.host}:{cfg.port}"
            
            os.environ['HTTP_PROXY'] = proxy_url
            os.environ['HTTPS_PROXY'] = proxy_url
            
            # 处理 bypass (requests 库识别 NO_PROXY)
            # 格式: "google.com, .example.com"
            if cfg.bypass_list:
                os.environ['NO_PROXY'] = ",".join(cfg.bypass_list)
        else:
            # 清除代理
            os.environ.pop('HTTP_PROXY', None)
            os.environ.pop('HTTPS_PROXY', None)
            os.environ.pop('NO_PROXY', None)

    def patch_socket_for_hosts(self):
        """
        [黑科技] 运行时修改 socket.getaddrinfo 实现自定义 Hosts。
        这会影响所有 Python 层的域名解析。
        """
        hosts_map = settings.config.network.hosts
        if not hosts_map: return

        _real_getaddrinfo = socket.getaddrinfo

        def new_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            # 如果命中 Hosts 配置，直接替换 IP
            if host in hosts_map:
                # print(f"Hosts Redirect: {host} -> {hosts_map[host]}")
                target_ip = hosts_map[host]
                return _real_getaddrinfo(target_ip, port, family, type, proto, flags)
            
            return _real_getaddrinfo(host, port, family, type, proto, flags)

        socket.getaddrinfo = new_getaddrinfo

