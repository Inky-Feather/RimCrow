"""系统 Hosts 的受控文件操作；worker 入口只依赖标准库，不初始化应用。"""

import ctypes
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import socket
import stat
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Any


MARKER_START = b"# --- RimCrow Hosts Start ---"
MARKER_END = b"# --- RimCrow Hosts End ---"
WORKER_TIMEOUT = 3.0
AUTHORIZATION_TIMEOUT = 60.0
MAX_MESSAGE_BYTES = 2 * 1024 * 1024


class HostsChangedError(OSError):
    """检测到外部修改，不覆盖其它程序刚写入的内容。"""


def _system_hosts_path() -> Path:
    if os.name != "nt":
        return Path("/etc/hosts")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    get_directory = kernel.GetSystemWindowsDirectoryW
    get_directory.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
    get_directory.restype = ctypes.c_uint32
    buffer = ctypes.create_unicode_buffer(32768)
    length = get_directory(buffer, len(buffer))
    if not 0 < length < len(buffer):
        raise ctypes.WinError(ctypes.get_last_error())
    return Path(buffer.value) / "System32/drivers/etc/hosts"


@contextmanager
def _writer_lock():
    """普通 worker 和提权 helper 共用串行锁，清理不能越过正在提交的写入。"""
    if os.name != "nt":
        yield
        return
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.WaitForSingleObject.restype = ctypes.c_uint32
    kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateMutexW(None, False, "Local\\RimCrow.SystemHostsWriter")
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    acquired = False
    try:
        wait = kernel.WaitForSingleObject(handle, int(WORKER_TIMEOUT * 1000))
        acquired = wait in (0, 0x80)  # 前一个 worker 异常退出时仍取得废弃互斥量的所有权。
        if not acquired:
            raise TimeoutError("System Hosts writer is busy")
        yield
    finally:
        if acquired:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


def _failure(exc: Exception) -> dict[str, Any]:
    code = "WRITE_FAILED"
    if isinstance(exc, PermissionError):
        code = "PERMISSION_DENIED"
    elif isinstance(exc, HostsChangedError):
        code = "CONTENT_CHANGED"
    elif isinstance(exc, TimeoutError):
        code = "TIMEOUT"
    elif isinstance(exc, ValueError):
        code = "INVALID_CONTENT"
    return {"status": "error", "error_code": f"NETWORK.HOSTS.{code}", "error": str(exc),
            "errno": getattr(exc, "errno", None), "winerror": getattr(exc, "winerror", None)}


