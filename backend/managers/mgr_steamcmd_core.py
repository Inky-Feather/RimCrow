import os
import subprocess
import time
import re
import signal
from pathlib import Path
from backend.utils.logger import logger
from backend.settings import settings

class SteamCMDController:
    def __init__(self, steamcmd_exe_path: str):
        self.steamcmd_exe = str(Path(steamcmd_exe_path))
        self.steamcmd_dir = str(Path(steamcmd_exe_path).parent)
        self.current_process = None
        
        # 匹配进度的正则：例如 "[  0%] Checking for available update..."
        self.progress_pattern = re.compile(r'\[\s*(\d+)%\]')

    def _get_clean_env(self):
        """
        获取干净的环境变量（极其重要）
        解决 HTTPS 证书报错的核心：在初始化阶段屏蔽所有的网络代理变量
        """
        env = os.environ.copy()
        
        # 除非你在设置里明确指定让 SteamCMD 走代理，否则强行剔除代理环境变量
        # （注意：建议在首次初始化时，即使设置了代理也强制设为 False，初始化完再开启）
        if not settings.config.network.use_proxy_on_steamcmd:
            env.pop('HTTP_PROXY', None)
            env.pop('HTTPS_PROXY', None)
            env.pop('http_proxy', None)
            env.pop('https_proxy', None)
            env.pop('ALL_PROXY', None)
            env.pop('all_proxy', None)
            
        return env

    def initialize_steamcmd(self, on_progress=None):
        """
        执行初始化：只运行 steamcmd.exe +quit 让它自己下载依赖
        """
        logger.info("开始执行 SteamCMD 初始化部署...")
        
        # 修复残留：如果之前崩溃过，可能残留了损坏的文件，除了 exe 全删掉能解决 90% 的疑难杂症
        self._clean_corrupted_init()

        cmd = [self.steamcmd_exe, '+quit']
        
        return self._run_and_monitor(
            cmd=cmd, 
            task_name="初始化", 
            on_progress=on_progress,
            timeout=300 # 初始化下载可能需要几分钟
        )

    def _clean_corrupted_init(self):
        """清理失败的初始化残留文件 (仅保留 steamcmd.exe)"""
        if not Path(self.steamcmd_exe).exists(): return
            
        for item in Path(self.steamcmd_dir).iterdir():
            if item.name.lower() != 'steamcmd.exe':
                try:
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        import shutil
                        shutil.rmtree(item)
                except Exception as e:
                    logger.warning(f"清理残留文件失败 {item.name}: {e}")

    def _run_and_monitor(self, cmd: list, task_name: str, on_progress=None, timeout=300):
        """
        核心运行器：实时读取输出、处理阻塞、防卡死
        """
        # 调试模式下强制给 SteamCMD 新建一个独立控制台窗口，便于直接观察真实输出。
        # 非调试模式仍然保持后台静默运行，并通过管道解析进度。
        debug_show_console = os.name == 'nt' and bool(settings.config.debug_mode)
        startupinfo = None
        creationflags = 0
        if os.name == 'nt':
            if debug_show_console:
                creationflags = subprocess.CREATE_NEW_CONSOLE
            else:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        try:
            # 启动进程，必须指定 cwd 为 steamcmd 所在目录
            self.current_process = subprocess.Popen(
                cmd,
                cwd=str(self.steamcmd_dir),
                env=self._get_clean_env(),
                stdout=None if debug_show_console else subprocess.PIPE,
                stderr=None if debug_show_console else subprocess.STDOUT, # 调试模式下直接把输出留在新控制台窗口
                stdin=None if debug_show_console else subprocess.PIPE,    # 非调试模式保留 stdin 防止 SteamCMD 等待用户输入卡死
                startupinfo=startupinfo,
                creationflags=creationflags,
                text=True,
                encoding='utf-8',         # SteamCMD 有时会有乱码
                errors='replace'
            )
            
            logger.info(f"SteamCMD 进程已启动 PID: {self.current_process.pid}")
            
            start_time = time.time()

            if debug_show_console:
                while self.current_process.poll() is None:
                    if time.time() - start_time > timeout:
                        logger.error(f"SteamCMD {task_name} 超时被强制终止")
                        self.kill_all()
                        return False, "执行超时"
                    time.sleep(0.2)
                return self.current_process.returncode == 0, "执行完成"
            
            # 实时读取输出
            for line in iter(self.current_process.stdout.readline, ''): # type: ignore
                line = line.strip()
                if not line:
                    continue
                    
                # 1. 检测是否卡死超时
                if time.time() - start_time > timeout:
                    logger.error(f"SteamCMD {task_name} 超时被强制终止")
                    self.kill_all()
                    return False, "执行超时"

                # 2. 忽略无关紧要的报错（比如多语言文件缺失）
                if "ILocalize::AddFile() failed" in line:
                    continue

                # 3. 捕捉致命的 HTTPS 报错
                if "Can't use HTTPS because steamcommon" in line:
                    logger.error(f"拦截到致命错误: {line}")
                    self.kill_all()
                    return False, "网络/代理配置导致初始化失败(缺少SSL组件)"

                # 4. 解析进度并推给前端
                match = self.progress_pattern.search(line)
                if match and on_progress:
                    percent = int(match.group(1))
                    on_progress(percent, line)
                else:
                    # 打印关键日志
                    if "Error" in line or "Failed" in line:
                        logger.warning(f"[SteamCMD] 输出警告：{line}")
                    else:
                        logger.debug(f"[SteamCMD] 输出：{line}")

            # 等待进程正常结束
            self.current_process.wait()
            return self.current_process.returncode == 0, "执行完成"

        except Exception as e:
            logger.error(f"SteamCMD 执行异常: {e}", exc_info=True)
            self.kill_all()
            return False, str(e)
        finally:
            self.current_process = None

    # ==========================================
    # 强制关闭进程树 (Kill Switch)
    # ==========================================
    def kill_all(self):
        """
        彻底杀死 SteamCMD 及其衍生的所有子进程 (如 steamerrorreporter.exe)
        """
        if not self.current_process: return

        pid = self.current_process.pid
        logger.warning(f"准备强制击杀 SteamCMD 进程树 PID: {pid}")
        
        try:
            if os.name == 'nt':
                # Windows: 使用 taskkill /T (杀进程树) /F (强制)
                subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(pid)], 
                    capture_output=True, 
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                # Linux/Mac: 使用 os.killpg 杀进程组
                import signal
                os.killpg(os.getpgid(pid), signal.SIGTERM)
        except Exception as e:
            logger.error(f"强制击杀 SteamCMD 失败: {e}")
        finally:
            self.current_process = None
