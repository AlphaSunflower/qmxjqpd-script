import sys
import threading

import cv2
import numpy as np
import os
import time as _time
import json
import psutil

from services.logger_service import logger
from core.strategy_manager import stop_event
from paths import save_path, CONFIG_PATH

# 限制 OpenCV 线程数为 1，减少 CPU 占用
cv2.setNumThreads(1)

# --- CPU 亲和性：限制到一半核心，结构性降低 CPU 上限 ---
try:
    _proc = psutil.Process()
    _all_cores = _proc.cpu_affinity()
    _half = max(1, len(_all_cores) // 2)
    _proc.cpu_affinity(_all_cores[:_half])
except Exception:
    pass  # 部分平台不支持 cpu_affinity

# RapidOCR 条件导入
try:
    import onnxruntime as ort
    from rapidocr_onnxruntime import RapidOCR
    _RAPID_OCR_AVAILABLE = True
except ImportError:
    _RAPID_OCR_AVAILABLE = False

class ImageService:
    def __init__(self):
        # 串行化 C++ 操作（SIFT/FLANN/RapidOCR 非线程安全）
        self._lock = threading.Lock()

        # 模板图片缓存
        self._template_cache: dict = {}

        # RapidOCR 延迟初始化
        self._rapid_ocr = None
        self._rapid_ocr_initialized = False

        # CPU 限流状态
        self._cpu_throttle_enabled, self._cpu_threshold = self._load_cpu_throttle_config()
        self._cpu_max_wait: float = 2.0
        self._cpu_check_interval: float = 0.2
        psutil.cpu_percent(interval=None)  # 预热，首次调用返回值才有意义

        # SIFT 特征检测器
        self.sift = cv2.SIFT_create()
        # FLANN 匹配器参数
        FLANN_INDEX_KDTREE = 1
        index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
        search_params = dict(checks=50)
        self.flann = cv2.FlannBasedMatcher(index_params, search_params)
        # SIFT 模板描述符缓存：template_path -> (keypoints, descriptors)
        self._sift_desc_cache: dict = {}

    def bytes_to_cv2(self, image_bytes):
        """
        将原始二进制数据转换为 OpenCV BGR 格式。
        """
        if image_bytes is None:
            return None
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)

    def _get_template(self, template_path, grayscale=False):
        """从缓存获取模板图片，缓存未命中时从磁盘加载。"""
        cache_key = (template_path, grayscale)
        if cache_key not in self._template_cache:
            # 使用 numpy.fromfile + cv2.imdecode 代替 cv2.imread，以支持中文路径
            data = np.fromfile(template_path, dtype=np.uint8)
            if grayscale:
                template = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
            else:
                template = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if template is None:
                return None
            self._template_cache[cache_key] = template
        return self._template_cache[cache_key]

    def match_template(self, screen_img, template_path, threshold=0.8):
        """
        标准模板匹配
        screen_img: 屏幕截图 (二进制或 cv2 图像)
        template_path: 模板图片路径
        threshold: 匹配阈值 (0-1)
        返回: 匹配中心坐标 (x, y) 或 None
        """
        try:
            if isinstance(screen_img, (bytes, bytearray)):
                screen_img = self.bytes_to_cv2(screen_img)

            template = self._get_template(template_path)
            if template is None:
                logger.error(f"未找到模板图片: {template_path}")
                return None

            result = cv2.matchTemplate(screen_img, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            if max_val >= threshold:
                h, w = template.shape[:2]
                center_x = max_loc[0] + w // 2
                center_y = max_loc[1] + h // 2
                logger.debug(f"模板匹配成功: {template_path} 置信度 {max_val:.2f}")
                return (center_x, center_y)
            else:
                return None
        except Exception as e:
            logger.error(f"模板匹配出错: {e}")
            return None

    def match_template_roi(self, screen_img, template_path, roi, threshold=0.8):
        """
        带 ROI 裁剪的模板匹配，先裁剪指定区域再匹配，大幅减少计算量。
        screen_img: 屏幕截图 (二进制或 cv2 图像)
        template_path: 模板图片路径
        roi: 裁剪区域 (x, y, w, h)，基于 1280x720 设计坐标，由调用方在外部缩放
        threshold: 匹配阈值 (0-1)
        返回: 匹配中心坐标 (x, y)，基于原始屏幕坐标；未匹配返回 None
        """
        try:
            if isinstance(screen_img, (bytes, bytearray)):
                screen_img = self.bytes_to_cv2(screen_img)
            if screen_img is None:
                return None

            x, y, w, h = roi
            screen_h, screen_w = screen_img.shape[:2]
            # 裁剪 ROI 区域（边界保护）
            x1 = max(0, x)
            y1 = max(0, y)
            x2 = min(screen_w, x + w)
            y2 = min(screen_h, y + h)
            cropped = screen_img[y1:y2, x1:x2]

            template = self._get_template(template_path)
            if template is None:
                logger.error(f"未找到模板图片: {template_path}")
                return None

            # 模板尺寸不能大于裁剪区域
            th, tw = template.shape[:2]
            ch, cw = cropped.shape[:2]
            if th > ch or tw > cw:
                return None

            result = cv2.matchTemplate(cropped, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            if max_val >= threshold:
                center_x = x1 + max_loc[0] + tw // 2
                center_y = y1 + max_loc[1] + th // 2
                logger.debug(f"ROI模板匹配成功: {template_path} 置信度 {max_val:.2f}")
                return (center_x, center_y)
            return None
        except Exception as e:
            logger.error(f"ROI模板匹配出错: {e}")
            return None

    def match_sift(self, screen_img, template_path, min_match_count=30, roi=None):
        """
        使用 RANSAC 的 SIFT 特征匹配
        screen_img: 屏幕截图
        template_path: 模板图片路径
        min_match_count: 最小匹配点数量
        roi: 可选，裁剪区域 (x, y, w, h)
        返回: 匹配中心坐标 (x, y) 或 None
        """
        try:
            if isinstance(screen_img, (bytes, bytearray)):
                screen_img = self.bytes_to_cv2(screen_img)

            template = self._get_template(template_path, grayscale=True)
            if template is None:
                logger.error(f"未找到模板图片: {template_path}")
                return None

            # ROI 裁剪
            roi_offset_x, roi_offset_y = 0, 0
            if roi:
                x, y, w, h = roi
                screen_h, screen_w = screen_img.shape[:2]
                x1 = max(0, x)
                y1 = max(0, y)
                x2 = min(screen_w, x + w)
                y2 = min(screen_h, y + h)
                screen_img = screen_img[y1:y2, x1:x2]
                roi_offset_x, roi_offset_y = x1, y1

            target = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)

            # SIFT detectAndCompute + FLANN knnMatch 非线程安全，需加锁
            with self._lock:
                if template_path not in self._sift_desc_cache:
                    kp1, des1 = self.sift.detectAndCompute(template, None)
                    self._sift_desc_cache[template_path] = (kp1, des1)
                else:
                    kp1, des1 = self._sift_desc_cache[template_path]

                kp2, des2 = self.sift.detectAndCompute(target, None)

                if des1 is None or des2 is None or len(des1) < 2 or len(des2) < 2:
                    return None

                matches = self.flann.knnMatch(des1, des2, k=2)

            good = []
            for m, n in matches:
                if m.distance < 0.7 * n.distance:
                    good.append(m)

            if len(good) > min_match_count:
                src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
                dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

                M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

                if M is None:
                    return None

                h, w = template.shape
                pts = np.float32([[0, 0], [0, h - 1], [w - 1, h - 1], [w - 1, 0]]).reshape(-1, 1, 2)
                dst = cv2.perspectiveTransform(pts, M)

                center_x = int(np.mean(dst[:, 0, 0])) + roi_offset_x
                center_y = int(np.mean(dst[:, 0, 1])) + roi_offset_y

                logger.debug(f"SIFT 匹配成功: {template_path} 匹配点数 {len(good)}")
                return (center_x, center_y)
            else:
                return None

        except Exception as e:
            logger.error(f"SIFT 匹配出错: {e}")
            return None

    def match_sift_details(self, screen_img, template_path, min_match_count=30, roi=None):
        """
        使用 RANSAC 的 SIFT 特征匹配
        screen_img: 屏幕截图
        template_path: 模板图片路径
        min_match_count: 最小匹配点数量
        roi: 可选，裁剪区域 (x, y, w, h)
        返回: (匹配点数量, (center_x, center_y)) 或 (匹配点数量, None)
        """
        try:
            if isinstance(screen_img, (bytes, bytearray)):
                screen_img = self.bytes_to_cv2(screen_img)

            template = self._get_template(template_path, grayscale=True)
            if template is None:
                logger.error(f"未找到模板图片: {template_path}")
                return 0, None

            # ROI 裁剪
            roi_offset_x, roi_offset_y = 0, 0
            if roi:
                x, y, w, h = roi
                screen_h, screen_w = screen_img.shape[:2]
                x1 = max(0, x)
                y1 = max(0, y)
                x2 = min(screen_w, x + w)
                y2 = min(screen_h, y + h)
                screen_img = screen_img[y1:y2, x1:x2]
                roi_offset_x, roi_offset_y = x1, y1

            target = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)

            # SIFT detectAndCompute + FLANN knnMatch 非线程安全，需加锁
            with self._lock:
                if template_path not in self._sift_desc_cache:
                    kp1, des1 = self.sift.detectAndCompute(template, None)
                    self._sift_desc_cache[template_path] = (kp1, des1)
                else:
                    kp1, des1 = self._sift_desc_cache[template_path]

                kp2, des2 = self.sift.detectAndCompute(target, None)

                if des1 is None or des2 is None or len(des1) < 2 or len(des2) < 2:
                    return 0, None

                matches = self.flann.knnMatch(des1, des2, k=2)

            # 根据 Lowe's ratio test 筛选良好匹配
            good = []
            for m, n in matches:
                if m.distance < 0.7 * n.distance:
                    good.append(m)

            if len(good) > min_match_count:
                src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
                dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

                # 计算单应性矩阵
                M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

                if M is None:
                    return len(good), None

                h, w = template.shape
                pts = np.float32([[0, 0], [0, h - 1], [w - 1, h - 1], [w - 1, 0]]).reshape(-1, 1, 2)
                dst = cv2.perspectiveTransform(pts, M)

                # 计算变换后区域的中心
                center_x = int(np.mean(dst[:, 0, 0])) + roi_offset_x
                center_y = int(np.mean(dst[:, 0, 1])) + roi_offset_y

                logger.debug(f"SIFT 匹配成功: {template_path} 匹配点数 {len(good)}")
                return len(good), (center_x, center_y)
            else:
                return len(good), None

        except Exception as e:
            logger.error(f"SIFT 匹配出错: {e}")
            return 0, None

    def _init_rapid_ocr(self):
        """延迟初始化 RapidOCR，限制 CPU 线程数为 1"""
        if self._rapid_ocr_initialized:
            return
        with self._lock:
            if self._rapid_ocr_initialized:
                return
            self._rapid_ocr_initialized = True

            if not _RAPID_OCR_AVAILABLE:
                logger.warning("RapidOCR/onnxruntime 未安装，高精确识别不可用")
                return

            # 限制 ONNX Runtime 只使用 1 个 CPU 核心
            sess_options = ort.SessionOptions()
            sess_options.intra_op_num_threads = 1
            sess_options.inter_op_num_threads = 1

            sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

            self._rapid_ocr = RapidOCR(ort_sess_options=sess_options)
            logger.info("RapidOCR 初始化成功 (限制1个CPU核心)")

    def _load_cpu_throttle_config(self) -> tuple:
        """从 config/settings.json 读取 CPU 限流配置。
        返回 (enabled: bool, threshold: float)，默认 (True, 25.0)。
        """
        _DEFAULTS = (True, 25.0)
        try:
            saved = save_path('config/settings.json')
            config_file = saved if os.path.exists(saved) else CONFIG_PATH
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                enabled = cfg.get('cpu_throttle_enabled', _DEFAULTS[0])
                threshold = float(cfg.get('cpu_threshold_percent', _DEFAULTS[1]))
                return (enabled, threshold)
        except Exception:
            pass
        return _DEFAULTS

    def _cpu_gate(self) -> None:
        """自适应 CPU 限流门控：CPU 超过阈值时等待下降后再执行 OCR。
        使用 psutil.cpu_percent(interval=None) 非阻塞获取瞬时 CPU 使用率。
        支持 stop_event 优雅停止。
        """
        if not self._cpu_throttle_enabled:
            return

        start = _time.monotonic()
        while True:
            cpu_pct = psutil.cpu_percent(interval=None)
            if cpu_pct < self._cpu_threshold:
                return

            elapsed = _time.monotonic() - start
            if elapsed >= self._cpu_max_wait:
                logger.warning(
                    f"CPU 限流: 等待 {elapsed:.1f}s 后 CPU 仍为 {cpu_pct:.0f}%，"
                    f"超过 {self._cpu_max_wait}s 上限，强制执行 OCR"
                )
                return

            if stop_event.is_set():
                return

            logger.debug(
                f"CPU 限流: 当前 {cpu_pct:.0f}% > {self._cpu_threshold:.0f}%，"
                f"等待 {self._cpu_check_interval}s..."
            )
            _time.sleep(self._cpu_check_interval)

    def ocr_text_rapid(self, screen_img, area=None):
        """
        使用 RapidOCR 进行高精度识别
        :param screen_img: 屏幕截图（二进制或 cv2 图像）
        :param area: 裁剪区域 (x, y, w, h)
        :return: 文本列表
        """
        self._init_rapid_ocr()
        if self._rapid_ocr is None:
            return []

        try:
            if isinstance(screen_img, (bytes, bytearray)):
                screen_img = self.bytes_to_cv2(screen_img)
            if screen_img is None:
                return []
            if area:
                x, y, w, h = area
                screen_img = screen_img[y:y+h, x:x+w]

            self._cpu_gate()
            with self._lock:
                result, _ = self._rapid_ocr(screen_img)
            if result is None:
                return []

            # result 格式: [[box, text, score], ...]
            return [item[1] for item in result if item[1].strip()]
        except Exception as e:
            logger.error(f"RapidOCR 推理异常: {e}")
            return []

image_service = ImageService()