def update_system_hosts(path: Path, hosts: dict[str, str], *, before_replace: Callable[[], None] | None = None) -> bool:
    """只替换本应用标记块；保留块外原始字节，写入失败不截断原文件。"""
    if not isinstance(hosts, dict):
        raise ValueError("Invalid Hosts mapping")
    for host, address in hosts.items():
        if not isinstance(host, str) or not isinstance(address, str):
            raise ValueError("Invalid Hosts mapping")
        if not re.fullmatch(r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", host) or len(host) > 253:
            raise ValueError("Invalid Hosts domain")
        ipaddress.ip_address(address)
        if "%" in address:
            raise ValueError("Scoped IP addresses are not supported")
    original = path.read_bytes()
    # 不猜测损坏标记的边界，避免误删用户或其它软件的内容。
    lines = original.splitlines(keepends=True)
    content = bytearray()
    inside = False
    for line in lines:
        marker = line.rstrip(b"\r\n")
        if marker == MARKER_START:
            if inside:
                raise ValueError("Nested RimCrow Hosts block")
            inside = True
        elif marker == MARKER_END:
            if not inside:
                raise ValueError("Unmatched RimCrow Hosts marker")
            inside = False
        elif not inside:
            content.extend(line)
    if inside:
        raise ValueError("Unclosed RimCrow Hosts block")
    if hosts:
        newline = b"\r\n" if b"\r\n" in original else b"\n"
        if content and not content.endswith(b"\n"):
            content.extend(newline)
        content.extend(MARKER_START + newline)
        for host, address in sorted(hosts.items()):
            content.extend(f"{address}\t{host}".encode("ascii") + newline)
        content.extend(MARKER_END + newline)
    if content == original:
        return False

    temp_path = None
    try:
        # Windows 的 tempfile 可能把权限拒绝误判为重名并海量重试；这里只重试真实重名。
        for attempt in range(3):
            candidate = path.with_name(f".rimcrow-hosts-{uuid.uuid4().hex}.tmp")
            try:
                fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                temp_path = candidate
                break
            except FileExistsError:
                if attempt == 2:
                    raise
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        # 替换前再次核对，遇到并发外部修改时不覆盖。此检查不提供跨软件事务锁。
        if path.read_bytes() != original:
            raise HostsChangedError("System Hosts changed during update")
        if before_replace is not None:
            before_replace()
        if path.read_bytes() != original:
            raise HostsChangedError("System Hosts changed before commit")
        if os.name == "nt":
            replace = ctypes.WinDLL("kernel32", use_last_error=True).ReplaceFileW
            replace.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
            replace.restype = ctypes.c_int
            # ReplaceFile 保留目标 ACL；不能用 chmod 复制 Windows 权限。
            if not replace(str(path), str(temp_path), None, 0, None, None):
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            info = path.stat()
            os.chown(temp_path, info.st_uid, info.st_gid)
            os.chmod(temp_path, stat.S_IMODE(info.st_mode))
            os.replace(temp_path, path)
        if path.read_bytes() != content:
            raise HostsChangedError("System Hosts verification failed after replacement")
        return True
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _send_message(connection: socket.socket, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=True).encode("ascii")
    if len(data) > MAX_MESSAGE_BYTES:
        raise ValueError("Hosts message is too large")
    connection.sendall(len(data).to_bytes(4, "big") + data)


def _receive_message(connection: socket.socket) -> dict[str, Any]:
    deadline = time.monotonic() + WORKER_TIMEOUT

    def receive(size: int) -> bytes:
        data = bytearray()
        while len(data) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Hosts message deadline exceeded")
            connection.settimeout(remaining)
            chunk = connection.recv(size - len(data))
            if not chunk:
                raise ConnectionAbortedError("Hosts controller disconnected")
            data.extend(chunk)
        return bytes(data)

    size = int.from_bytes(receive(4), "big")
    if not 0 < size <= MAX_MESSAGE_BYTES:
        raise ValueError("Invalid Hosts message size")
    payload = json.loads(receive(size))
    if not isinstance(payload, dict):
        raise ValueError("Invalid Hosts message")
    return payload


def _launch_elevated_helper(entrypoint: Path, port: int, token: str) -> dict[str, Any]:
    """运行在可回收的授权 broker 中，不把 UAC 等待放到主进程或网络锁内。"""
    if os.name != "nt":
        raise OSError("Hosts elevation is only supported on Windows")

    class ShellExecuteInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint32), ("fMask", ctypes.c_uint32), ("hwnd", ctypes.c_void_p),
            ("lpVerb", ctypes.c_wchar_p), ("lpFile", ctypes.c_wchar_p), ("lpParameters", ctypes.c_wchar_p),
            ("lpDirectory", ctypes.c_wchar_p), ("nShow", ctypes.c_int), ("hInstApp", ctypes.c_void_p),
            ("lpIDList", ctypes.c_void_p), ("lpClass", ctypes.c_wchar_p), ("hkeyClass", ctypes.c_void_p),
            ("dwHotKey", ctypes.c_uint32), ("hIcon", ctypes.c_void_p), ("hProcess", ctypes.c_void_p),
        ]

    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    ole = ctypes.OleDLL("ole32")
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoUninitialize.argtypes = []
    shell.ShellExecuteExW.argtypes = [ctypes.POINTER(ShellExecuteInfo)]
    shell.ShellExecuteExW.restype = ctypes.c_int
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.WaitForSingleObject.restype = ctypes.c_uint32
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    args = [] if getattr(sys, "frozen", False) or "__compiled__" in globals() else [str(entrypoint.resolve())]
    args.extend(["--system-hosts-helper", str(port), token])
    info = ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x40 | 0x100 | 0x400  # 保留进程句柄，同步启动，错误由应用统一提示。
    info.lpVerb = "runas"
    info.lpFile = sys.executable
    info.lpParameters = subprocess.list2cmdline(args)
    info.lpDirectory = str(entrypoint.resolve().parent)
    initialized = False
    try:
        ole.CoInitializeEx(None, 2)
        initialized = True
        if not shell.ShellExecuteExW(ctypes.byref(info)):
            error = ctypes.get_last_error()
            return {"status": "error", "error_code": "NETWORK.HOSTS.ELEVATION_CANCELLED" if error == 1223 else "NETWORK.HOSTS.ELEVATION_FAILED", "winerror": error}
        if not info.hProcess:
            raise OSError("UAC returned no process handle")
        # 授权和文件执行分开计时；主进程取消时会回收 broker 并关闭 helper 通道。
        if kernel.WaitForSingleObject(info.hProcess, int((WORKER_TIMEOUT + 1) * 1000)) != 0:
            raise TimeoutError("Elevated Hosts helper did not exit")
        return {"status": "success"}
    finally:
        if info.hProcess:
            kernel.CloseHandle(info.hProcess)
        if initialized:
            ole.CoUninitialize()


