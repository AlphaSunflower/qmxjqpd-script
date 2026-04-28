from __future__ import annotations
import os
import sys
import time
import random
import threading
from abc import ABC, abstractmethod

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.adb_service import ADBService
from services.image_service import image_service
from services.logger_service import logger
from core.strategy_manager import stop_event, register_screen_size


class BaseStrategy(ABC):
    """
    策略基类，提供所有策略共用的方法。
    子类只需实现 run() 方法和流程控制方法。
    """

    def __init__(self, port: int, config: dict, click_offset: int = 10):
        """
        初始化策略
        :param port: ADB 端口号
        :param config: 模式配置字典
        :param click_offset: 点击偏差，默认 10
        """
        self.port = port
        self.config = config
        self.click_offset = click_offset
        self.adb: ADBService = None
        self.image: ImageService = None
        self.screen_size: tuple = None
        self.victory_count = 0
        self.failure_count = 0
        self._strategy_name = self.__class__.__name__

    def _connect(self) -> bool:
        """
        连接 ADB 设备并初始化图像识别服务
        """
        try:
            self.adb = ADBService(port=self.port)
            if not self.adb.connect():
                return False
            self.image = image_service

            size = self.adb.get_screen_size()
            if size:
                self.screen_size = size
                register_screen_size(self.port, size)
                logger.info(f"[端口 {self.port}] [{self._strategy_name}] 屏幕分辨率: {size[0]}x{size[1]}")
            else:
                logger.warning(f"[端口 {self.port}] [{self._strategy_name}] 无法获取屏幕分辨率")

            logger.info(f"[端口 {self.port}] [{self._strategy_name}] 初始化完成")
            return True
        except Exception as e:
            logger.error(f"[端口 {self.port}] [{self._strategy_name}] 连接初始化失败: {e}")
            return False

    def _disconnect(self):
        """
        断开 ADB 连接
        """
        if self.adb:
            self.adb.disconnect()

    def _scale_coords(self, x: int, y: int) -> tuple:
        """
        将 1280x720 设计坐标转换为当前设备坐标
        :return: (实际x, 实际y)
        """
        if not self.screen_size:
            return (x, y)
        scale = self.screen_size[0] / 1280
        return (int(x * scale), int(y * scale))

    def _tap_with_offset(self, x: int, y: int, offset: int = None) -> bool:
        """
        带偏差的点击（可重写），设计坐标基于 1280x720，自动按屏幕宽度比例缩放
        :param x: 横坐标（基于 1280x720）
        :param y: 纵坐标（基于 1280x720）
        :param offset: 偏差值，默认使用 self.click_offset
        :return: 点击是否成功
        """
        if offset is None:
            offset = self.click_offset

        scale = (self.screen_size[0] / 1280) if self.screen_size else 1.0
        offset_x = int(random.randint(-offset, offset) * scale)
        offset_y = int(random.randint(-offset, offset) * scale)
        tap_x = int(x * scale + offset_x)
        tap_y = int(y * scale + offset_y)

        if self.adb is None:
            return False
        self.adb.tap(tap_x, tap_y)
        self.adb.invalidate_screen_cache()
        return True

    def _match_template(self, template_name: str, threshold: float = 0.8) -> tuple:
        """
        模板匹配查找目标
        :param template_name: 模板图片文件名（不含路径）
        :param threshold: 匹配阈值
        :return: 匹配到的中心坐标 (x, y)，未匹配到返回 None
        """
        if self.adb is None or self.image is None:
            return None

        screen = self.adb.screencap()
        if screen is None:
            return None

        template_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "resources", "images", template_name
        )
        if not os.path.exists(template_path):
            logger.warning(f"[端口 {self.port}] 模板图片不存在: {template_path}")
            return None

        return self.image.match_template(screen, template_path, threshold)

    def _match_sift(self, template_name: str, min_match: int = 30) -> tuple:
        """
        SIFT 特征匹配查找目标
        :param template_name: 模板图片文件名
        :param min_match: 最小匹配点数
        :return: 匹配到的中心坐标 (x, y)，未匹配到返回 None
        """
        if self.adb is None or self.image is None:
            return None

        screen = self.adb.screencap()
        if screen is None:
            return None

        template_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "resources", "images", template_name
        )
        if not os.path.exists(template_path):
            logger.warning(f"[端口 {self.port}] 模板图片不存在: {template_path}")
            return None

        return self.image.match_sift(screen, template_path, min_match)

    def _wait_for_image(self, template_name: str, timeout: float = 10,
                        interval: float = 1, method: str = "template") -> tuple:
        """
        等待图像出现
        :param template_name: 模板图片文件名
        :param timeout: 超时时间（秒）
        :param interval: 检测间隔（秒）
        :param method: "template" 或 "sift"
        :return: 匹配到的坐标 (x, y)，超时返回 None
        """
        start = time.time()
        while not stop_event.is_set():
            if time.time() - start > timeout:
                break
            pos = self._match_template(template_name) if method == "template" else self._match_sift(template_name)
            if pos:
                return pos
            time.sleep(interval)
        return None

    def _ocr_area(self, area: tuple = None) -> list:
        """
        OCR 识别屏幕文字，同步版本。
        :param area: 裁剪区域 (x, y, w, h)，None 表示全屏，坐标基于 1280x720
        :return: 识别到的文本列表
        """
        if self.adb is None or self.image is None:
            return []

        screen = self.adb.screencap()
        if screen is None:
            return []

        if area:
            sx, sy = self._scale_coords(area[0], area[1])
            sw, sh = self._scale_coords(area[2], area[3])
            screen = self.adb.screencap_area(sx, sy, sw, sh)
            if screen is None:
                return []

        return self.image.ocr_text(screen, stop_check=stop_event.is_set)

    def _ocr_area_async(self, area: tuple = None) -> str:
        """
        异步 OCR，立即提交到线程池，立即返回 request_id。
        调用后策略可继续执行其他逻辑，通过 _ocr_result 查询结果。
        :param area: 裁剪区域 (x, y, w, h)
        :return: request_id，或 None（失败时）
        """
        if self.adb is None or self.image is None:
            return None

        screen = self.adb.screencap()
        if screen is None:
            return None

        if area:
            sx, sy = self._scale_coords(area[0], area[1])
            sw, sh = self._scale_coords(area[2], area[3])
            screen = self.adb.screencap_area(sx, sy, sw, sh)
            if screen is None:
                return None

        return self.image.ocr_text_async(screen)

    def _ocr_result(self, request_id: str) -> list:
        """
        查询异步 OCR 结果（非阻塞）。
        :param request_id: _ocr_area_async 返回的 id
        :return: 文本列表（完成时），或 None（未完成）
        """
        if self.image is None or request_id is None:
            return []
        return self.image.ocr_poll(request_id)

    def _get_pixel_color(self, x: int, y: int) -> tuple:
        """
        获取屏幕指定坐标的颜色（BGR 格式），坐标基于 1280x720 设计分辨率。
        :param x: 横坐标
        :param y: 纵坐标
        :return: (B, G, R) 元组，或失败时返回 None
        """
        if self.adb is None or self.image is None:
            return None
        screen = self.adb.screencap()
        if screen is None:
            return None
        sx, sy = self._scale_coords(x, y)
        return self.image.get_pixel_color(screen, sx, sy)

    def _is_color_in_range(self, x: int, y: int, lower: tuple, upper: tuple) -> bool:
        """
        判断屏幕指定坐标的颜色是否在阈值范围内（BGR 格式），坐标基于 1280x720。
        :param x: 横坐标
        :param y: 纵坐标
        :param lower: (B, G, R) 下界
        :param upper: (B, G, R) 上界
        :return: 在范围内返回 True
        """
        color = self._get_pixel_color(x, y)
        return self.image.is_color_in_range(color, lower, upper)

    def _wait_for_color(self, x: int, y: int, lower: tuple, upper: tuple,
                        timeout: float = 10.0, interval: float = 0.5) -> bool:
        """
        等待屏幕指定坐标的颜色进入阈值范围，坐标基于 1280x720。
        :param x: 横坐标
        :param y: 纵坐标
        :param lower: (B, G, R) 下界
        :param upper: (B, G, R) 上界
        :param timeout: 超时时间（秒）
        :param interval: 检测间隔（秒）
        :return: 颜色进入范围返回 True，超时返回 False
        """
        if self.adb is None or self.image is None:
            return False
        import time
        start = time.time()
        while time.time() - start < timeout and not stop_event.is_set():
            color = self._get_pixel_color(x, y)
            if self.image.is_color_in_range(color, lower, upper):
                return True
            time.sleep(interval)
        return False

    def _swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 500):
        """
        滑动屏幕，设计坐标基于 1280x720，自动按屏幕宽度比例缩放
        """
        if self.adb:
            sx1, sy1 = self._scale_coords(x1, y1)
            sx2, sy2 = self._scale_coords(x2, y2)
            self.adb.swipe(sx1, sy1, sx2, sy2, duration)
            self.adb.invalidate_screen_cache()

    def _sleep(self, seconds: float):
        """
        带停止检测的 sleep
        """
        interval = 0.5
        elapsed = 0.0
        while elapsed < seconds and not stop_event.is_set():
            time.sleep(interval)
            elapsed += interval

    def run(self):
        """
        策略入口，由 StrategyManager 调用
        """
        if not self._connect():
            logger.error(f"[端口 {self.port}] [{self._strategy_name}] 连接失败，策略退出")
            return

        try:
            logger.info(f"[端口 {self.port}] [{self._strategy_name}] 开始执行")
            self._execute()
        except Exception as e:
            logger.error(f"[端口 {self.port}] [{self._strategy_name}] 执行异常: {e}")
        finally:
            self._disconnect()
            logger.info(f"[端口 {self.port}] [{self._strategy_name}] 执行结束")

    def detecting_hall(self):
        '''
        如果检测到时大厅return True
        '''
        pos = self._match_sift("begin.png", min_match=50)
        if pos:
            return True
        return None
    def detecting_chaolian(self):
        '''
        如果检测到时超级联赛return True
        '''
    #     70 9   230 70
        text = self._ocr_area((70,9,160,61))
        for e in text:
            if "超级" in e:
                return True
        return None
    def _ocr(self,area,context):
        text = self._ocr_area(area)
        if text:
            for e in text:
                if context in e:
                    return True
        return False
    @abstractmethod
    def _execute(self):
        """
        策略具体执行逻辑，由子类实现
        """
        pass
