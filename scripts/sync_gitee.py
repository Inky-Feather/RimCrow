"""将 GitHub 的分支、标签和指定正式发行版单向同步到 Gitee。"""

import fnmatch
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


SOURCE = "Inky-Feather/RimCrow"
TARGET = "InkyXFeather/RimCrow"
GITHUB_API = f"https://api.github.com/repos/{SOURCE}"
GITEE_API = f"https://gitee.com/api/v5/repos/{TARGET}"
DEFAULT_PATTERNS = "\n".join([
    "RimCrow-{tag}-windows.zip", "RimCrow-{tag}-macos.zip",
    "RimCrow-{tag}-linux.zip", "SHA256SUMS.txt",
])


def api_request(session: requests.Session, method: str, base: str, path: str,
                allow_missing: bool = False, **kwargs: Any) -> Any:
    """不输出响应正文或带认证的 URL，避免服务端回显令牌。"""
    response = session.request(method, base + path, timeout=(15, 120), allow_redirects=False, **kwargs)
    with response:
        if allow_missing and response.status_code == 404:
            return None
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"{method} {path} 失败，HTTP {response.status_code}")
        return response.json()


def list_pages(session: requests.Session, base: str, path: str) -> list[dict[str, Any]]:
    items = []
    for page in range(1, 1001):
        batch = api_request(session, "GET", base, path, params={"page": page, "per_page": 100})
        if not isinstance(batch, list):
            raise ValueError(f"附件列表格式错误: {path}")
        items.extend(batch)
        if len(batch) < 100:
            return items
    raise RuntimeError("附件列表超过分页上限，停止同步")


def select_assets(assets: list[dict[str, Any]], tag: str, patterns: str,
                  max_bytes: int) -> list[dict[str, Any]]:
    rules = [line.strip().replace("{tag}", tag) for line in patterns.splitlines() if line.strip()]
    selected = []
    names = set()
    for asset in assets:
        name = asset.get("name", "")
        if not any(fnmatch.fnmatchcase(name, pattern) for pattern in rules):
            continue
        if not name or name in {".", ".."} or "/" in name or "\\" in name or any(ord(c) < 32 for c in name):
            raise ValueError("附件名称不是安全的文件名")
        if name in names:
            raise ValueError(f"GitHub 附件名称重复: {name}")
        size = asset.get("size")
        if not isinstance(size, int) or not 0 < size <= max_bytes:
            raise ValueError(f"附件大小无效或超过 {max_bytes} 字节: {name}")
        if asset.get("state") != "uploaded":
            raise ValueError(f"附件尚未上传完成: {name}")
        names.add(name)
        selected.append(asset)
    if not any(item["name"].endswith(".zip") for item in selected):
        raise ValueError("没有符合规则的 ZIP 安装包；请先上传附件再发布，或调整筛选规则")
    return selected


