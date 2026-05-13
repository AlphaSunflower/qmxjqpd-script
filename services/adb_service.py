import os
import threading
import time
import subprocess
import sys
from ppadb.client import Client as AdbClient
from services.logger_service import logger
import json
import io
from PIL import Image

# Windows 下防止 subprocess 弹出控制台黑窗
_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0


class ADBService:
    MAX_RECONNECT_ATTEMPTS = 5
    RECONNECT_BASE_DELAY = 2.0

    def __init__(self, port=None, host="127.0.0.1"):
        """
        初始化 ADB 服务
        port: ADB 设备端口，默认为 16384（主模拟器）
        host: ADB 主机地址，默认 127.0.0.1
        """
        self.client = None
        self.device = None
        self.host = host
        self.port = port if port is not None else 16384
        self._screen_cache = None
        self._screen_cache_time = 0.0
        self._cache_lock = threading.Lock()
        self._reconnect_count = 0
        self._last_reconnect_time = 0.0
        self._reconnect_lock = threading.Lock()

    @staticmethod
    def _is_connection_error(exception: Exception) -> bool:
        """检测异常是否为设备断连错误。"""
        msg = str(exception).lower()
        if "device" in msg and ("not found" in msg or "offline" in msg):
            return True
        if "connection" in msg and ("refused" in msg or "reset" in msg or "broken pipe" in msg):
            return True
        if isinstance(exception, RuntimeError):
            return True
        return False

    def is_device_ready(self) -> bool:
        """快速检测设备是否已连接且响应正常。"""
        if not self.device:
            return False
        try:
            result = self.device.shell("echo ok")
            return result is not None and "ok" in str(result)
        except Exception:
            return False

    def reconnect(self, stop_check=None) -> bool:
        """
        尝试完整重连设备，指数退避。
        :param stop_check: 可选 callable，返回 True 时中断等待
        :return: 重连成功返回 True
        """
        with self._reconnect_lock:
            if self._reconnect_count > 0 and (time.time() - self._last_reconnect_time) < 30:
                return self.is_device_ready()

            self._reconnect_count += 1
            self._last_reconnect_time = time.time()

            if self._reconnect_count > self.MAX_RECONNECT_ATTEMPTS:
                logger.error(
                    f"[端口 {self.port}] 已达到最大重连次数 ({self.MAX_RECONNECT_ATTEMPTS})，放弃重连"
                )
                return False

            delay = self.RECONNECT_BASE_DELAY * (2 ** (self._reconnect_count - 1))
            logger.warning(
                f"[端口 {self.port}] 设备断开，将在 {delay:.0f}s 后尝试重连 "
                f"(第 {self._reconnect_count}/{self.MAX_RECONNECT_ATTEMPTS} 次)..."
            )

            if stop_check:
                waited = 0.0
                while waited < delay:
                    if stop_check():
                        return False
                    time.sleep(min(1.0, delay - waited))
                    waited += 1.0
            else:
                time.sleep(delay)

            try:
                self.disconnect()
            except Exception:
                pass

            success = self.connect()
            if success:
                self._reconnect_count = 0
                self.invalidate_screen_cache()
                logger.info(f"[端口 {self.port}] 重连成功")
            else:
                logger.error(f"[端口 {self.port}] 重连失败")

            return success

    def reset_reconnect_counter(self):
        """重置重连计数器。"""
        with self._reconnect_lock:
            self._reconnect_count = 0

    def connect(self, retries: int = 3, retry_delay: float = 1.0):
        """
        连接到 ADB 服务器和设备，支持重试。
        :param retries: 最大重试次数（查找设备阶段）
        :param retry_delay: 重试间隔（秒）
        返回: 连接成功返回 True，否则返回 False
        """
        try:
            subprocess.run(
                ["adb", "start-server"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_CREATE_NO_WINDOW,
            )

            self.client = AdbClient(host="127.0.0.1", port=5037)

            device_address = f"{self.host}:{self.port}"
            logger.info(f"[端口 {self.port}] 正在连接设备: {device_address}...")

            subprocess.run(
                ["adb", "connect", device_address],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_CREATE_NO_WINDOW,
            )

            # 重试查找设备（adb connect 后设备注册存在延迟）
            for attempt in range(1, retries + 1):
                time.sleep(retry_delay)
                devices = self.client.devices()
                for device in devices:
                    if device.serial == device_address:
                        self.device = device
                        logger.info(f"[端口 {self.port}] 成功连接到设备: {device_address}")
                        return True

                if attempt < retries:
                    logger.warning(
                        f"[端口 {self.port}] 未找到设备 {device_address}，"
                        f"第 {attempt}/{retries} 次重试..."
                    )

            logger.error(
                f"[端口 {self.port}] 未找到目标设备 {device_address}，"
                f"当前可用设备: {[d.serial for d in self.client.devices()]}"
            )
            return False

        except Exception as e:
            logger.error(f"[端口 {self.port}] ADB 连接失败: {e}")
            return False

    def disconnect(self):
        """
        断开 ADB 连接
        """
        try:
            device_address = f"{self.host}:{self.port}"
            subprocess.run(
                ["adb", "disconnect", device_address],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_CREATE_NO_WINDOW,
            )
            self.device = None
            self.client = None
        except Exception as e:
            logger.warning(f"[端口 {self.port}] 断开连接时出错: {e}")

    def screencap(self, use_cache: bool = True, cache_ttl: float = 0.3):
        """
        截取屏幕并返回二进制数据。连接错误时自动重连并重试一次。
        use_cache: 是否使用缓存，默认 True
        cache_ttl: 缓存有效期（秒），默认 0.3
        返回: 图片的二进制数据，失败返回 None
        """
        if not self.device:
            logger.error(f"[端口 {self.port}] 设备未连接")
            return None

        if use_cache:
            with self._cache_lock:
                if self._screen_cache is not None:
                    if time.time() - self._screen_cache_time < cache_ttl:
                        return self._screen_cache

        for attempt in range(2):
            try:
                result = self.device.screencap()
                if use_cache:
                    with self._cache_lock:
                        self._screen_cache = result
                        self._screen_cache_time = time.time()
                return result
            except Exception as e:
                if not self._is_connection_error(e):
                    logger.error(f"[端口 {self.port}] 截图失败: {e}")
                    return None
                if attempt == 0:
                    logger.warning(f"[端口 {self.port}] 截图时检测到设备断开: {e}")
                    self.invalidate_screen_cache()
                    if not self.reconnect():
                        return None
                else:
                    logger.error(f"[端口 {self.port}] 重连后截图仍然失败: {e}")
                    return None

    def invalidate_screen_cache(self):
        """清除截图缓存，在点击/滑动等改变屏幕的操作后调用"""
        with self._cache_lock:
            self._screen_cache = None
            self._screen_cache_time = 0.0

    def screencap_area(self, x, y, w, h):
        """
        截取屏幕指定区域并返回二进制数据
        x, y, w, h: 区域坐标和宽高
        返回: 图片的二进制数据，失败返回 None
        """
        full_img_bytes = self.screencap()
        if not full_img_bytes:
            return None

        try:
            image = Image.open(io.BytesIO(full_img_bytes))
            cropped = image.crop((x, y, x + w, y + h))

            img_byte_arr = io.BytesIO()
            cropped.save(img_byte_arr, format='PNG')
            return img_byte_arr.getvalue()
        except Exception as e:
            logger.error(f"[端口 {self.port}] 区域截图失败: {e}")
            return None

    def tap(self, x, y=None):
        """
        点击屏幕指定坐标
        x: 横坐标，或元组 (x, y)
        y: 纵坐标（当 x 为元组时，此参数忽略）
        """
        if isinstance(x, tuple):
            x, y = x[0], x[1]

        if not self.device:
            return
        try:
            self.device.shell(f"input tap {int(x)} {int(y)}")
        except Exception as e:
            if self._is_connection_error(e):
                logger.warning(f"[端口 {self.port}] 点击时设备断开: {e}")
                self.reconnect()
            else:
                logger.error(f"[端口 {self.port}] 点击失败: {e}")

    def swipe(self, x1, y1, x2, y2, duration=500):
        """
        滑动屏幕
        x1, y1: 起始坐标
        x2, y2: 终点坐标
        duration: 滑动持续时间（毫秒）
        """
        if not self.device:
            return
        try:
            self.device.shell(f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {int(duration)}")
            logger.debug(f"[端口 {self.port}] 从 ({x1}, {y1}) 滑动到 ({x2}, {y2})")
        except Exception as e:
            if self._is_connection_error(e):
                logger.warning(f"[端口 {self.port}] 滑动时设备断开: {e}")
                self.reconnect()
            else:
                logger.error(f"[端口 {self.port}] 滑动失败: {e}")

    def shell(self, cmd):
        """
        执行 ADB Shell 命令
        cmd: 命令字符串
        """
        if not self.device:
            return None
        try:
            return self.device.shell(cmd)
        except Exception as e:
            if self._is_connection_error(e):
                logger.warning(f"[端口 {self.port}] shell 时设备断开: {e}")
                self.reconnect()
            else:
                logger.error(f"[端口 {self.port}] shell 失败: {e}")
            return None

    def get_screen_size(self) -> tuple:
        """
        获取设备屏幕分辨率（自动处理屏幕旋转，返回逻辑分辨率）
        依次尝试 dumpsys display / wm size 两种方式
        :return: (width, height)，失败返回 None
        """
        def try_dumpsys():
            try:
                output = self.device.shell("dumpsys display")
                output = output.strip()
                w, h = None, None
                for line in output.splitlines():
                    line = line.strip()
                    if line.startswith("mDisplayWidth="):
                        w = int(line.split("=")[1])
                    elif line.startswith("mDisplayHeight="):
                        h = int(line.split("=")[1])
                    if w is not None and h is not None:
                        break
                if w and h:
                    return (w, h)
            except Exception:
                pass
            return None

        def try_wm_size():
            try:
                output = self.device.shell("wm size")
                output = output.strip()
                if not output:
                    return None
                parts = output.split(":")[-1].strip().split("x")
                if len(parts) == 2:
                    raw_w = int(parts[0])
                    raw_h = int(parts[1])
                    # wm size 输出可能不反映旋转，取较大值作为宽
                    w, h = max(raw_w, raw_h), min(raw_w, raw_h)
                    return (w, h)
            except Exception:
                pass
            return None

        for name, func in [("dumpsys display", try_dumpsys), ("wm size", try_wm_size)]:
            result = func()
            if result:
                return result

        return None
