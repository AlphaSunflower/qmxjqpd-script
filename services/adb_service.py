import os
import time
import subprocess
from ppadb.client import Client as AdbClient
from services.logger_service import logger
import json
import io
from PIL import Image


class ADBService:
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

    def connect(self):
        """
        连接到 ADB 服务器和设备
        返回: 连接成功返回 True，否则返回 False
        """
        try:
            subprocess.run(
                ["adb", "start-server"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            self.client = AdbClient(host="127.0.0.1", port=5037)

            device_address = f"{self.host}:{self.port}"
            logger.info(f"[端口 {self.port}] 正在连接设备: {device_address}...")

            subprocess.run(
                ["adb", "connect", device_address],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            devices = self.client.devices()
            for device in devices:
                if device.serial == device_address:
                    self.device = device
                    logger.info(f"[端口 {self.port}] 成功连接到设备: {device_address}")
                    return True

            logger.error(
                f"[端口 {self.port}] 未找到目标设备 {device_address}，"
                f"当前可用设备: {[d.serial for d in devices]}"
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
                stderr=subprocess.DEVNULL
            )
            self.device = None
            self.client = None
        except Exception as e:
            logger.warning(f"[端口 {self.port}] 断开连接时出错: {e}")

    def screencap(self):
        """
        截取屏幕并返回二进制数据
        返回: 图片的二进制数据，失败返回 None
        """
        if not self.device:
            logger.error(f"[端口 {self.port}] 设备未连接")
            return None
        try:
            result = self.device.screencap()
            return result
        except Exception as e:
            logger.error(f"[端口 {self.port}] 截图失败: {e}")
            return None

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
            logger.debug(f"[端口 {self.port}] 点击坐标: ({x}, {y})")
        except Exception as e:
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
            logger.error(f"[端口 {self.port}] 滑动失败: {e}")

    def shell(self, cmd):
        """
        执行 ADB Shell 命令
        cmd: 命令字符串
        """
        if not self.device:
            return None
        return self.device.shell(cmd)

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
