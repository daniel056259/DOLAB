import time
import inspect
import os
import json
from typing import Dict, NamedTuple, Optional, Any
from enum import Enum

class LogLevel(Enum):
    VERBOSE = 1
    DEBUG = 2
    INFO = 3
    WARN = 4
    ERROR = 5

class StepInfo(NamedTuple):
    name: str
    start_time: float

class Log:
    overall_start: float = time.time()
    steps: Dict[int, StepInfo] = {}
    step_counter: int = 0
    log_level: LogLevel = LogLevel.VERBOSE
    log_dir: str = "logs"
    log_file: Optional[str] = None
    critical_log_file: Optional[str] = None
    enable_console: bool = True
    include_warn_in_critical: bool = False
    max_file_size: int = 100 * 1024 * 1024

    _current_log_file: Optional[str] = None
    _current_critical_log_file: Optional[str] = None

    @classmethod
    def set_level(cls, level: LogLevel) -> None:
        cls.log_level = level

    @classmethod
    def set_log_file(cls, log_dir: Optional[str] = None) -> None:
        cls.log_dir = log_dir if log_dir else cls.log_dir
        os.makedirs(cls.log_dir, exist_ok=True)
        date_str = time.strftime("%Y-%m-%d")
        base_file = os.path.join(cls.log_dir, f"{date_str}.log")

        # 롤링된 마지막 파일 찾기
        cls._current_log_file = cls._find_latest_log_file(base_file)
        cls.log_file = base_file
        cls.critical_log_file = os.path.join(cls.log_dir, f"critical_{date_str}.log")
        cls._current_critical_log_file = cls.critical_log_file

    @classmethod
    def _find_latest_log_file(cls, base_path: str) -> str:
        if not os.path.exists(base_path):
            return base_path

        base, ext = os.path.splitext(base_path)
        counter = 1
        candidate = base_path
        while True:
            next_file = f"{base}_{counter}{ext}"
            if not os.path.exists(next_file):
                break
            candidate = next_file
            counter += 1
        return candidate
    
    @classmethod
    def set_console_output(cls, enable: bool) -> None:
        cls.enable_console = enable

    @classmethod
    def set_critical_include_warn(cls, include: bool) -> None:
        cls.include_warn_in_critical = include

    @classmethod
    def set_max_file_size(cls, size_in_bytes: int) -> None:
        cls.max_file_size = size_in_bytes

    @classmethod
    def _get_caller(cls) -> str:
        stack = inspect.stack()
        for frame in stack:
            module = inspect.getmodule(frame.frame)
            if module and module.__file__:
                filename = os.path.basename(module.__file__).replace(".py", "")
                if filename not in ("log", "logger"):
                    return filename
        return "Unknown"

    @classmethod
    def _roll_log_file(cls, file_path: str) -> str:
        base, ext = os.path.splitext(file_path)
        counter = 1
        new_file = f"{base}_{counter}{ext}"
        while os.path.exists(new_file):
            counter += 1
            new_file = f"{base}_{counter}{ext}"
        return new_file

    @classmethod
    def _check_roll_and_get_file(cls, path: str, is_critical: bool = False) -> str:
        if os.path.exists(path) and os.path.getsize(path) >= cls.max_file_size:
            new_path = cls._roll_log_file(path)
            if is_critical:
                cls._current_critical_log_file = new_path
            else:
                cls._current_log_file = new_path
            return new_path
        return path

    @classmethod
    def _log_to_file(cls, message: str, is_critical: bool = False) -> None:
        if cls._current_log_file:
            path = cls._check_roll_and_get_file(cls._current_log_file, is_critical=False)
            with open(path, "a", encoding="utf-8") as f:
                f.write(message + "\n")

        if is_critical and cls._current_critical_log_file:
            path = cls._check_roll_and_get_file(cls._current_critical_log_file, is_critical=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(message + "\n")

    @classmethod
    def log(cls, *args: Any, level: LogLevel = LogLevel.INFO) -> None:
        if level.value < cls.log_level.value:
            return

        tag = cls._get_caller()
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        formatted_message = " ".join(
            json.dumps(arg, ensure_ascii=False) if isinstance(arg, dict) else str(arg)
            for arg in args
        )

        # 로그 파일 내에서 줄바꿈이 일어나지 않도록 '\n'을 '\\n'으로 수정
        if level is not LogLevel.DEBUG:
            formatted_message = formatted_message.replace("\n", "\\n")

        log_output = f"[{timestamp}] [{level.name}] [{tag}] {formatted_message}"

        if cls.enable_console:
            print(log_output)

        is_critical = level in {LogLevel.ERROR} or (cls.include_warn_in_critical and level == LogLevel.WARN)
        cls._log_to_file(log_output, is_critical)

    @classmethod
    def v(cls, *args: Any) -> None:
        cls.log(*args, level=LogLevel.VERBOSE)

    @classmethod
    def d(cls, *args: Any) -> None:
        cls.log(*args, level=LogLevel.DEBUG)

    @classmethod
    def i(cls, *args: Any) -> None:
        cls.log(*args, level=LogLevel.INFO)

    @classmethod
    def w(cls, *args: Any) -> None:
        cls.log(*args, level=LogLevel.WARN)

    @classmethod
    def e(cls, *args: Any) -> None:
        cls.log(*args, level=LogLevel.ERROR)

    @classmethod
    def start(cls, step_name: str) -> int:
        cls.step_counter += 1
        step_id = cls.step_counter
        cls.steps[step_id] = StepInfo(step_name, time.time())
        cls.v(f"[{step_id}] {step_name} started")
        return step_id

    @classmethod
    def end(cls, step_id: int) -> None:
        if step_id not in cls.steps:
            cls.e(f"'{step_id}' ID의 단계가 존재하지 않습니다.")
            return

        step = cls.steps[step_id]
        end_time = time.time()
        duration = end_time - step.start_time

        cls.i(f"[{step_id}] {step.name} completed (Elapsed time: {duration:.2f}s)")
        del cls.steps[step_id]
