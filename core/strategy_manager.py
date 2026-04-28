import threading
import time
from typing import Dict, List, Type

from services.logger_service import logger

# 全局停止事件，所有线程共享
stop_event = threading.Event()

# 屏幕尺寸聚合器，供策略实例向管理器报告尺寸
_screen_sizes: dict = {}
_screen_sizes_lock = threading.Lock()


def register_screen_size(port: int, size: tuple):
    """策略实例调用，上报本端口屏幕尺寸"""
    with _screen_sizes_lock:
        _screen_sizes[port] = size


def get_screen_size(port: int) -> tuple:
    """查询指定端口的屏幕尺寸"""
    with _screen_sizes_lock:
        return _screen_sizes.get(port)


def get_all_screen_sizes() -> dict:
    """查询所有端口的屏幕尺寸"""
    with _screen_sizes_lock:
        return dict(_screen_sizes)


class StrategyManager:
    """
    策略管理器：负责加载策略、创建线程、执行调度。
    """

    def __init__(self, ports: List[int]):
        """
        :param ports: 端口列表，每个端口对应一个执行线程
        """
        self.ports = ports
        self.threads: List[threading.Thread] = []
        self._running = False

    def _worker(self, port: int, strategy_classes: List[Type]):
        """
        单个端口的工作线程，加载该端口对应的所有策略
        :param port: ADB 端口
        :param strategy_classes: 该端口要执行的策略类列表
        """
        for strategy_cls in strategy_classes:
            if stop_event.is_set():
                break
            try:
                instance = strategy_cls(port=port)
                instance.run()
            except Exception as e:
                logger.error(f"[端口 {port}] 执行策略 {strategy_cls.__name__} 异常: {e}")

    def start(self, strategy_classes: List[Type]):
        """
        启动所有策略线程
        :param strategy_classes: 要执行的策略类列表
        """
        if self._running:
            logger.warning("策略管理器已在运行中")
            return

        stop_event.clear()
        self._running = True
        logger.info(f"策略管理器启动，共 {len(self.ports)} 个端口")
        logger.info(f"端口列表: {self.ports}")

        for port in self.ports:
            if stop_event.is_set():
                break
            t = threading.Thread(
                target=self._worker,
                args=(port, strategy_classes),
                name=f"StrategyThread-{port}"
            )
            t.daemon = True
            t.start()
            self.threads.append(t)
            logger.info(f"[端口 {port}] 线程启动")

    def stop(self):
        """
        停止所有策略线程
        """
        if not self._running:
            return

        logger.info("正在停止所有策略...")
        stop_event.set()

        for t in self.threads:
            t.join(timeout=5)

        self.threads.clear()
        self._running = False
        logger.info("策略管理器已停止")

    def is_running(self) -> bool:
        return self._running
