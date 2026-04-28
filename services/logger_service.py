import logging
import os
import datetime
import sys
import queue


class LoggerService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerService, cls).__new__(cls)
            cls._instance._initialize_logger()
        return cls._instance

    def _initialize_logger(self):
        self.logger = logging.getLogger("DragonBallAuto")
        self.logger.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            '[%(asctime)s][%(threadName)s][%(levelname)s] %(message)s',
            datefmt='%H:%M:%S'
        )

        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        today_str = datetime.datetime.now().strftime("%Y%m%d")
        file_handler = logging.FileHandler(f"{log_dir}/{today_str}.log", encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        self._log_queue: queue.Queue = queue.Queue()

    def _log(self, level, message):
        if level == "DEBUG":
            self.logger.debug(message)
        elif level == "INFO":
            self.logger.info(message)
        elif level == "WARNING":
            self.logger.warning(message)
        elif level == "ERROR":
            self.logger.error(message)

        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        formatted_msg = f"[{timestamp}][{level}] {message}"
        try:
            self._log_queue.put_nowait((formatted_msg, level))
        except queue.Full:
            pass

    def drain_queue(self):
        """取出队列中的所有日志消息，返回列表。"""
        messages = []
        while True:
            try:
                msg = self._log_queue.get_nowait()
                messages.append(msg)
            except queue.Empty:
                break
        return messages

    def get_queue_size(self) -> int:
        return self._log_queue.qsize()

    def debug(self, message):
        self._log("DEBUG", message)

    def info(self, message):
        self._log("INFO", message)

    def warning(self, message):
        self._log("WARNING", message)

    def error(self, message):
        self._log("ERROR", message)


# 单例实例
logger = LoggerService()