def run_elevated_hosts_helper(port: int, token: str) -> int:
    """只通过一次性回环通道取得映射和提交许可，不接受文件路径或命令。"""
    with socket.create_connection(("127.0.0.1", port), timeout=WORKER_TIMEOUT) as connection:
        challenge = secrets.token_hex(32)
        _send_message(connection, {"challenge": challenge})
        proof = _receive_message(connection).get("proof", "")
        expected = hmac.digest(bytes.fromhex(token), ("server:" + challenge).encode("ascii"), "sha256").hex()
        if not isinstance(proof, str) or not hmac.compare_digest(proof, expected):
            raise ValueError("Untrusted Hosts controller")
        _send_message(connection, {"proof": hmac.digest(bytes.fromhex(token), ("helper:" + challenge).encode("ascii"), "sha256").hex()})
        request = _receive_message(connection)

        def confirm_commit() -> None:
            _send_message(connection, {"status": "prepared"})
            if _receive_message(connection).get("commit") is not True:
                raise ConnectionAbortedError("Hosts task was cancelled")

        try:
            with _writer_lock():
                changed = update_system_hosts(_system_hosts_path(), request["hosts"], before_replace=confirm_commit)
            result = {"status": "success", "changed": changed, "error_code": ""}
        except Exception as exc:
            result = _failure(exc)
        _send_message(connection, result)
        return 0 if result["status"] == "success" else 1


def _ensure_worker_stdio() -> None:
    if os.name == "nt" and (sys.stdin is None or sys.stdout is None):
        import msvcrt
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetStdHandle.argtypes = [ctypes.c_uint32]
        kernel.GetStdHandle.restype = ctypes.c_void_p
        # 无控制台打包的标准流可能为 None，但父进程建立的管道句柄仍有效。
        if sys.stdin is None:
            sys.stdin = os.fdopen(msvcrt.open_osfhandle(kernel.GetStdHandle(-10), os.O_RDONLY), "r", encoding="utf-8")
        if sys.stdout is None:
            sys.stdout = os.fdopen(msvcrt.open_osfhandle(kernel.GetStdHandle(-11), os.O_WRONLY), "w", encoding="utf-8")


def run_system_hosts_worker() -> int:
    """固定操作系统 Hosts 路径，父进程不能指定任意文件。"""
    _ensure_worker_stdio()
    try:
        hosts = json.load(sys.stdin)
        if not isinstance(hosts, dict):
            raise ValueError("Invalid Hosts mapping")
        with _writer_lock():
            changed = update_system_hosts(_system_hosts_path(), hosts)
        result = {"status": "success", "changed": changed, "error_code": ""}
    except Exception as exc:
        result = _failure(exc)
    sys.stdout.write(json.dumps(result, ensure_ascii=True))
    return 0 if result["status"] == "success" else 1


