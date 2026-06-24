from core import stop_event
from core.base_strategy import BaseStrategy
from services.logger_service import logger
from core.strategy_manager import update_strategy_stats


class Dynasty33Strategy(BaseStrategy):
    """
    王朝33策略
    """

    def _execute(self):
        #加载配置
        self.ending_good = self.config.get('ending_good')
        self.sending_drawing = self.config.get('sending_drawing')
        self.status = "SEARCHING" #寻找目标SEARCHING
        self.turn_off = self.config.get('turn_off')
        #涂鸦和赛后点赞控制器
        self.is_sending_drawing = False
        self.dancing = self.config.get('dancing')

        # 检测当前的在哪里
        if self.detecting_hall():
            pass
        elif self.detecting_chaolian():
            self._tap_with_offset(60, 35, offset=5)
            self._sleep(1)
        if self._ocr((1050, 380, 120, 30), "王朝"):
            self.status = "FREE"
            self._sleep(1)
        self._init_stuck_detection()
        self._init_iteration_stuck_detection(max_iterations=60)
        while not stop_event.is_set():
            made_progress = False
            if self.status == "SEARCHING":
                # 是否可以再次识别到王朝
                if self._ocr((910,405,95,25),"王朝"):
                    self.status = "FREE"
                    self._sleep(1)
                    made_progress = True
                else:
                    self._tap_with_offset(1120, 450,offset=10)
                    self._sleep(2)
                    if self._match_sift("mode_choose.png",50):
                        self._sleep(1)
                        self._swipe(1000,50,1000,710,500)
                        self._sleep(0.5)
                        self._swipe(1000, 50, 1000, 710, 500)
                        self._sleep(2)
                        pos = self._match_sift("dynasty_33.png", 50)
                        if pos:
                            self._tap_with_offset(int(pos[0]), int(pos[1]), offset=5)
                            self._sleep(1)
                            self._tap_with_offset(1000, 650, offset=5)
                            self._sleep(2)
                            made_progress = True
                        else:
                            logger.error("未找到王朝33模式,请联系开发人员")
                    else:
                        logger.error("未找到模式选择界面")
            elif self.status == "FREE":
                if self.detecting_hall():
                    # 点击匹配
                    self._tap_with_offset(1200,450,offset=5)
                    self.status = "MATCHING"
                    self._sleep(1)
                    made_progress = True
                elif self._match_sift("over.png",50):
                    self.status = "OVER"
                    made_progress = True
                else:
                    if self._match_sift("inner.png",50):
                        self.status = "INNER"
                        logger.debug("已经进入对局")
                        made_progress = True
                    elif self._match_sift("game.png",50):
                        self.status = "INNER"
                        logger.debug("已经进入对局")
                        made_progress = True
            elif self.status == "MATCHING":
                self._sleep(2)
                if self._match_sift("over.png",50):
                    self.status = "OVER"
                    made_progress = True
                if self.detecting_hall():
                    self.status = "FREE"
                    made_progress = True
                else:
                    if self._match_sift("inner.png", 50) or self._match_sift("game.png", 50):
                        self.status = "INNER"
                        logger.debug("已经进入对局")
                        made_progress = True
                    elif self._match_sift("game.png",50):
                        self.status = "INNER"
                        logger.debug("已经进入对局")
                        made_progress = True
            elif self.status == "INNER":
                if self._match_sift("inner.png", 50) or self._match_sift("game.png", 50):
                    if self.sending_drawing and not self.is_sending_drawing:
                        self._tap_with_offset(1210,120,offset=0)
                        self._sleep(1)
                        self._tap_with_offset(800, 230, offset=3)
                        self.is_sending_drawing = True
                        self._sleep(2)
                    made_progress = True
                elif self._match_sift("ending_click.png", 50):
                    self.status = "ENDING"
                    self._tap_with_offset(700, 620, offset=5)
                    self._sleep(2)
                    made_progress = True

            elif self.status == "ENDING":
                if self._match_sift("ending_click.png", 50):
                    self._tap_with_offset(700, 620, offset=5)
                    self._sleep(2)
                    made_progress = True
                elif self._ocr((950, 615, 70, 40), "返"):
                    if self.ending_good:
                        self._sleep(1)
                        self._tap_with_offset(30, 500, offset=0)
                    if self._match_sift("victory.png", 50):
                        self.victory_count += 1
                        update_strategy_stats(self.port, victory=self.victory_count, failure=self.failure_count)
                        logger.info(f"对局结束，胜利{self.victory_count}场，失败{self.failure_count}场")
                        self._tap_with_offset(990, 640, offset=2)
                        self._sleep(1)
                        self.status = "FREE"
                        made_progress = True
                    elif self._match_sift("defeat.png", 50):
                        self.failure_count += 1
                        update_strategy_stats(self.port, victory=self.victory_count, failure=self.failure_count)
                        logger.info(f"对局结束，胜利{self.victory_count}场，失败{self.failure_count}场")
                        self._tap_with_offset(990, 640, offset=2)
                        self._sleep(1)
                        self.status = "FREE"
                        made_progress = True
            elif self.status == "OVER":
                if self._match_sift("over.png",120):
                    logger.info("已达上限")
                    self._sleep(1)
                    self._tap_with_offset(890, 580, offset=5)
                    logger.info(f"对局结束，胜利{self.victory_count}场，失败{self.failure_count}场")
                    made_progress = True
                    break

                self._sleep(0.5)

            if self._is_stuck(timeout=180) or self._check_iteration_stuck():
                if stop_event.is_set():
                    break
                logger.warning(f"[端口 {self.port}] 检测到卡死，尝试重连恢复...")
                if self._ensure_device():
                    self._init_stuck_detection()
                    self._init_iteration_stuck_detection(max_iterations=200)
                    continue
                else:
                    logger.error(f"[端口 {self.port}] 重连失败，退出循环")
                    break

            if made_progress:
                self._reset_iteration_stuck()

            self._sleep(0.5)
        if self.dancing:
            self._dancing()
        if self.turn_off:
            self.computer_turn_off()
            return None
        else:
            return  True