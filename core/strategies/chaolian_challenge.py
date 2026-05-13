from core import stop_event
from core.strategies.base_chaolian import BaseChaolianStrategy
from services.logger_service import logger


class ChaolianChallengeStrategy(BaseChaolianStrategy):
    """超联挑战赛策略"""

    def _execute(self):
        self.is_excu_strategy = self.config.get('is_excu_strategy')
        self.is_inter_match = self.config.get('is_inter_match')

        self._navigate_to_chaolian_main()
        self._sleep(2)
        # 使用 _ocr_region 批量检测，一次 OCR 推理检查两个关键词
        texts_challenge = self._ocr_region((510, 300, 70, 30))
        combined_challenge = "".join(texts_challenge)
        if "挑战" not in combined_challenge:
            logger.error("没有看到挑战赛目标！")
            return
        self._tap_with_offset(550, 320, offset=1)
        self._sleep(1)

        if self._ocr((700, 580, 120, 40), "开启"):
            self._tap_with_offset(770, 600, offset=5)
            self._sleep(3)
            self._tap_with_offset(890, 570, offset=5)
            self._sleep(1)
        self._tap_with_offset(630, 600, offset=4)
        self._sleep(2)

        if self.is_inter_match:
            self._inner_match()
        else:
            self._not_inner_match()
        logger.info("已完成任务")
        return
    def _inner_match(self):
        self.count = 0
        self.loading = None
        self.status = "FREE"
        self.inner_strategy_status = 0
        self._init_stuck_detection()
        self._init_iteration_stuck_detection(max_iterations=60)
        while not stop_event.is_set():
            screen = self._grab_screen()
            made_progress = False

            if self.status == "FREE":
                if self._ocr((450, 70, 390, 50), "选择", screen=screen):
                    self._tap_with_offset(230, 360, offset=30)
                    self._sleep(1)
                    self._tap_with_offset(630, 650, offset=5)
                    self._sleep(1)
                    self.status = "CHOSE"
                    made_progress = True
                else:
                    self.count += 1
                    if self.count >= 3:
                        if self._ocr((80, 10, 110, 45), "挑战", screen=screen):
                            self.status = "CHOSE"
                            self.count = 0
                            made_progress = True

            elif self.status == "CHOSE":
                texts_title = self._ocr_region((80, 10, 110, 45), screen=screen)
                combined_title = "".join(texts_title)
                if "挑战" in combined_title:
                    made_progress = True
                    texts_first = self._ocr_region((720, 270, 110, 30), screen=screen)
                    if "首发" not in "".join(texts_first):
                        self._tap_with_offset(580, 270, offset=5)
                        self._sleep(2)
                    texts_btn = self._ocr_region((950, 650, 110, 40), screen=screen)
                    combined_btn = "".join(texts_btn)
                    if "前往" in combined_btn:
                        self._tap_with_offset(1000, 670, offset=10)
                        self._sleep(3)
                    if "进入" in combined_btn:
                        self._tap_with_offset(1000, 670, offset=10)
                        self.status = "INNER"
                else:
                    texts_enter = self._ocr_region((700, 580, 120, 40), screen=screen)
                    texts_select = self._ocr_region((450, 70, 390, 50), screen=screen)
                    if "进入" in "".join(texts_enter):
                        self._tap_with_offset(770, 610, offset=3)
                        self.status = "INNER"
                        self._sleep(1)
                        made_progress = True
                    if "选择" in "".join(texts_select):
                        self.status = "FREE"
                        made_progress = True

            elif self.status == "INNER":
                if self._match_sift("chaolian_match.png", min_match=50, screen=screen):
                    logger.debug("比赛进行中")
                    if self.is_excu_strategy:
                        self._execute_tactic()
                    made_progress = True
                elif self._match_sift("ready.png", min_match=45, screen=screen):
                    self._tap_with_offset(780, 610, offset=3)
                    logger.debug("准备阶段点击")
                    self._sleep(1)
                    made_progress = True
                elif self._match_sift("chaolian_win.png", min_match=50, screen=screen):
                    if self._ocr((950, 620, 70, 30), "返", screen=screen):
                        self.victory_count += 1
                        logger.info(f"比赛胜利，胜利{self.victory_count}场，失败{self.failure_count}场")
                        self._tap_with_offset(920, 635, offset=5)
                        self.status = "FREE"
                        self._sleep(1)
                        made_progress = True
                elif self._match_sift("chaolian_defeat.png", min_match=50, screen=screen):
                    if self._ocr((950, 620, 70, 30), "返", screen=screen):
                        self.failure_count += 1
                        logger.info("比赛失败")
                        self._tap_with_offset(920, 635, offset=5)
                        self.status = "FREE"
                        made_progress = True
                elif self._match_sift("chaolian_challenge_end.png", min_match=90, screen=screen):
                    self._tap_with_offset(905,650, offset=5)
                    self.status = "FREE"
                    logger.info("完成所有挑战赛")
                    self._sleep(4)
                    self._tap_with_offset(60, 35, offset=0)
                    made_progress = True
                    break

            if self._is_stuck(timeout=900) or self._check_iteration_stuck():
                if stop_event.is_set():
                    break
                logger.warning(f"[端口 {self.port}] 检测到卡死，尝试重连恢复...")
                if self._ensure_device():
                    self._init_stuck_detection()
                    self._init_iteration_stuck_detection(max_iterations=60)
                    continue
                else:
                    logger.error(f"[端口 {self.port}] 重连失败，退出 inner_match 循环")
                    break

            if made_progress:
                self._reset_iteration_stuck()

            self._sleep(1)

    def _not_inner_match(self):
        self.count = 0
        self.loading = None
        self.status = "FREE"
        self._init_stuck_detection()
        self._init_iteration_stuck_detection(max_iterations=60)
        while not stop_event.is_set():
            screen = self._grab_screen()
            made_progress = False

            if self.status == "FREE":
                texts_select = self._ocr_region((450, 70, 390, 50), screen=screen)
                texts_title = self._ocr_region((80, 10, 110, 45), screen=screen)
                if "选择" in "".join(texts_select):
                    self._tap_with_offset(230, 360, offset=30)
                    self._sleep(1)
                    self._tap_with_offset(630, 650, offset=5)
                    self._sleep(1)
                    self.status = "CHOSE"
                    made_progress = True
                else:
                    self.count += 1
                    if self.count >= 3:
                        if "挑战" in "".join(texts_title):
                            self.status = "CHOSE"
                            made_progress = True

            elif self.status == "CHOSE":
                texts_title = self._ocr_region((80, 10, 110, 45), screen=screen)
                texts_start = self._ocr_region((700, 580, 120, 40), screen=screen)
                if "挑战" in "".join(texts_title):
                    self._tap_with_offset(60, 35, offset=1)
                    self._sleep(1)
                    made_progress = True
                if "开始" in "".join(texts_start):
                    self._tap_with_offset(770, 600, offset=3)
                    self.status = "INNER"
                    self._sleep(1)
                    made_progress = True

            elif self.status == "INNER":
                texts_start = self._ocr_region((700, 580, 120, 40), screen=screen)
                if "开始" in "".join(texts_start):
                    logger.info("比赛结束，进入下一个挑战赛")
                    self.status = "FREE"
                    self._sleep(1)
                    self._tap_with_offset(630, 600, offset=4)
                    self._sleep(1)
                    made_progress = True

            if self._is_stuck(timeout=900) or self._check_iteration_stuck():
                if stop_event.is_set():
                    break
                logger.warning(f"[端口 {self.port}] 检测到卡死，尝试重连恢复...")
                if self._ensure_device():
                    self._init_stuck_detection()
                    self._init_iteration_stuck_detection(max_iterations=60)
                    continue
                else:
                    logger.error(f"[端口 {self.port}] 重连失败，退出 not_inner_match 循环")
                    break

            if made_progress:
                self._reset_iteration_stuck()

            self._sleep(1)
