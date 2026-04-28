import sys

import cv2
import numpy as np
import os
import io
import uuid
import concurrent.futures
import multiprocessing
multiprocessing.freeze_support()
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_pir_apply_inplace_pass"] = "0"
os.environ["FLAGS_enable_new_executor"] = "0"
os.environ["FLAGS_use_mkldnn"] = "0"
from paddleocr import PaddleOCR
# from paddlex import create_model
from services.logger_service import logger
from PIL import Image
def get_real_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.abspath(".")
class ImageService:
    def __init__(self):
        # 初始化 PaddleOCR
        # use_angle_cls=True 启用方向分类
        # lang='ch' 支持中文识别 (chinese)
        # 默认使用 ch 模型，它同时支持中文、英文和数字
        try:
            import os
            import sys
            
            # 获取打包后的资源路径
            if hasattr(sys, '_MEIPASS'):
                model_dir = os.path.join(sys._MEIPASS, 'paddleocr', 'ppocr')
            else:
                model_dir = None

            # 移除 show_log 参数，新版本 PaddleOCR 可能不支持
            ocr_params = {
                'use_angle_cls': True,
                'lang': 'ch',
                'enable_mkldnn': False,
                'device': 'cpu'
            }

            # 如果是打包环境，尝试指定模型路径
            if model_dir and os.path.exists(model_dir):
                ocr_params['det_model_dir'] = os.path.join(model_dir, 'models', 'det')
                ocr_params['rec_model_dir'] = os.path.join(model_dir, 'models', 'rec')
                ocr_params['cls_model_dir'] = os.path.join(model_dir, 'models', 'cls')

            self.ocr = PaddleOCR(**ocr_params)
            # self.ocr = create_model("OCR", lang="ch")
            # 尝试抑制 PaddleOCR 自身的日志输出 (如果需要)
            import logging
            logging.getLogger("ppocr").setLevel(logging.ERROR)

            logger.info("PaddleOCR 初始化成功 (语言: 中文/ch)。")
        except Exception as e:
            logger.error(f"PaddleOCR 初始化失败: {e}")
            self.ocr = None

        # SIFT 特征检测器
        self.sift = cv2.SIFT_create()
        # FLANN 匹配器参数
        FLANN_INDEX_KDTREE = 1
        index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
        search_params = dict(checks=50)
        self.flann = cv2.FlannBasedMatcher(index_params, search_params)

        # OCR 异步线程池
        self._ocr_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="OCRWorker")
        self._ocr_pending: dict = {}  # request_id -> Future

    def bytes_to_cv2(self, image_bytes):
        """
        将原始二进制数据转换为 OpenCV 图像格式
        image_bytes: 图片的二进制数据
        返回: OpenCV BGR 格式的图像
        """
        if image_bytes is None:
            return None
        image = Image.open(io.BytesIO(image_bytes))
        image_np = np.array(image)
        # 将 RGB 转换为 BGR
        image_bgr = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
        return image_bgr

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
            
            template = cv2.imread(template_path)
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

            template = cv2.imread(template_path, 0) # 读取为灰度图
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

            template = cv2.imread(template_path, 0) # 读取为灰度图
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

    def ocr_text(self, screen_img, area=None):
        """
        识别图像中的文字
        screen_img: 屏幕截图
        area: 裁剪区域 (x, y, w, h)
        返回: 识别到的文本列表
        """
        if self.ocr is None:
            return []
            
        try:
            if isinstance(screen_img, (bytes, bytearray)):
                screen_img = self.bytes_to_cv2(screen_img)

            if area:
                x, y, w, h = area
                screen_img = screen_img[y:y+h, x:x+w]

            # 调试：保存送入 OCR 的图片，方便分析
            # debug_path = "logs/debug_ocr_input.png"
            # cv2.imwrite(debug_path, screen_img)
            # logger.debug(f"已保存 OCR 输入图片至 {debug_path}")

            # PaddleOCR 的 predict 方法在某些版本中可能存在参数兼容性问题
            # 尝试直接调用，如果失败则使用位置参数
                # 尝试标准调用，明确指定参数名以避免位置参数混淆
                # 显式关闭 cls (方向分类)，对于游戏截图通常不需要且可能导致误判
                # 如果发现文字方向识别错误，可以改为 cls=True
            result = self.ocr.ocr(screen_img)

            texts = []
            if result:
                logger.debug(f"OCR 原始返回结果类型: {type(result)}")

                # 检查是否为 PaddleX / New PaddleOCR 格式 (result[0] 是 dict)
                if len(result) > 0 and isinstance(result[0], dict) and 'rec_texts' in result[0]:
                    res_dict = result[0]
                    texts_list = res_dict.get('rec_texts', [])
                    scores_list = res_dict.get('rec_scores', [])

                    for i, text in enumerate(texts_list):
                        score = scores_list[i] if i < len(scores_list) else 1.0
                        logger.debug(f"OCR 识别: '{text}' (置信度: {score:.2f})")
                        texts.append(text)
                else:
                    # PaddleOCR 返回的结构可能是 [ [ [points], (text, conf) ], ... ]
                    # 也可能是空列表 [] 如果没识别到
                    # 注意：result[0] 在某些版本/情况下可能是 None
                    lines = result[0] if result[0] is not None else []

                    for line in lines:
                        try:
                            # line format: [[points], (text, confidence)]
                            # 或者 [[points], text]
                            if line and len(line) >= 2:
                                content = line[1]
                                text = ""
                                confidence = 1.0

                                if isinstance(content, (list, tuple)) and len(content) >= 1:
                                    text = content[0]
                                    confidence = content[1] if len(content) > 1 else 1.0
                                elif isinstance(content, str):
                                    text = content
                                    confidence = 1.0 # 无法获取置信度
                                else:
                                    logger.warning(f"OCR line[1] 格式未知: {type(content)} - {content}")
                                    continue

                                logger.debug(f"OCR 识别: '{text}' (置信度: {confidence:.2f})")
                                texts.append(text)
                        except Exception as e:
                            logger.error(f"解析 OCR 行数据失败: {e}, line数据: {line}")

            
            logger.debug(f"OCR 最终结果列表: {texts}")
            return texts
        except Exception as e:
            logger.error(f"OCR 错误: {e}")
            return []

    def _parse_ocr_result(self, raw_result):
        """
        解析 PaddleOCR 原始输出，提取文本列表。
        供 ocr_text 和 ocr_poll 共用。
        """
        texts = []
        if not raw_result:
            return texts

        if len(raw_result) > 0 and isinstance(raw_result[0], dict) and 'rec_texts' in raw_result[0]:
            res_dict = raw_result[0]
            texts_list = res_dict.get('rec_texts', [])
            scores_list = res_dict.get('rec_scores', [])
            for i, text in enumerate(texts_list):
                score = scores_list[i] if i < len(scores_list) else 1.0
                texts.append(text)
        else:
            lines = raw_result[0] if raw_result[0] is not None else []
            for line in lines:
                try:
                    if line and len(line) >= 2:
                        content = line[1]
                        if isinstance(content, (list, tuple)) and len(content) >= 1:
                            text = content[0]
                        elif isinstance(content, str):
                            text = content
                        else:
                            continue
                        texts.append(text)
                except Exception:
                    continue
        return texts

    def _ocr_engine(self, processed_img):
        """
        运行在 OCR 线程池中的推理方法。
        只执行 PaddleOCR 核心推理，持有 GIL 的操作在此完成。
        """
        return self.ocr.ocr(processed_img)

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

    def ocr_text(self, screen_img, area=None):
        """
        同步 OCR，兼容旧接口。
        内部使用异步提交 + 轮询等待，不阻塞 Tkinter 主线程。
        """
        if self.ocr is None:
            return []
        request_id = self.ocr_text_async(screen_img, area)
        if request_id is None:
            return []
        import time
        for _ in range(50):
            result = self.ocr_poll(request_id)
            if result is not None:
                return result
            time.sleep(0.1)
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
