import http.server
import socketserver
import threading
import os
import socket

class AssetServer:
    '''简单的本地静态文件服务器，用于提供缩略图等资源访问。'''
    def __init__(self):
        self.port = self.find_free_port()
        self.root_dir = os.path.join(os.getcwd(), 'cache') # 根目录设为 cache
        
        # 创建处理器
        handler = lambda *args: http.server.SimpleHTTPRequestHandler(*args, directory=self.root_dir)
        self.httpd = socketserver.TCPServer(("localhost", self.port), handler)
        
        # 后台运行
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        print(f"Asset server started at http://localhost:{self.port}")

    def find_free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    def get_url(self, filename):
        """获取某个文件的访问 URL"""
        return f"http://localhost:{self.port}/thumbnails/{filename}"