def run_hosts_authorization(entrypoint: Path, port: int, token: str) -> int:
    _ensure_worker_stdio()
    try:
        result = _launch_elevated_helper(entrypoint, port, token)
    except Exception as exc:
        result = _failure(exc)
    if sys.stdout is not None:
        sys.stdout.write(json.dumps(result, ensure_ascii=True))
    return 0 if result["status"] == "success" else 1


class SystemHostsService:
    """单写入者、仅保留最新目标；文件操作由有超时的短命子进程执行。"""

    def __init__(self, entrypoint: Path, on_result: Callable[[dict[str, Any]], None]):
        self._entrypoint = entrypoint
        self._on_result = on_result
        self._condition = threading.Condition()
        self._thread: threading.Thread | None = None
        self._pending: tuple[dict[str, str], bool] | None = None
        self._desired: dict[str, str] | None = None
        self._closing = False
        self._version = 0
        self._executing_version = 0
        self._elevation_connection: socket.socket | None = None
        self._state: dict[str, Any] = {"status": "idle", "error_code": "", "version": 0}

    def submit(self, hosts: dict[str, str], *, allow_elevation: bool = False) -> None:
        with self._condition:
            if self._closing or (hosts == self._desired and self._state["status"] != "error"):
                return
            self._enqueue(hosts, allow_elevation=allow_elevation)

    def _enqueue(self, hosts: dict[str, str], *, allow_elevation: bool = False) -> None:
        if self._elevation_connection is not None:
            try:
                self._elevation_connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass  # 通道可能已随 helper 的正常结束关闭。
        self._version += 1
        self._desired = dict(hosts)
        self._pending = (dict(hosts), allow_elevation)
        self._state = {"status": "applying", "error_code": "", "version": self._version, "removing": not bool(hosts)}
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="system-hosts", daemon=True)
            self._thread.start()
        self._condition.notify_all()

    def status(self) -> dict[str, Any]:
        with self._condition:
            return dict(self._state)

    def close(self) -> None:
        with self._condition:
            if not self._closing:
                self._closing = True
                if self._thread is None:
                    return
                # 清理必须排在已有写入之后，旧任务不能在清理完成后重新提交。
                self._enqueue({})
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(WORKER_TIMEOUT * 2 + 1)

    def _worker_command(self, mode: str) -> list[str]:
        cmd = [sys.executable]
        # Nuitka 不设置 sys.frozen；编译后的 sys.executable 也已是应用自身。
        if not getattr(sys, "frozen", False) and "__compiled__" not in globals():
            cmd.append(str(self._entrypoint))
        cmd.append(mode)
        return cmd

    def _execute(self, hosts: dict[str, str], *, allow_elevation: bool = False) -> dict[str, Any]:
        cmd = self._worker_command("--system-hosts-worker")
        env = {**os.environ, "_PYI_SPLASH_IPC": "0", "PYTHONIOENCODING": "utf-8"}
        try:
            result = subprocess.run(
                cmd, input=json.dumps(hosts), capture_output=True, text=True, encoding="utf-8",
                timeout=WORKER_TIMEOUT, env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            payload = json.loads(result.stdout)
            if not isinstance(payload, dict) or payload.get("status") not in {"success", "error"} or (result.returncode != 0 and payload["status"] == "success"):
                raise ValueError("Invalid system Hosts worker result")
            if allow_elevation and os.name == "nt" and payload.get("error_code") == "NETWORK.HOSTS.PERMISSION_DENIED":
                return self._execute_elevated(hosts)
            return payload
        except subprocess.TimeoutExpired:
            # subprocess.run 会终止并回收超时子进程，不留下继续写入的孤儿任务。
            return {"status": "error", "error_code": "NETWORK.HOSTS.TIMEOUT"}
        except TimeoutError as exc:
            return _failure(exc)
        except (OSError, ValueError) as exc:
            return {"status": "error", "error_code": "NETWORK.HOSTS.WORKER_FAILED", "error": str(exc)}

    def _execute_elevated(self, hosts: dict[str, str]) -> dict[str, Any]:
        with self._condition:
            version = self._executing_version
            if self._closing or version != self._version or self._desired != hosts:
                return {"status": "error", "error_code": "NETWORK.HOSTS.CANCELLED"}
            self._state = {**self._state, "status": "authorizing"}

        def is_current() -> bool:
            with self._condition:
                return not self._closing and version == self._version

        # 不把文件路径或待写入数据放入提权命令行；随机令牌仅用于本次本机连接。
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            if os.name == "nt":
                server.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            server.settimeout(0.1)
            token = secrets.token_hex(32)
            cmd = self._worker_command("--system-hosts-authorize") + [str(server.getsockname()[1]), token]
            process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       env={**os.environ, "_PYI_SPLASH_IPC": "0", "PYTHONIOENCODING": "utf-8"},
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            deadline = time.monotonic() + AUTHORIZATION_TIMEOUT
            try:
                while is_current():
                    if time.monotonic() >= deadline:
                        return {"status": "error", "error_code": "NETWORK.HOSTS.AUTHORIZATION_TIMEOUT"}
                    try:
                        connection, _ = server.accept()
                    except socket.timeout:
                        if process.poll() is not None:
                            output, _ = process.communicate(timeout=WORKER_TIMEOUT)
                            payload = json.loads(output)
                            if not isinstance(payload, dict) or payload.get("status") != "error":
                                raise ValueError("Authorization ended without a Hosts result")
                            return payload
                        continue
                    with connection:
                        connection.settimeout(WORKER_TIMEOUT)
                        with self._condition:
                            self._elevation_connection = connection
                        if not is_current():
                            break
                        challenge = _receive_message(connection).get("challenge")
                        if not isinstance(challenge, str) or len(challenge) != 64 or not challenge.isascii():
                            continue
                        key = bytes.fromhex(token)
                        _send_message(connection, {"proof": hmac.digest(key, ("server:" + challenge).encode("ascii"), "sha256").hex()})
                        proof = _receive_message(connection).get("proof", "")
                        expected = hmac.digest(key, ("helper:" + challenge).encode("ascii"), "sha256").hex()
                        if not isinstance(proof, str) or not hmac.compare_digest(proof, expected):
                            continue
                        if not is_current():
                            break
                        _send_message(connection, {"hosts": hosts})
                        payload = _receive_message(connection)
                        if payload.get("status") == "prepared":
                            _send_message(connection, {"commit": is_current()})
                            payload = _receive_message(connection)
                        if payload.get("status") not in {"success", "error"}:
                            raise ValueError("Invalid elevated Hosts result")
                        return payload
                return {"status": "error", "error_code": "NETWORK.HOSTS.CANCELLED"}
            finally:
                with self._condition:
                    self._elevation_connection = None
                # 关闭监听器后，迟到的 helper 无法取得映射；正在准备的 helper 无法取得提交许可。
                server.close()
                if process.poll() is None:
                    process.kill()
                try:
                    process.communicate(timeout=WORKER_TIMEOUT)
                except subprocess.TimeoutExpired:
                    # 授权子进程不能让继承管道的异常情况拖住退出。
                    process.stdout.close()
                    process.stderr.close()

    def _run(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._pending is not None)
                (hosts, allow_elevation), version = self._pending, self._version
                self._executing_version = version
                self._pending = None
            start = time.perf_counter()
            try:
                result = self._execute(hosts, allow_elevation=allow_elevation)
            except Exception as exc:
                result = _failure(exc)
            state = {**result, "status": "error" if result["status"] == "error" else "applied" if hosts else "removed",
                     "version": version, "removing": not bool(hosts), "duration_ms": round((time.perf_counter() - start) * 1000, 2)}
            with self._condition:
                is_current = version == self._version
                if is_current:
                    self._state = state
                finished = self._closing and self._pending is None
            if is_current:
                try:
                    self._on_result(dict(state))
                except Exception:
                    logging.getLogger(__name__).exception("系统 Hosts 结果通知失败")
            if finished:
                return
