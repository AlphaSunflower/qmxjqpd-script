import sys

import cv2
import numpy as np
import os
import io
import uuid
import concurrent.futures
import multiprocessing
multiprocessing.freeze_support()

# 打包后指定模型缓存目录，避免 RapidOCR 尝试从网络下载模型
if hasattr(sys, '_MEIPASS'):
    os.environ.setdefault('RAPIDOCR_HOME', os.path.join(sys._MEIPASS, 'rapidocr_models'))

from rapidocr_onnxruntime import RapidOCR
from services.logger_service import logger

class ImageService:
    def __init__(self):
        # 模板图片缓存
        self._template_cache: dict = {}

        # 初始化 RapidOCR（ONNX 推理，中文识别 + 方向分类）
        try:
            self.ocr = RapidOCR()
            logger.info("RapidOCR 初始化成功 (语言: 中文)。")
        except Exception as e:
            logger.error(f"RapidOCR 初始化失败: {e}")
            self.ocr = None

        # SIFT 特征检测器
        self.sift = cv2.SIFT_create()
        # FLANN 匹配器参数
        FLANN_INDEX_KDTREE = 1
        index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
        search_params = dict(checks=50)
        self.flann = cv2.FlannBasedMatcher(index_params, search_params)

        # OCR 异步线程池
        self._ocr_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="OCRWorker")
        self._ocr_pending: dict = {}  # request_id -> Future

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
            mode = 0 if grayscale else 1
            template = cv2.imread(template_path, mode)
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

    def match_sift(self, screen_img, template_path, min_match_count=30):
        """
        使用 RANSAC 的 SIFT 特征匹配
        screen_img: 屏幕截图
        template_path: 模板图片路径
        min_match_count: 最小匹配点数量
        返回: 匹配中心坐标 (x, y) 或 None
        """
        try:
            if isinstance(screen_img, (bytes, bytearray)):
                screen_img = self.bytes_to_cv2(screen_img)

            template = self._get_template(template_path, grayscale=True)
            if template is None:
                logger.error(f"未找到模板图片: {template_path}")
                return None

            target = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY) # 转换为灰度图

            # 使用 SIFT 检测关键点和描述符
            kp1, des1 = self.sift.detectAndCompute(template, None)
            kp2, des2 = self.sift.detectAndCompute(target, None)

            if des1 is None or des2 is None:
                logger.warning("SIFT: 未找到描述符。")
                return None

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
                    return None

                h, w = template.shape
                pts = np.float32([[0, 0], [0, h - 1], [w - 1, h - 1], [w - 1, 0]]).reshape(-1, 1, 2)
                dst = cv2.perspectiveTransform(pts, M)

                # 计算变换后区域的中心
                center_x = int(np.mean(dst[:, 0, 0]))
                center_y = int(np.mean(dst[:, 0, 1]))

                logger.debug(f"SIFT 匹配成功: {template_path} 匹配点数 {len(good)}")
                return (center_x, center_y)
            else:
                return None

        except Exception as e:
            logger.error(f"SIFT 匹配出错: {e}")
            return None

    def match_sift_details(self, screen_img, template_path, min_match_count=30):
        """
        使用 RANSAC 的 SIFT 特征匹配
        screen_img: 屏幕截图
        template_path: 模板图片路径
        min_match_count: 最小匹配点数量
        返回: (匹配点数量, (center_x, center_y)) 或 (匹配点数量, None)
        """
        try:
            if isinstance(screen_img, (bytes, bytearray)):
                screen_img = self.bytes_to_cv2(screen_img)

            template = self._get_template(template_path, grayscale=True)
            if template is None:
                logger.error(f"未找到模板图片: {template_path}")
                return 0, None

            target = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY) # 转换为灰度图

            # 使用 SIFT 检测关键点和描述符
            kp1, des1 = self.sift.detectAndCompute(template, None)
            kp2, des2 = self.sift.detectAndCompute(target, None)

            if des1 is None or des2 is None:
                logger.warning("SIFT: 未找到描述符。")
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
                center_x = int(np.mean(dst[:, 0, 0]))
                center_y = int(np.mean(dst[:, 0, 1]))
                
                logger.debug(f"SIFT 匹配成功: {template_path} 匹配点数 {len(good)}")
                return len(good), (center_x, center_y)
            else:
                return len(good), None

        except Exception as e:
            logger.error(f"SIFT 匹配出错: {e}")
            return 0, None

    def _parse_ocr_result(self, raw_result):
        """
        解析 RapidOCR 输出，提取文本列表。
        RapidOCR 返回格式: [[box, text, score], ...] 或 None
        """
        texts = []
        if not raw_result:
            return texts
        for item in raw_result:
            try:
                if len(item) >= 2:
                    text = item[1]
                    if text:
                        texts.append(text)
            except Exception:
                continue
        return texts

    def _ocr_engine(self, processed_img):
        """
        运行在 OCR 线程池中的推理方法。
        只执行 RapidOCR 核心推理。
        """
        result, _ = self.ocr(processed_img)
        return result

    def ocr_text_async(self, screen_img, area=None):
        """
        异步 OCR：将推理提交到线程池，立即返回 request_id。
        图片预处理在调用线程完成，推理在后台线程执行。
        :param screen_img: 屏幕截图（二进制或 cv2 图像）
        :param area: 裁剪区域 (x, y, w, h)
        :return: request_id（用于后续 ocr_poll 查询），或 None（失败时）
        """
        if self.ocr is None:
            return None

        try:
            # 图片预处理在调用线程做（快速）
            if isinstance(screen_img, (bytes, bytearray)):
                screen_img = self.bytes_to_cv2(screen_img)
            if screen_img is None:
                return None
            if area:
                x, y, w, h = area
                screen_img = screen_img[y:y+h, x:x+w]

            request_id = uuid.uuid4().hex
            future = self._ocr_executor.submit(self._ocr_engine, screen_img)
            self._ocr_pending[request_id] = future
            return request_id
        except Exception as e:
            logger.error(f"OCR 异步提交失败: {e}")
            return None

    def ocr_poll(self, request_id):
        """
        检查异步 OCR 结果（非阻塞）。
        :param request_id: ocr_text_async 返回的 id
        :return: 文本列表（完成时），或 None（未完成/失败/不存在）
        """
        if request_id not in self._ocr_pending:
            return None
        future = self._ocr_pending[request_id]
        if not future.done():
            return None
        try:
            raw = future.result()
            del self._ocr_pending[request_id]
            return self._parse_ocr_result(raw)
        except Exception as e:
            logger.error(f"OCR 推理异常: {e}")
            del self._ocr_pending[request_id]
            return []

    def ocr_text(self, screen_img, area=None, stop_check=None):
        """
        同步 OCR，兼容旧接口。
        使用 Future.result(timeout) 实现可中断等待，支持 stop_check 回调。
        """
        if self.ocr is None:
            return []
        request_id = self.ocr_text_async(screen_img, area)
        if request_id is None:
            return []
        if request_id not in self._ocr_pending:
            return []
        future = self._ocr_pending[request_id]
        import time
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if stop_check and stop_check():
                return []
            try:
                raw = future.result(timeout=0.2)
                del self._ocr_pending[request_id]
                return self._parse_ocr_result(raw)
            except concurrent.futures.TimeoutError:
                continue
        logger.warning("OCR 同步等待超时")
        return []

    def get_pixel_color(self, screen_img, x, y):
        """
        获取图像指定坐标的颜色（BGR 格式）。
        支持二进制截图数据或 cv2 图像对象。
        :param screen_img: 屏幕截图（二进制数据或 cv2 图像）
        :param x: 横坐标
        :param y: 纵坐标
        :return: (B, G, R) 元组，或越界/无效时返回 None
        """
        try:
            if isinstance(screen_img, (bytes, bytearray)):
                screen_img = self.bytes_to_cv2(screen_img)

            if screen_img is None:
                return None

            h, w = screen_img.shape[:2]
            if x < 0 or x >= w or y < 0 or y >= h:
                logger.warning(f"坐标 ({x}, {y}) 超出图像范围 ({w}x{h})")
                return None

            pixel = screen_img[y, x]
            if len(pixel) == 3:
                return (int(pixel[0]), int(pixel[1]), int(pixel[2]))
            return None
        except Exception as e:
            logger.error(f"获取像素颜色失败: {e}")
            return None

    def is_color_in_range(self, color, lower, upper):
        """
        判断颜色是否在指定阈值范围内（BGR 格式）。
        :param color: (B, G, R) 颜色值
        :param lower: (B, G, R) 下界
        :param upper: (B, G, R) 上界
        :return: 在范围内返回 True，否则返回 False
        """
        if color is None:
            return False
        b, g, r = color
        lb, lg, lr = lower
        ub, ug, ur = upper
        return (lb <= b <= ub) and (lg <= g <= ug) and (lr <= r <= ur)

    def wait_for_color(self, screen_img, x, y, lower, upper,
                       timeout=10.0, interval=0.5):
        """
        等待指定坐标的颜色进入阈值范围。
        :param screen_img: 屏幕截图（由 ADBService.screencap() 返回的二进制数据）
        :param x: 横坐标
        :param y: 纵坐标
        :param lower: (B, G, R) 下界
        :param upper: (B, G, R) 上界
        :param timeout: 超时时间（秒）
        :param interval: 检测间隔（秒）
        :return: 颜色进入范围时返回 True，超时返回 False
        """
        import time
        start = time.time()
        while time.time() - start < timeout:
            color = self.get_pixel_color(screen_img, x, y)
            if color is not None:
                logger.debug(f"坐标 ({x},{y}) 当前颜色: BGR{color}，阈值: {lower}-{upper}")
            if self.is_color_in_range(color, lower, upper):
                logger.debug(f"坐标 ({x},{y}) 颜色匹配阈值 BGR{color}")
                return True
            time.sleep(interval)
        logger.debug(f"等待颜色超时: 坐标 ({x},{y}) 始终未匹配阈值 {lower}-{upper}")
        return False

image_service = ImageService()
