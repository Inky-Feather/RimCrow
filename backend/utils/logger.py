# backend/utils/logger.py
import logging
import json
import os
import sys
import datetime
import colorlog  # 引入 colorlog
from logging.handlers import TimedRotatingFileHandler
from icecream import ic

# 定义日志格式
class JSONFormatter(logging.Formatter):
    """
    结构化 JSON 格式化器
    方便前端 LogViewer 解析和搜索，也方便后续 AI 读取上下文
    """
    def format(self, record):
        log_record = {
            "timestamp": datetime.datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            "level": record.levelname,
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
            "path": record.pathname  # 完整路径，方便点击跳转
        }
        # 如果有异常堆栈，也记录下来
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_record, ensure_ascii=False)

class WebviewHandler(logging.Handler):
    """
    将日志实时推送到前端的 Handler
    """
    def emit(self, record):
        from backend.utils.event_bus import EventBus
        # 如果 EventBus 没有窗口引用，直接跳过，防止报错
        # 这里的 _window 是在 EventBus 中定义的类变量
        if not getattr(EventBus, '_window', None): return 
        try:
            # 格式化为字典对象直接发给前端，不需要再次 JSON 序列化
            log_entry = {
                "id":  f"{record.created}-{id(record)}", # 唯一ID
                "timestamp": datetime.datetime.fromtimestamp(record.created).strftime('%H:%M:%S'),
                "level": record.levelname,
                "module": record.module,
                "message": record.getMessage(),
                "details": record.exc_text if record.exc_text else ""
            }
            # 通过 EventBus 发送给前端
            # 前端监听 'app-log' 事件即可
            EventBus.emit('app-log', log_entry)
        except Exception:
            self.handleError(record)

class CustomColoredFormatter(colorlog.ColoredFormatter):
    """
    自定义的控制台格式化器
    能够智能识别是否为 icecream 的调试信息，并去除多余的 logger.py 调用栈信息
    """
    def format(self, record):
        # 保存原始的格式字符串
        original_fmt = self._style._fmt
        
        # 检查是否标记为 icecream 的日志 (在 log_to_debug 中设置)
        if getattr(record, 'is_icecream', False):
            # 对于 ic() 的输出，我们移除 %(name)s:%(module)s:%(lineno)d 部分
            # 因为 ic() 的 message 内容本身就已经包含了原本的文件名和行号
            # 这样就避免了打印出 "RimModManager:logger:133" 这种无效信息
            self._style._fmt = '%(log_color)s%(asctime)s | %(levelname)-8s | %(message)s'
        
        # 调用父类的 format 方法进行格式化
        result = super().format(record)
        
        # 恢复原始格式，保证普通 logger.info/debug 不受影响
        self._style._fmt = original_fmt
        return result

class LoggerManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        from backend.settings import settings
        # 1. 防止重复初始化 (单例模式下 __init__ 会被多次调用)
        if getattr(self, '_initialized', False): return
        self._initialized = True

        # 1. 创建 Logger
        self._logger = logging.getLogger("RimModManager")
        self._logger.setLevel(logging.DEBUG if settings.config.debug_mode else logging.INFO)
        self._logger.propagate = False # 防止重复打印

        # 2. 准备路径
        log_dir = os.path.join(os.getcwd(), 'data', 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'app.log')

        # 3. Handler: 文件输出 (JSON 结构化，按天轮转)
        file_handler = TimedRotatingFileHandler(
            log_file, when='midnight', interval=1, backupCount=settings.config.log_retention_days, encoding='utf-8'
        )
        file_handler.setFormatter(JSONFormatter())
        file_handler.setLevel(logging.DEBUG) # 文件里尽可能记录所有细节
        self._logger.addHandler(file_handler)

        # 4. Handler: 控制台输出 (Colorlog 美化)
        # 解决 Windows GBK 编码崩溃问题
        
        # 1. 尝试强制重配置 stdout/stderr 为 UTF-8
        if sys.platform.startswith('win'):
            try:
                # Python 3.7+ 支持直接 reconfigure
                if hasattr(sys.stdout, 'reconfigure'):
                    sys.stdout.reconfigure(encoding='utf-8') # type: ignore
                if hasattr(sys.stderr, 'reconfigure'):
                    sys.stderr.reconfigure(encoding='utf-8') # type: ignore
            except Exception:
                # 如果处于某些特殊无控制台环境 (pythonw.exe)，sys.stdout 可能是 None
                pass
        # 2. 安全地添加控制台 Handler
        # 只有当 sys.stdout 存在（不是 None）时才添加，避免 --noconsole 模式下报错
        if sys.stdout is not None:
            try:
                console_handler = logging.StreamHandler(sys.stdout)
        
                # 使用我们自定义的 CustomColoredFormatter
                color_formatter = CustomColoredFormatter(
                    fmt='%(log_color)s%(asctime)s | %(levelname)-8s | %(name)s:%(module)s:%(lineno)d - %(message)s',
                    datefmt='%H:%M:%S',
                    reset=True,
                    log_colors={
                        'DEBUG':    'cyan',
                        'INFO':     'white',
                        'WARNING':  'yellow',
                        'ERROR':    'red',
                        'CRITICAL': 'red,bg_white',
                    },
                    secondary_log_colors={},
                    style='%'
                )
                
                console_handler.setFormatter(color_formatter)
                console_handler.setLevel(logging.DEBUG if settings.config.debug_mode else logging.INFO)
                self._logger.addHandler(console_handler)
            except Exception as e:
                # 如果控制台初始化还是失败，记录错误但不让程序崩溃
                # 这里只能用文件记录了，因为控制台坏了
                file_handler.emit(logging.LogRecord(
                    "Logger", logging.ERROR, "", 0, f"Console handler init failed: {e}", (), None
                ))
                
        # 5. Handler: Webview 推送 (前端 UI 显示)
        webview_handler = WebviewHandler()
        webview_handler.setLevel(logging.DEBUG)
        self._logger.addHandler(webview_handler)

        # 6. 集成 Icecream (关键步骤)
        self._configure_icecream(settings.config.debug_mode)
        self._logger.info("Logger system initialized with Colorlog.")

    def _configure_icecream(self, debug_mode: bool):
        """ 配置 icecream 的行为 """
        if debug_mode:
            ic.enable()
            # 【核心】将 ic 的输出重定向到 logger.debug
            # 这样 ic() 打印的内容既会在控制台高亮显示（ic自带），也会被写入 log 文件
            def log_to_debug(text):
                # 移除 icecream 自动添加的 'ic| ' 前缀
                # 注意：如果你希望在控制台看到 'IC| '，可以不 replace，或者只在 JSON 里 replace
                clean_text = text.replace('IC| ', '') 
                if self._logger:
                    # 【修改点】添加 extra 参数，告诉 Formatter 这是一条来自 icecream 的消息
                    self._logger.debug(clean_text, extra={'is_icecream': True})
            
            ic.configureOutput(prefix='IC| ', includeContext=True, outputFunction=log_to_debug)
        else:
            # 生产环境禁用 ic，避免性能损耗和敏感信息泄露
            ic.disable()

    @property
    def logger(self) -> logging.Logger:
        return self._logger

# 全局单例
logger_manager = LoggerManager()
# 导出 logger 实例供其他模块使用
logger = logger_manager.logger