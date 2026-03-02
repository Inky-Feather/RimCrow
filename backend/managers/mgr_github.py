# backend/managers/mgr_github.py
import requests
import re
import os
import zipfile
import shutil
import time
from backend.utils.logger import logger
from backend.settings import DATA_DIR, settings
from backend.database.models import GithubModRecord, GithubTimeline, db
from backend.managers.mgr_download import TaskStatus
from backend.utils.tools import current_ms

class GithubManager:
    API_BASE = "https://api.github.com/repos"

    def __init__(self, download_mgr):
        self.download_mgr = download_mgr

    def parse_repo_url(self, url: str):
        """解析 GitHub URL 提取 owner 和 repo"""
        match = re.search(r"github\.com/([^/]+)/([^/]+)", url)
        if not match: return None, None
        owner = match.group(1)
        repo = match.group(2).replace(".git", "")
        return owner, repo

    def fetch_repo_info(self, url: str):
        """获取仓库基础信息、默认分支以及最新 Release 信息"""
        owner, repo = self.parse_repo_url(url)
        if not owner: return {"error": "无效的 GitHub 链接"}
        try:
            # 1. 获取基础信息 (包含默认分支)
            repo_res = requests.get(f"{self.API_BASE}/{owner}/{repo}", timeout=10).json()
            if "message" in repo_res and repo_res["message"] == "Not Found":
                return {"error": "找不到该仓库"}
                
            default_branch = repo_res.get("default_branch", "main")
            
            # 2. 获取最新 Release
            release_res = requests.get(f"{self.API_BASE}/{owner}/{repo}/releases/latest", timeout=5)
            has_release = release_res.status_code == 200
            release_info = release_res.json() if has_release else {}
            return {
                "owner": owner,
                "repo": repo,
                "default_branch": default_branch,
                "has_release": has_release,
                "latest_release_tag": release_info.get("tag_name"),
                "latest_release_name": release_info.get("name"),
                "release_zip_url": release_info.get("zipball_url") # Github提供的源码打包ZIP
            }
        except Exception as e:
            return {"error": str(e)}

    def record_timeline(self, repo_url: str, action: str, message: str):
        """主动记录操作轨迹"""
        with db.atomic():
            GithubTimeline.create(repo_url=repo_url, action=action, message=message)

    def trigger_download(self, repo_url: str, install_type: str = "source", target_version: str = ""):
        """发起下载并绑定解压钩子"""
        owner, repo = self.parse_repo_url(repo_url)
        if not owner: return False
        if not repo: return False
        download_url = ""
        filename = ""
        if install_type == "release":
            download_url = f"https://github.com/{owner}/{repo}/archive/refs/tags/{target_version}.zip"
            filename = f"{repo}_{target_version}.zip"
        else:
            # 默认 Source 模式 (下载分支最新代码)
            branch = target_version or "main"
            download_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"
            filename = f"{repo}_{branch}_source.zip"

        # 记录下载开始
        self.record_timeline(repo_url, "download", f"开始获取压缩包: {filename}")

        # 设置下载完成的回调闭包
        def on_download_complete(task):
            self._handle_extraction(task.dest_path, repo_url, repo, install_type, target_version)

        def on_download_error(task):
            self.record_timeline(repo_url, "error", f"下载失败: {task.error_msg}")

        # 推入全局下载队列 (下载到 data/Downloads)
        dl_dir = str(DATA_DIR / "Downloads")
        task_id = self.download_mgr.add_task(
            url=download_url,
            dest_dir=dl_dir,
            filename=filename,
            on_complete=on_download_complete,
            on_error=on_download_error
        )
        return task_id

    def _handle_extraction(self, zip_path: str, repo_url: str, repo_name: str, install_type: str, version: str):
        """智能解压与寻址逻辑"""
        self.record_timeline(repo_url, "extract", "压缩包获取成功，正在解压...")
        temp_extract_dir = zip_path + "_extracted"
        self_mods_dir = settings.config.self_mods_path
        try:
            # 1. 解压到临时目录
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_extract_dir)
            # 2. 智能深潜：寻找包含 About/About.xml 的真实根目录
            mod_root_path = None
            for root, dirs, files in os.walk(temp_extract_dir):
                if "About" in dirs:
                    about_xml = os.path.join(root, "About", "About.xml")
                    if os.path.exists(about_xml):
                        mod_root_path = root
                        break
            if not mod_root_path:
                raise Exception("未能在压缩包中找到合法的 Mod 结构 (缺少 About.xml)")
            # 3. 移动到管理器 Mod 目录
            # 命名规则：_Github_RepoName
            final_folder_name = f"_GH_{repo_name}"
            target_path = os.path.join(self_mods_dir, final_folder_name)
            # 如果存在旧版本，先删除
            if os.path.exists(target_path):
                shutil.rmtree(target_path)
            # 移动文件
            shutil.move(mod_root_path, target_path)
            # 4. 更新数据库记录
            with db.atomic():
                record = GithubModRecord.get_or_none(repo_url=repo_url)
                if record:
                    record.installed_version = version
                    record.local_folder = final_folder_name
                    record.last_update_time = current_ms()
                    record.save()
            self.record_timeline(repo_url, "success", f"部署成功！已安装版本: {version}")
        except Exception as e:
            logger.error(f"GitHub解压部署失败: {e}")
            self.record_timeline(repo_url, "error", f"部署失败: {str(e)}")
        finally:
            # 清理临时文件和压缩包
            if os.path.exists(temp_extract_dir):
                shutil.rmtree(temp_extract_dir)
            if os.path.exists(zip_path):
                os.remove(zip_path)
    