def download_hash(url: str, output: Path | None, max_bytes: int,
                  expected_size: int | None = None,
                  allowed_hosts: set[str] | None = None) -> str:
    """公开附件独立下载，不向对象存储或跳转目标发送平台认证头。"""
    parsed_url = urlparse(url)
    if parsed_url.scheme != "https" or (allowed_hosts and parsed_url.hostname not in allowed_hosts):
        raise ValueError("附件下载地址必须使用 HTTPS")
    digest = hashlib.sha256()
    size = 0
    handle = output.open("wb") if output else None
    try:
        for redirect_count in range(6):
            try:
                response = requests.get(url, stream=True, timeout=(15, 120),
                                        allow_redirects=allowed_hosts is None)
            except requests.RequestException:
                raise RuntimeError("附件下载请求失败，网络或 TLS 错误") from None
            with response:
                if response.status_code in {301, 302, 303, 307, 308} and allowed_hosts:
                    if redirect_count == 5 or not response.headers.get("Location"):
                        raise RuntimeError("附件下载重定向次数过多或缺少目标地址")
                    url = urljoin(url, response.headers["Location"])
                    parsed_url = urlparse(url)
                    if parsed_url.scheme != "https" or parsed_url.hostname not in allowed_hosts:
                        raise ValueError("附件下载重定向目标不在允许的 Gitee 域名内")
                    continue
                if response.status_code != 200:
                    raise RuntimeError(f"下载附件失败，HTTP {response.status_code}")
                for chunk in response.iter_content(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("附件实际大小超过限制")
                    digest.update(chunk)
                    if handle:
                        handle.write(chunk)
            break
        else:
            raise RuntimeError("附件下载重定向次数过多")
        if expected_size is not None and size != expected_size:
            raise ValueError("附件实际大小与 GitHub 记录不符")
        return digest.hexdigest()
    finally:
        if handle:
            handle.close()


def sync_code(directory: Path, token: str, dry_run: bool, tag: str = "",
              only_tag: bool = False) -> None:
    """强制更新源端引用，但不删除目标端独有分支和标签。"""
    askpass = directory / "askpass.sh"
    askpass.write_text(
        "#!/bin/sh\ncase \"$1\" in\n"
        f"*'https://gitee.com'*|*'https://InkyXFeather{chr(64)}gitee.com'*) ;;\n"
        "*) exit 1 ;;\nesac\n"
        'case "$1" in\n*Username*) printf "%s\\n" "InkyXFeather" ;;\n'
        '*) printf "%s\\n" "$GITEE_TOKEN" ;;\nesac\n', encoding="utf-8")
    askpass.chmod(0o700)
    env = {**os.environ, "GIT_ASKPASS": str(askpass), "GIT_ASKPASS_REQUIRE": "force",
           "GIT_TERMINAL_PROMPT": "0", "GITEE_TOKEN": token}

    def git(*args: str) -> None:
        # 仓库 URL 和命令行均不含令牌，也不复用机器上已有的凭据助手。
        command_env = env.copy()
        if "push" not in args:
            command_env.pop("GITEE_TOKEN", None)
        command_env.pop("GITHUB_TOKEN", None)
        subprocess.run(["git", "-c", "credential.helper=", *args], cwd=directory,
                       env=command_env, check=True, timeout=300)

    git("init", "--bare", "repository.git")
    repo = str(directory / "repository.git")
    refs = [f"+refs/tags/{tag}:refs/tags/{tag}"] if only_tag else [
        "+refs/heads/*:refs/heads/*", "+refs/tags/*:refs/tags/*",
    ]
    git("--git-dir", repo, "fetch", "--no-tags", f"https://github.com/{SOURCE}.git", *refs)
    if tag:
        git("--git-dir", repo, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
    push_refs = [f"refs/tags/{tag}:refs/tags/{tag}"] if only_tag else [
        "refs/heads/*:refs/heads/*", "refs/tags/*:refs/tags/*",
    ]
    git("--git-dir", repo, "push", "--force", *(["--dry-run"] if dry_run else []),
        f"https://gitee.com/{TARGET}.git", *push_refs)


def sync_release(gitee: requests.Session, release: dict[str, Any],
                 files: list[tuple[Path, str]], existing: dict[str, Any] | None,
                 dry_run: bool, max_bytes: int = 100000000) -> None:
    tag = release["tag_name"]
    metadata = {"tag_name": tag, "name": release.get("name") or tag,
                "body": release.get("body") or "", "prerelease": False,
                "target_commitish": release.get("target_commitish") or "main"}
    if dry_run:
        print(f"预览：{'更新' if existing else '创建'} Gitee Release {tag}")
        return
    if existing:
        release_id = existing["id"]
        api_request(gitee, "PATCH", GITEE_API, f"/releases/{release_id}", data=metadata)
    else:
        # 同步代码已推送同名标签；不依赖可能变化的 target_commitish 分支。
        created = api_request(gitee, "POST", GITEE_API, "/releases", data=metadata)
        release_id = created["id"]
    for path, digest in files:
        with path.open("rb") as handle:
            result = api_request(gitee, "POST", GITEE_API, f"/releases/{release_id}/attach_files",
                                 files={"file": (path.name, handle, "application/octet-stream")})
        if not result:
            raise RuntimeError(f"上传附件未返回结果: {path.name}")
        uploaded = list_pages(gitee, GITEE_API, f"/releases/{release_id}/attach_files")
        matches = [item for item in uploaded if item.get("name") == path.name]
        if len(matches) != 1:
            raise RuntimeError(f"上传后无法唯一定位附件: {path.name}")
        url = matches[0].get("browser_download_url")
        if not url:
            raise RuntimeError(f"Gitee 未返回公开下载地址: {path.name}")
        if download_hash(url, None, max_bytes,
                         allowed_hosts={"gitee.com", "foruda.gitee.com"}) != digest:
            raise ValueError(f"上传后 SHA256 校验失败: {path.name}")
        print(f"已上传: {path.name} sha256={digest}")


def main() -> None:
    sync_code_value = os.environ.get("SYNC_CODE", "false")
    dry_run_value = os.environ.get("SYNC_DRY_RUN", "true")
    if sync_code_value not in {"true", "false"}:
        raise ValueError("SYNC_CODE 必须是 true 或 false")
    if dry_run_value not in {"true", "false"}:
        raise ValueError("SYNC_DRY_RUN 必须是 true 或 false")
    dry_run = dry_run_value == "true"
    should_sync_code = sync_code_value == "true"
    token = os.environ.get("GITEE_TOKEN", "")
    if not token:
        raise ValueError("请配置 GITEE_TOKEN Secret")
    max_bytes = int(os.environ.get("GITEE_MAX_ASSET_BYTES", "100000000"))
    if max_bytes <= 0:
        raise ValueError("GITEE_MAX_ASSET_BYTES 必须大于 0")
    with requests.Session() as github, requests.Session() as gitee, tempfile.TemporaryDirectory(prefix="gitee-sync-") as tmp:
        # 只重试只读请求；写入超时后由人工重跑，避免重复创建或上传。
        retry = Retry(total=2, connect=0, read=0, other=0, backoff_factor=1,
                      status_forcelist=[429, 502, 503, 504],
                      allowed_methods={"GET"}, raise_on_status=False)
        for session in (github, gitee):
            session.mount("https://", HTTPAdapter(max_retries=retry))
            session.headers["User-Agent"] = "RimCrow-Gitee-Sync"
        if os.environ.get("GITHUB_TOKEN"):
            github.headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
        gitee.headers["Authorization"] = f"Bearer {token}"
        api_request(gitee, "GET", GITEE_API, "")
        directory = Path(tmp)
        assets_dir = directory / "assets"
        assets_dir.mkdir()
        release = None
        existing = None
        pending = []
        tag = ""
        tag = os.environ.get("SYNC_RELEASE_TAG", "").strip()
        endpoint = f"/releases/tags/{quote(tag, safe='')}" if tag else "/releases/latest"
        release = api_request(github, "GET", GITHUB_API, endpoint)
        tag = release["tag_name"]
        if release.get("draft") or release.get("prerelease") or not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
            raise ValueError("仅同步已发布的正式版，Tag 格式必须为 v数字.数字.数字")
        assets = list_pages(github, GITHUB_API, f"/releases/{release['id']}/assets")
        selected = select_assets(assets, tag, os.environ.get("GITEE_ASSET_PATTERNS") or DEFAULT_PATTERNS, max_bytes)
        existing = api_request(gitee, "GET", GITEE_API, f"/releases/tags/{quote(tag, safe='')}", allow_missing=True)
        remote_assets = list_pages(gitee, GITEE_API, f"/releases/{existing['id']}/attach_files") if existing else []
        for asset in selected:
            name = asset["name"]
            path = assets_dir / name
            url = asset["browser_download_url"]
            if not url.startswith(f"https://github.com/{SOURCE}/releases/download/"):
                raise ValueError("GitHub 附件 URL 不属于指定源仓库")
            digest = download_hash(url, path, max_bytes, asset["size"])
            if asset.get("digest") and asset["digest"] != f"sha256:{digest}":
                raise ValueError(f"GitHub 附件 SHA256 校验失败: {name}")
            matches = [item for item in remote_assets if item.get("name") == name]
            if len(matches) > 1:
                raise ValueError(f"Gitee 存在重复附件名: {name}")
            if matches:
                # 同名不等于相同文件；真实比较字节，冲突时不覆盖旧包。
                remote_url = matches[0].get("browser_download_url")
                if not remote_url:
                    raise ValueError(f"Gitee 没有返回附件下载地址: {name}")
                if download_hash(remote_url, None, max_bytes,
                                 allowed_hosts={"gitee.com", "foruda.gitee.com"}) != digest:
                    raise ValueError(f"Gitee 同名附件内容不同，停止同步: {name}")
                print(f"内容一致，跳过: {name}")
            else:
                pending.append((path, digest))
                print(f"{'预览上传' if dry_run else '待上传'}: {name} sha256={digest}")
        # 先完成附件检查，再写远端；代码同步开关开启时同步全部分支和 Tag。
        if should_sync_code:
            sync_code(directory, token, dry_run, tag=tag)
        sync_release(gitee, release, pending, existing, dry_run, max_bytes)
        result = f"{'试运行完成（未修改 Gitee）' if dry_run else '同步完成'}：release {tag}，代码同步={'开启' if should_sync_code else '关闭'}，待上传/已上传附件 {len(pending)}"
        print(result)
        if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(summary, "a", encoding="utf-8") as handle:
                handle.write(f"## Gitee 同步结果\n\n{result}\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Requests 异常可能带完整 URL；在唯一的 CLI 错误出口遮蔽认证信息。
        message = str(exc)
        for key in ("GITEE_TOKEN", "GITHUB_TOKEN"):
            if secret := os.environ.get(key):
                message = message.replace(secret, "***").replace(quote(secret, safe=""), "***")
        print(f"同步失败: {message}", file=sys.stderr)
        sys.exit(1)
