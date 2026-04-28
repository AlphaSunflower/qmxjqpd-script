import datetime

import time

from core import stop_event
from core.base_strategy import BaseStrategy
from services.logger_service import logger


class ChaolianChallengeStrategy(BaseStrategy):
    """
    超联挑战赛策略
    """

    def _execute(self):

        self.is_inter_match = self.config.get('is_inter_match')
        self.is_excu_strategy = self.config.get('is_excu_strategy')
        #检查是否是超级联赛
        if not self.detecting_chaolian():
            # 检测是否在大厅
            if self.detecting_hall():
                self._tap_with_offset(130,390,offset=1)
                self._sleep(1.5)
            #检查是否在通信证
            #检测是否在补给箱.....（同一个位置）
        # 点击进入季前赛
        #先检测是否是挑战赛
        if not self._ocr((510,300,70,30),"挑战"):
            logger.error("没有看到挑战赛目标！")
            return
        #点击挑战赛
        self._tap_with_offset(550,320,offset=1)
        self._sleep(1)
        if self._ocr((700, 580, 120, 40),"开启"):
            self._tap_with_offset(770,600,offset=5)
            self._sleep(3)
            #开启全新一轮的挑战
            self._tap_with_offset(890,570,offset=5)
            self._sleep(1)
        #前往赛事
        self._tap_with_offset(630,600,offset=4)
        self._sleep(2)

        if self.is_inter_match:
            self._inner_match()

        else:
            self._not_inner_match()
        logger.info("已完成任务")

    def _inner_match(self):
        self.count = 0
        self.loading = None
        self.status = "FREE"  # FREE空闲、CHOSE已选择天赋、INNER正在比赛
        self.inner_strategy_status = 0  # 0未执行战术、-1为冷却中
        while not stop_event.is_set():
            if self.status == "FREE":
                #检查是否是第一次挑战
                # 检查是否在选天赋界面
                if self._ocr((450, 70, 390, 50), "选择"):
                    # 选择技能加成
                    self._tap_with_offset(230,360,offset=30)
                    self._sleep(1)
                    #选泽
                    self._tap_with_offset(630,650,offset=5)
                    #580,270
                    self._sleep(1)
                    self.status = "CHOSE"
                else:
                    self.count += 1
                    if self.count >=3:
                        if self._ocr((80, 10, 110, 45), "挑战"):
                            self.status = "CHOSE"
                            self.count = 0

            elif self.status == "CHOSE":
                if self._ocr((80, 10, 110, 45), "挑战"):
                    # 方案一，在赛事界面点击挑战
                    if not self._ocr((720,270,110,30),"首发"):
                        self._tap_with_offset(580, 270, offset=5)
                        self._sleep(2)
                    if self._ocr((950,650,110,40),"前往"):
                        self._tap_with_offset(1000,670,offset=10)
                        self._sleep(3)
                    if self._ocr((950,650,110,40),"进入"):
                        self._tap_with_offset(1000,670,offset=10)
                        self.status = "INNER"

                else:
                    if self._ocr((700, 580, 120, 40), "进入"):
                        self._tap_with_offset(770, 610, offset=3)
                        self.status = "INNER"
                        self._sleep(1)
                    if self._ocr((450, 70, 390, 50), "选择"):
                        self.status = "FREE"

            elif self.status == "INNER":
                if self._match_sift("chaolian_match.png",50):
                    logger.debug("比赛进行中")
                    if self.is_excu_strategy:
                        if self.inner_strategy_status == 0:
                            #执行战术
                            logger.info("执行战术")
                            self._tap_with_offset(70,210,offset=1)
                            self._sleep(2)
                            self._tap_with_offset(270, 380,offset=2)
                            self._sleep(2)
                            #更改执行战术状态
                            self.inner_strategy_status = -1
                            #记录开始冷却时间
                            self.loading = datetime.datetime.now()
                            logger.info(f"战术执行完毕，开始冷却，当前时间：{self.loading}")
                        #战术冷却状态的逻辑
                        elif self.inner_strategy_status == -1:
                            if self.loading is not None:
                                # 计算经过的时间（秒）
                                elapsed_time = (datetime.datetime.now() - self.loading).total_seconds()
                                logger.debug(f"冷却中，已过 {elapsed_time:.1f} 秒")
                                if elapsed_time >= 62:
                                    self.inner_strategy_status = 0
                                    self.loading = None
                                    logger.info("冷却完毕，战术可再次执行")
                if self._match_sift("ready.png",50):
                    self._tap_with_offset(780, 610, offset=3)
                    logger.debug("准备阶段点击")
                    self._sleep(1)
                if self._match_sift("chaolian_win.png",50):
                    if self._ocr((950,620,70,30),"返回"):
                        self.victory_count+=1
                        logger.info("比赛胜利,胜利"+str(self.victory_count)+"场"+"失败"+str(self.failure_count)+"场")
                        self._tap_with_offset(920, 635, offset=5)
                        self.status = "FREE"
                        logger.info(f"比赛胜利")
                        self._sleep(1)
                if self._match_sift("chaolian_defeat.png",40):
                    if self._ocr((950,620,70,30),"返回"):
                        self.failure_count+=1
                        logger.info("比赛失败")
                        self._tap_with_offset(920, 635, offset=5)
                        self.status = "FREE"


    def _not_inner_match(self):
        self.loading = None
        self.status = "FREE"  # FREE空闲、CHOSE已选择天赋、INNER正在比赛
        while not stop_event.is_set():
            if self.status == "FREE":
                if self._ocr((450, 70, 390, 50), "选择"):
                    # 选择技能加成
                    self._tap_with_offset(230,360,offset=30)
                    self._sleep(1)
                    #选泽
                    self._tap_with_offset(630,650,offset=5)
                    #580,270
                    self._sleep(1)
                    self.status = "CHOSE"

                else:
                    self.count += 1
                    if self.count>=3:
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
                    logger.info(f"比赛结束,进入下一个挑战赛")
                    self.status = "FREE"
                    self._sleep(1)
                    # 前往赛事
                    self._tap_with_offset(630, 600, offset=4)
                    self._sleep(1)