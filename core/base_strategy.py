from __future__ import annotations
import os
import sys
import time
import random
from abc import ABC, abstractmethod

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.adb_service import ADBService
from services.image_service import image_service
from services.logger_service import logger
from core.strategy_manager import stop_event, register_screen_size, update_strategy_stats


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

        self.screen_size: tuple = None
        self.victory_count = 0
        self.failure_count = 0
        self._strategy_name = self.__class__.__name__
        self._consecutive_screen_failures = 0
        self._max_screen_failures = 5
        self._screen_fail_since = None

    def _ensure_device(self) -> bool:
        """
        确保设备可用。连续截图失败超过阈值时触发 ADB 重连。
        :return: 设备可用返回 True，不可恢复返回 False
        """
        if self.adb is None:
            return False
        if self.adb.is_device_ready():
            return True
        logger.warning(f"[端口 {self.port}] 设备无响应，尝试重连...")
        success = self.adb.reconnect(stop_check=stop_event.is_set)
        if success:
            self._consecutive_screen_failures = 0
            self._screen_fail_since = None
            return True
        return False

    def _init_stuck_detection(self):
        """初始化卡死检测：记录初始状态和时间。"""
        self._last_status = None
        self._last_status_time = time.monotonic()

    def _is_stuck(self, timeout=180):
        """检查当前状态是否卡死（状态未变化超过指定秒数）。INNER 状态使用更长超时。"""
        if stop_event.is_set():
            return True
        if self.status != self._last_status:
            self._last_status = self.status
            self._last_status_time = time.monotonic()
            return False
        elapsed = time.monotonic() - self._last_status_time
        effective_timeout = 600 if self.status == "INNER" else timeout
        if elapsed > effective_timeout:
            logger.warning(f"[端口 {self.port}] 卡死检测：状态 '{self.status}' 已持续 {elapsed:.0f}s，触发恢复")
            return True
        return False

    def _init_iteration_stuck_detection(self, max_iterations: int = 200):
        """初始化迭代卡死检测：追踪无进展的循环迭代次数。"""
        self._stuck_iteration_count = 0
        self._stuck_max_iterations = max_iterations

    def _check_iteration_stuck(self) -> bool:
        """检查是否迭代卡死（连续多轮循环无任何进展）。"""
        self._stuck_iteration_count += 1
        if self._stuck_iteration_count >= self._stuck_max_iterations:
            logger.warning(
                f"[端口 {self.port}] 迭代卡死检测：{self._stuck_max_iterations} 轮无进展，触发恢复"
            )
            return True
        return False

    def _reset_iteration_stuck(self):
        """重置迭代卡死计数器（有进展时调用）。"""
        self._stuck_iteration_count = 0

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

    def _match_template(self, template_name: str, threshold: float = 0.75) -> tuple:
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

    def _grab_screen(self):
        """
        截取当前屏幕。连续失败超过阈值时触发重连并重试一次。
        :return: 屏幕截图二进制数据，失败返回 None
        """
        if self.adb is None:
            return None
        result = self.adb.screencap()
        if result is None:
            self._consecutive_screen_failures += 1
            if self._screen_fail_since is None:
                self._screen_fail_since = time.time()
            if self._consecutive_screen_failures >= self._max_screen_failures:
                logger.warning(
                    f"[端口 {self.port}] 连续 {self._consecutive_screen_failures} 次截图失败，触发重连..."
                )
                if self._ensure_device():
                    result = self.adb.screencap(use_cache=False)
                    if result is not None:
                        self._consecutive_screen_failures = 0
                        self._screen_fail_since = None
        else:
            self._consecutive_screen_failures = 0
            self._screen_fail_since = None
        return result

    def _match_sift(self, template_name: str, min_match: int = 30, roi: tuple = None, screen=None) -> tuple:
        """
        SIFT 特征匹配查找目标
        :param template_name: 模板图片文件名
        :param min_match: 最小匹配点数
        :param roi: 可选，裁剪区域 (x, y, w, h)，基于 1280x720 设计坐标
        :param screen: 可选，预截取的屏幕数据
        :return: 匹配到的中心坐标 (x, y)，未匹配到返回 None
        """
        if self.adb is None or self.image is None:
            return None

        if screen is None:
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

        # 将 ROI 坐标从 1280x720 缩放到实际屏幕坐标
        scaled_roi = None
        if roi:
            sx, sy = self._scale_coords(roi[0], roi[1])
            sw = int(roi[2] * (self.screen_size[0] / 1280)) if self.screen_size else roi[2]
            sh = int(roi[3] * (self.screen_size[0] / 1280)) if self.screen_size else roi[3]
            scaled_roi = (sx, sy, sw, sh)

        result = self.image.match_sift(screen, template_path, min_match, roi=scaled_roi)
        if result is None:
            return None

        # 将实际屏幕坐标反向缩放为 1280x720 设计坐标
        if self.screen_size:
            scale = self.screen_size[0] / 1280
            return (int(result[0] / scale), int(result[1] / scale))
        return result

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

    def _ocr_area(self, area: tuple = None, screen=None) -> list:
        """
        OCR 识别屏幕文字，同步版本。
        :param area: 裁剪区域 (x, y, w, h)，None 表示全屏，坐标基于 1280x720
        :param screen: 可选，预截取的屏幕数据，为 None 时自动截屏
        :return: 识别到的文本列表
        """
        if self.adb is None or self.image is None:
            return []

        if screen is None:
            screen = self.adb.screencap()
        if screen is None:
            return []

        if area:
            sx, sy = self._scale_coords(area[0], area[1])
            sw, sh = self._scale_coords(area[2], area[3])
            return self.image.ocr_text_rapid(screen, area=(sx, sy, sw, sh))

        return self.image.ocr_text_rapid(screen)

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
        interval = min(1.0, seconds)
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
            update_strategy_stats(self.port, mode=self._strategy_name, status="运行中", victory=0, failure=0)
            self._execute()
        except Exception as e:
            logger.error(f"[端口 {self.port}] [{self._strategy_name}] 执行异常: {e}")
        finally:
            update_strategy_stats(self.port, status="已完成")
            self._disconnect()
            logger.info(f"[端口 {self.port}] [{self._strategy_name}] 执行结束")

    def detecting_hall(self):
        '''
        如果检测到时大厅return True
        '''
        pos = self._match_sift("begin.png", min_match=50)
        if pos:
            return pos
        return None
    def detecting_chaolian(self):
        '''
        如果检测到时超级联赛return True
        '''
        pos = self._match_sift("超级_title.png", min_match=50)
        return pos is not None
    def _ocr(self, area, context, screen=None):
        text = self._ocr_area(area, screen=screen)
        logger.debug("识别到的ocr" + str(text))
        if not text:
            return False

        # 将所有识别结果拼接成一个字符串，解决文本框分割问题
        combined = "".join(text)

        # 精确匹配
        if context in combined:
            return True

        # 模糊匹配：逐字符比较，容忍部分识别错误
        return self._fuzzy_match(context, combined)

    def _fuzzy_match(self, keyword: str, text: str, tolerance: float = 0.5) -> bool:
        """
        模糊匹配，容忍部分字符识别错误
        :param keyword: 要匹配的关键词
        :param text: 识别到的文本
        :param tolerance: 匹配容忍度 (0-1)，0.5 表示 50% 字符匹配即可
        :return: 匹配成功返回 True
        """
        if not keyword or not text:
            return False

        keyword_len = len(keyword)
        text_len = len(text)

        # 关键词长度为 1 时，直接检查字符是否存在
        if keyword_len == 1:
            return keyword in text

        # 计算需要匹配的最少字符数（至少匹配 1 个字符）
        min_match = max(1, int(keyword_len * tolerance))

        # 滑动窗口检查每个可能的子串
        for i in range(text_len - keyword_len + 1):
            substring = text[i:i + keyword_len]
            # 计算匹配的字符数
            match_count = sum(1 for k, s in zip(keyword, substring) if k == s)
            if match_count >= min_match:
                return True

        return False

    def _ocr_region(self, area: tuple, screen=None) -> list:
        """
        OCR 一次，返回该区域所有文本列表，供调用方检查多个关键词。
        相比多次调用 _ocr()，本方法只需截图+推理一次。
        :param area: 裁剪区域 (x, y, w, h)，基于 1280x720
        :param screen: 可选，预截取的屏幕数据
        :return: 文本列表
        """
        return self._ocr_area(area, screen=screen)
    def computer_turn_off(self):
        """执行系统关机（5 秒延迟，可在终端执行 shutdown /a 取消）"""
        import subprocess
        logger.info("将在 5 秒后关机，可在终端执行 shutdown /a 取消")
        subprocess.run(["shutdown", "/s", "/t", "5"])

    def _dancing(self):
        #跳舞
        while not stop_event.is_set():
            if not self.detecting_hall():
                if self.detecting_chaolian():
                    self._tap_with_offset(60, 35, offset=5)
                    self._sleep(2)
                #以及其他地方
            else:
                break
        self._tap_with_offset(1150,560,offset=5)
        finish = False
        #检查
        self.dance_start_time = 0
        while not stop_event.is_set():
            if self._match_sift("speed.png", min_match=30):
                self._sleep(2)
                if self.dance_start_time == 0:
                    self._tap_with_offset(1230, 430, offset=0)
                    self.dance_start_time = time.time()
                else:
                    if time.time() - self.dance_start_time > 780:
                        self._tap_with_offset(1230, 430, offset=0)
                        self._sleep(2)
                        self._tap_with_offset(1175, 35, offset=0)
                        self._sleep(3)
                        self._tap_with_offset(1150,560,offset=0)
                        finish = True
                    else:
                        self._sleep(5)
            if finish:
                break

    @abstractmethod
    def _execute(self):
        """
        策略具体执行逻辑，由子类实现
        """
        pass
