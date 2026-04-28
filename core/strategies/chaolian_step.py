from core import stop_event
from core.strategies.base_chaolian import BaseChaolianStrategy
from services.logger_service import logger


class ChaolianStepStrategy(BaseChaolianStrategy):
    """超级联赛天梯赛策略"""

    def _execute(self):
        self.is_excu_strategy = self.config.get('is_excu_strategy')
        self.is_inter_match = self.config.get('is_inter_match')
        self._setup_match_count()

        self._navigate_to_chaolian_main()

        if not self._ocr((800, 300, 70, 30), "天梯"):
            logger.error("没有看到天梯赛目标！")
            return
        self._tap_with_offset(830, 320, offset=1)
        self._sleep(1)

        if self.is_inter_match:
            self._inner_match()
        else:
            self._not_inner_match_simple()
        logger.info("已完成任务")

    def _inner_match(self):
        self.loading = None
        self.status = "FREE"
        self.inner_strategy_status = 0

        while not stop_event.is_set():
            if self.match_count >= 30:
                logger.info("已达到30场比赛，退出循环")
                break
            if self.status == "FREE" or self.status == "MATCHING":
                self._sleep(2)
                self._tap_with_offset(830, 320, offset=1)
                self._sleep(1)
                result = self._check_enter_match()
                if result:
                    self.status = result
            if self.status == "INNER":
                if self._match_sift("chaolian_match.png", 50):
                    logger.debug("比赛进行中")
                    if self.is_excu_strategy:
                        self._execute_tactic()
                else:
                    self._check_enter_match()
                    if self._match_sift("ready.png", 50):
                        self._tap_with_offset(780, 610, offset=3)
                        logger.debug("准备阶段点击")
                        self._sleep(1)
                    if self._ocr((690, 620, 260, 40), "点击"):
                        self._tap_with_offset(690, 620, offset=30)
                        self.status = "ENDING"
                        self._sleep(1)
            if self.status == "ENDING":
                if self._match_sift("chaolian_win.png", 50):
                    if self._ocr((950, 620, 70, 30), "返回"):
                        self.victory_count += 1
                        logger.info(f"比赛胜利，胜利{self.victory_count}场，失败{self.failure_count}场")
                        self._tap_with_offset(920, 635, offset=5)
                        self.status = "FREE"
                        self.match_count += self.change_count
                        logger.info(f"比赛结束，场次计数：{self.match_count}")
                        self._sleep(1)
                if self._match_sift("chaolian_defeat.png", 40):
                    if self._ocr((950, 620, 70, 30), "返回"):
                        self.failure_count += 1
                        logger.info(f"比赛失败，失败{self.failure_count}场，胜利{self.victory_count}场")
                        self._tap_with_offset(920, 635, offset=5)
                        self.status = "FREE"
                        self.match_count += self.change_count
                        logger.info(f"比赛结束，场次计数：{self.match_count}")

            self._sleep(0.3)
