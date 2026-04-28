import datetime

import time

from core import stop_event
from core.base_strategy import BaseStrategy
from services.logger_service import logger


class ChaolianFrontStrategy(BaseStrategy):
    """
    超级联赛季前赛策略
    """
    def _execute(self):
        self.only_thirty_match = self.config.get('only_thirty_match')
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
        #先检测是否是季前赛
        if not self._ocr((420,300,70,30),"季前"):
            logger.error("没有看到季前赛目标！")
            return
        #点击季前赛
        self._tap_with_offset(455,322,offset=1)
        self._sleep(1)
        #判断只打30场、是否进入比赛、是否执行战术
        #判断只打30场 self.match_count比赛次数，-1为无限制，self.change_count为没打完一场改变次数
        self.match_count = 0
        if self.only_thirty_match:
            self.change_count = 1
        else:
            self.change_count = 0
        if self.is_inter_match:
            self._inner_match()

        else:
            self._not_inner_match()
        logger.info("已完成任务")

    def _inner_match(self):
        self.loading = None
        self.status = "FREE" #FREE空闲、MATCHING正在匹配、INNER正在比赛
        self.inner_strategy_status = 0 #0未执行战术、-1为冷却中

        while not stop_event.is_set():
            "进入比赛一系列的操作"
            if self.match_count>=30:
                logger.info("已达到30场比赛，退出循环")
                break
            if self.status == "FREE" or self.status == "MATCHING":
                if self._ocr((700, 580, 120, 40), "开始"):
                    self._tap_with_offset(770, 600, offset=3)
                    self.status = "MATCHING"
                    logger.debug("状态变更为：MATCHING")
                if self._ocr((700, 580, 120, 40), "进入"):
                    self._tap_with_offset(770, 600, offset=3)
                    logger.info("进入比赛")
                    self.status = "INNER"
            if self.status == "INNER":
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
                else:
                    if self._ocr((700, 580, 120, 40), "进入"):
                        self._tap_with_offset(770, 600, offset=3)
                        logger.info("进入比赛")
                    #准备阶段700 600   /255, 151, 54
                if self._match_sift("ready.png",50):
                    self._tap_with_offset(780, 610, offset=3)
                    logger.debug("准备阶段点击")
                    self._sleep(1)
                if self._match_sift("chaolian_win.png",60):
                    if self._ocr((950,620,70,30),"返回"):
                        self.victory_count+=1
                        logger.info("比赛胜利,胜利"+str(self.victory_count)+"场"+"失败"+str(self.failure_count)+"场")
                        self._tap_with_offset(920, 635, offset=5)
                        self.status = "FREE"
                        self.match_count += self.change_count
                        logger.info(f"比赛结束，场次计数：{self.match_count}")
                        self._sleep(1)
                if self._match_sift("chaolian_defeat.png",60):
                    if self._ocr((950,620,70,30),"返回"):
                        self.failure_count+=1
                        logger.info("比赛失败,失败"+str(self.failure_count)+"场"+"胜利"+str(self.victory_count)+"场")
                        self._tap_with_offset(920, 635, offset=5)
                        self.status = "FREE"
                        self.match_count += self.change_count
                        logger.info(f"比赛结束，场次计数：{self.match_count}")
    def _not_inner_match(self):
        self.loading = None
        self.status = "FREE" #FREE空闲、MATCHING正在匹配、INNER正在比赛

        while not stop_event.is_set():
            "进入比赛一系列的操作"
            if self.match_count >= 30:
                logger.info("已达到30场比赛，退出循环")
                break
            if self.status == "FREE" or self.status == "MATCHING":
                if self._ocr((700, 580, 120, 40), "开始"):
                    self._tap_with_offset(770, 600, offset=3)
                    self.status = "MATCHING"
                    logger.debug("状态变更为：MATCHING")
                if self._ocr((700, 580, 120, 40), "进入"):
                    self._tap_with_offset(770, 600, offset=3)
                    logger.info("进入比赛")
                    self.status = "INNER"
            elif self.status == "INNER":
                if self._ocr((700, 580, 120, 40), "开始"):
                    self.match_count += self.change_count
                    logger.info(f"比赛结束，场次计数：{self.match_count}")
                    self.status = "FREE"
