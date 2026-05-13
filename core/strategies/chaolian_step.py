from core import stop_event
from core.strategies.base_chaolian import BaseChaolianStrategy
from services.logger_service import logger
from datetime import datetime


class ChaolianStepStrategy(BaseChaolianStrategy):
    """超级联赛天梯赛策略"""

    def _is_ladder_time(self) -> bool:
        """检查当前是否在天梯赛允许的时间段内（8:00-24:00）"""
        current_hour = datetime.now().hour
        return 8 <= current_hour < 24

    def _execute(self):
        self.is_excu_strategy = self.config.get('is_excu_strategy')
        self.is_inter_match = self.config.get('is_inter_match')
        self._setup_match_count()
        self.dancing = self.config.get('dancing')
        self._navigate_to_chaolian_main()
        
        if not self._is_ladder_time():
            logger.info("当前时间不在天梯赛时间段内（8:00-24:00），跳过天梯赛")
            return
        
        if not self._ocr((800, 300, 70, 30), "天梯"):
            logger.error("没有看到天梯赛目标！")
            return
        self._tap_with_offset(830, 320, offset=1)
        self._sleep(1)

        if self.is_inter_match:
            self._inner_match()
        else:
            self._not_inner_match_simple()
        if self.dancing:
            self._dancing()
        logger.info("已完成任务")
        return

    def _inner_match(self):
        self.loading = None
        self.status = "FREE"
        self.inner_strategy_status = 0
        self._init_stuck_detection()
        self._init_iteration_stuck_detection(max_iterations=60)

        while not stop_event.is_set():
            if not self._is_ladder_time():
                logger.info("当前时间不在天梯赛时间段内（8:00-24:00），跳过天梯赛")
                break
            if self.match_count >= 30:
                logger.info("已达到30场比赛，退出循环")
                break
            screen = self._grab_screen()
            made_progress = False

            if self.status == "FREE" or self.status == "MATCHING":
                self._sleep(2)
                self._tap_with_offset(830, 320, offset=1)
                self._sleep(1)
                result = self._check_enter_match(screen=screen)
                if result:
                    self.status = result
                    made_progress = True
            elif self.status == "INNER":
                if self._match_sift("chaolian_match.png", min_match=50, screen=screen):
                    logger.debug("比赛进行中")
                    if self.is_excu_strategy:
                        self._execute_tactic()
                    made_progress = True
                else:
                    self._check_enter_match(screen=screen)
                    if self._match_sift("ready.png", min_match=45, screen=screen):
                        self._tap_with_offset(780, 610, offset=3)
                        logger.debug("准备阶段点击")
                        self._sleep(1)
                        made_progress = True
                    if self._match_sift("chaolian_win.png", min_match=50, screen=screen) or self._match_sift("chaolian_defeat.png", min_match=50, screen=screen):
                        self.status = "ENDING"
                        self._sleep(1)
                        made_progress = True
                    elif self._ocr((690, 620, 260, 40), "点击", screen=screen):
                        self._tap_with_offset(690, 620, offset=30)
                        self.status = "ENDING"
                        self._sleep(1)
                        made_progress = True
            elif self.status == "ENDING":
                if self._match_sift("chaolian_win.png", min_match=50, screen=screen):
                    if self._ocr((950, 620, 70, 30), "返", screen=screen):
                        self.victory_count += 1
                        logger.info(f"比赛胜利，胜利{self.victory_count}场，失败{self.failure_count}场")
                        self._tap_with_offset(920, 635, offset=5)
                        self.status = "FREE"
                        self.match_count += self.change_count
                        logger.info(f"比赛结束，场次计数：{self.match_count}")
                        self._sleep(1)
                        made_progress = True
                elif self._match_sift("chaolian_defeat.png", min_match=50, screen=screen):
                    if self._ocr((950, 620, 70, 30), "返", screen=screen):
                        self.failure_count += 1
                        logger.info(f"比赛失败，失败{self.failure_count}场，胜利{self.victory_count}场")
                        self._tap_with_offset(920, 635, offset=5)
                        self.status = "FREE"
                        self.match_count += self.change_count
                        logger.info(f"比赛结束，场次计数：{self.match_count}")
                        made_progress = True
            else:
                if self._match_sift("chaolian_win.png", min_match=50, screen=screen) or self._match_sift("chaolian_defeat.png", min_match=50, screen=screen):
                    if self._ocr((950, 620, 70, 30), "返", screen=screen):
                        self._tap_with_offset(920, 635, offset=5)
                        self.status = "FREE"
                        self.match_count += self.change_count
                        logger.info(f"比赛结束，场次计数：{self.match_count}")
                        self._sleep(1)
                        made_progress = True

            if self._is_stuck(timeout=1800) or self._check_iteration_stuck():
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
