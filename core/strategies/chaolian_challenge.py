from core import stop_event
from core.strategies.base_chaolian import BaseChaolianStrategy
from services.logger_service import logger


class ChaolianChallengeStrategy(BaseChaolianStrategy):
    """超联挑战赛策略"""

    def _execute(self):
        self.is_excu_strategy = self.config.get('is_excu_strategy')
        self.is_inter_match = self.config.get('is_inter_match')

        self._navigate_to_chaolian_main()

        if not self._ocr((510, 300, 70, 30), "挑战"):
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

    def _inner_match(self):
        self.count = 0
        self.loading = None
        self.status = "FREE"
        self.inner_strategy_status = 0
        while not stop_event.is_set():
            if self.status == "FREE":
                if self._ocr((450, 70, 390, 50), "选择"):
                    self._tap_with_offset(230, 360, offset=30)
                    self._sleep(1)
                    self._tap_with_offset(630, 650, offset=5)
                    self._sleep(1)
                    self.status = "CHOSE"
                else:
                    self.count += 1
                    if self.count >= 3:
                        if self._ocr((80, 10, 110, 45), "挑战"):
                            self.status = "CHOSE"
                            self.count = 0

            elif self.status == "CHOSE":
                if self._ocr((80, 10, 110, 45), "挑战"):
                    if not self._ocr((720, 270, 110, 30), "首发"):
                        self._tap_with_offset(580, 270, offset=5)
                        self._sleep(2)
                    if self._ocr((950, 650, 110, 40), "前往"):
                        self._tap_with_offset(1000, 670, offset=10)
                        self._sleep(3)
                    if self._ocr((950, 650, 110, 40), "进入"):
                        self._tap_with_offset(1000, 670, offset=10)
                        self.status = "INNER"
                else:
                    if self._ocr((700, 580, 120, 40), "进入"):
                        self._tap_with_offset(770, 610, offset=3)
                        self.status = "INNER"
                        self._sleep(1)
                    if self._ocr((450, 70, 390, 50), "选择"):
                        self.status = "FREE"

            elif self.status == "INNER":
                if self._match_sift("chaolian_match.png", 50):
                    logger.debug("比赛进行中")
                    if self.is_excu_strategy:
                        self._execute_tactic()
                if self._match_sift("ready.png", 50):
                    self._tap_with_offset(780, 610, offset=3)
                    logger.debug("准备阶段点击")
                    self._sleep(1)
                if self._match_sift("chaolian_win.png", 50):
                    if self._ocr((950, 620, 70, 30), "返回"):
                        self.victory_count += 1
                        logger.info(f"比赛胜利，胜利{self.victory_count}场，失败{self.failure_count}场")
                        self._tap_with_offset(920, 635, offset=5)
                        self.status = "FREE"
                        logger.info("比赛胜利")
                        self._sleep(1)
                if self._match_sift("chaolian_defeat.png", 40):
                    if self._ocr((950, 620, 70, 30), "返回"):
                        self.failure_count += 1
                        logger.info("比赛失败")
                        self._tap_with_offset(920, 635, offset=5)
                        self.status = "FREE"

            self._sleep(0.3)

    def _not_inner_match(self):
        self.loading = None
        self.status = "FREE"
        while not stop_event.is_set():
            if self.status == "FREE":
                if self._ocr((450, 70, 390, 50), "选择"):
                    self._tap_with_offset(230, 360, offset=30)
                    self._sleep(1)
                    self._tap_with_offset(630, 650, offset=5)
                    self._sleep(1)
                    self.status = "CHOSE"
                else:
                    self.count += 1
                    if self.count >= 3:
                        if self._ocr((80, 10, 110, 45), "挑战"):
                            self.status = "CHOSE"
            elif self.status == "CHOSE":
                if self._ocr((80, 10, 110, 45), "挑战"):
                    self._tap_with_offset(60, 35, offset=1)
                    self._sleep(1)
                if self._ocr((700, 580, 120, 40), "开始"):
                    self._tap_with_offset(770, 600, offset=3)
                    self.status = "INNER"
                    self._sleep(1)
            elif self.status == "INNER":
                if self._ocr((700, 580, 120, 40), "开始"):
                    logger.info("比赛结束，进入下一个挑战赛")
                    self.status = "FREE"
                    self._sleep(1)
                    self._tap_with_offset(630, 600, offset=4)
                    self._sleep(1)
            self._sleep(0.3)
