import threading
import time
from typing import Dict, List, Type

from services.logger_service import logger

# 全局停止事件
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


# 策略运行状态（供 UI 仪表盘轮询）
_strategy_stats: dict = {}
_stats_lock = threading.Lock()


def update_strategy_stats(port: int, **kwargs):
    """策略线程调用，上报运行状态"""
    with _stats_lock:
        if port not in _strategy_stats:
            _strategy_stats[port] = {}
        _strategy_stats[port].update(kwargs)


def get_strategy_stats(port: int = None) -> dict:
    """查询策略运行状态"""
    with _stats_lock:
        if port is not None:
            return dict(_strategy_stats.get(port, {}))
        return {p: dict(s) for p, s in _strategy_stats.items()}


def clear_strategy_stats(port: int):
    """清除指定端口的策略状态"""
    with _stats_lock:
        _strategy_stats.pop(port, None)


class StrategyManager:
    """
    策略管理器：每个端口独立线程运行，所有端口并行执行。
    每个端口线程内部：策略1 → 策略2 → ... → 循环，直到 stop_event 触发。
    """

    def __init__(self, ports: List[int]):
        self.ports = ports
        self._threads: List[threading.Thread] = []
        self._running = False
        self._lock = threading.Lock()

    def _run_port(self, port: int, strategy_classes: List[Type]):
        """单端口线程：按顺序执行该端口的所有策略（一轮）"""
        for strategy_cls in strategy_classes:
            if stop_event.is_set():
                break
            try:
                instance = strategy_cls(port=port)
                instance.run()
            except Exception as e:
                logger.error(f"[端口 {port}] 执行策略 {strategy_cls.__name__} 异常: {e}")

    def _run_all(self, strategy_classes: List[Type]):
        """为每个端口启动独立线程并行执行"""
        self._threads = []
        for port in self.ports:
            t = threading.Thread(
                target=self._run_port,
                args=(port, strategy_classes),
                name=f"Port-{port}",
                daemon=True
            )
            t.start()
            self._threads.append(t)
            logger.info(f"[端口 {port}] 策略线程已启动")

        for t in self._threads:
            t.join()

        with self._lock:
            self._running = False

    def start(self, strategy_classes: List[Type]):
        """启动策略执行（每端口独立线程并行）"""
        if self._running:
            logger.warning("策略管理器已在运行中")
            return

        stop_event.clear()
        with self._lock:
            self._running = True
        logger.info(f"策略管理器启动，共 {len(self.ports)} 个端口（每端口独立线程并行）")
        logger.info(f"端口列表: {self.ports}")

        self._coordinator = threading.Thread(
            target=self._run_all,
            args=(strategy_classes,),
            name="StrategyCoordinator",
            daemon=True
        )
        self._coordinator.start()

    def stop(self, on_finished=None):
        """发送停止信号，等待线程结束"""
        if not self._running:
            return
        logger.info("正在向策略发送停止信号...")
        stop_event.set()

        def _cleanup():
            for t in self._threads:
                t.join(timeout=10)
            with self._lock:
                self._running = False
            if on_finished:
                on_finished()

        threading.Thread(target=_cleanup, daemon=True, name="StopCleanup").start()

    def is_running(self) -> bool:
        with self._lock:
            return self._running
