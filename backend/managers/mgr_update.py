import shutil
import sys
import os
import subprocess
from dataclasses import dataclass
from typing import Optional, List
from abc import ABC, abstractmethod
import zipfile
from packaging import version
from backend._version import __version__
from backend.utils.lanzou_parser import LanzouParser
from backend.utils.logger import logger

@dataclass
class UpdateInfo:
    has_update: bool
    version: str
    changelog: str
    download_url: str
    source_name: str  # "Lanzou", "GitHub", etc.
    file_size: Optional[str] = None
    publish_time: Optional[str] = None
    
class UpdateSource(ABC):
    @abstractmethod
    def check(self) -> Optional[UpdateInfo]:
        pass

# --- 蓝奏云源实现 ---
class LanzouSource(UpdateSource):
    def __init__(self, folder_url: str, password: str = ""):
        self.url = folder_url
        self.pwd = password
        self.parser = LanzouParser()

    def check(self):
        data = self.parser.get_all_files(self.url, self.pwd)
        if not data or 'latest' not in data:
            return None
        
        latest = data['latest']
        remote_v = latest['version']
        has_new = version.parse(remote_v) > version.parse(__version__)
        
        return UpdateInfo(
            has_update=has_new,
            version=remote_v,
            changelog=latest.get('note', "无更新日志"),
            download_url=latest.get('download_url', ""),
            source_name="蓝奏云",
            file_size=latest.get('size'),
            publish_time=latest.get('time')
        )

# --- GitHub 源实现 (预留) ---
class GithubSource(UpdateSource):
    def __init__(self, repo: str):
        self.api_url = f"https://api.github.com/repos/{repo}/releases/latest"

    def check(self):
        # import requests
        # try:
        #     res = requests.get(self.api_url, timeout=5).json()
        #     remote_v = res['tag_name'].replace('v', '')
        #     return UpdateInfo(...)
        # except: return None
        return None

# --- 更新总管 ---
class UpdateManager:
    def __init__(self):
        self.sources: List[UpdateSource] = [
            # 优先级：蓝奏云优先（国内快），GitHub 兜底
            LanzouSource("https://wwbns.lanzouu.com/b00mq4tqgf", "aite"), 
            GithubSource("YourName/RimModManager")
        ]

    def check_all(self) -> UpdateInfo:
        """遍历所有源，直到找到一个有效的返回结果"""
        for src in self.sources:
            try:
                info = src.check()
                if info: return info
            except Exception as e:
                logger.error(f"Update Source {src.__class__.__name__} failed: {e}")
                continue
        
        return UpdateInfo(False, __version__, "", "", "None")

    def execute_hot_swap(self, temp_zip_path):
        # 1. 获取物理路径
        # 注意：单文件模式下 sys.executable 是真正的 .exe 路径
        current_exe = os.path.abspath(sys.executable)
        exe_name = os.path.basename(current_exe)
        install_root = os.path.dirname(current_exe)
        
        # 2. 准备解压目录
        extract_path = os.path.join(install_root, "update_tmp_dir")
        if os.path.exists(extract_path):
            shutil.rmtree(extract_path, ignore_errors=True)
        os.makedirs(extract_path, exist_ok=True)

        try:
            # 3. 解决解压乱码问题
            with zipfile.ZipFile(temp_zip_path, 'r') as zf:
                for member in zf.infolist():
                    # 关键：手动处理编码转换
                    try:
                        # 尝试将文件名从 cp437 转回原始字节，再按 gbk 解码
                        filename = member.filename.encode('cp437').decode('gbk')
                    except:
                        filename = member.filename # 兜底使用原始
                    
                    # 构造目标路径
                    target_path = os.path.join(extract_path, filename)
                    
                    # 如果是目录
                    if member.is_dir():
                        os.makedirs(target_path, exist_ok=True)
                    else:
                        # 确保父目录存在
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        with zf.open(member) as source, open(target_path, "wb") as target:
                            shutil.copyfileobj(source, target)

            # 4. 定位新版本 Payload
            payload_dir = None
            for root, dirs, files in os.walk(extract_path):
                if exe_name in files:
                    payload_dir = root
                    break
            
            if not payload_dir:
                return False

            # 5. 生成高兼容性批处理
            bat_path = os.path.join(install_root, "_finish_update.bat")
            
            # 【核心修改点】:
            # 1. chcp 65001 -> 处理 UTF-8 (Python 写入的文件)
            # 2. set "_MEIPASS=" -> 极其重要！清除单文件模式的临时路径变量，防止 DLL 加载错误
            # 3. taskkill -> 确保进程彻底杀掉
            bat_content = f"""@echo off
chcp 65001 > nul
setlocal
title RimFlow Updater

echo 正在关闭旧进程...
taskkill /f /im "{exe_name}" >nul 2>&1
timeout /t 2 /nobreak > nul

:retry_move
echo 正在替换文件...
:: 使用 robocopy 替换
robocopy "{payload_dir}" "{install_root}" /E /IS /IT /MOVE /R:5 /W:2 /XF "{os.path.basename(bat_path)}"

if %ERRORLEVEL% GEQ 8 (
    echo 替换失败，请确保程序已关闭。
    timeout /t 3
    goto retry_move
)

echo 更新成功，正在清理环境并重启...

:: 【关键】清除 PyInstaller 环境残留，防止 DLL 找不到
set _MEIPASS=
set _MEIPASS2=
set PYI_EXPLODE_PATH=

:: 重启。使用 /d 指定工作目录，且不带环境变量启动
start "" /d "{install_root}" "{exe_name}"

:: 清理并自删
rd /s /q "{extract_path}"
del "{temp_zip_path}"
(goto) 2>nul & del "%~f0"
exit
"""
            # 写入批处理（注意编码）
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat_content)
            
            # 6. 运行脚本
            subprocess.Popen(
                ["cmd.exe", "/c", bat_path],
                cwd=install_root,
                shell=True,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            
            # 立即彻底结束 Python 进程
            os._exit(0)

        except Exception as e:
            print(f"Update failed: {e}")
            return False
