import time

from core import stop_event
from core.base_strategy import BaseStrategy
from services.logger_service import logger


class BaseChaolianStrategy(BaseStrategy):
    """超联策略基类，提供超联模式共用的方法。"""

    def _init_stuck_detection(self):
        """初始化卡死检测：记录初始状态和时间。"""
        self._last_status = None
        self._last_status_time = time.monotonic()

    def _is_stuck(self, timeout=90):
        """检查当前状态是否卡死（状态未变化超过指定秒数）。"""
        if self.status != self._last_status:
            self._last_status = self.status
            self._last_status_time = time.monotonic()
            return False
        elapsed = time.monotonic() - self._last_status_time
        if elapsed > timeout:
            logger.warning(f"卡死检测：状态 '{self.status}' 已持续 {elapsed:.0f} 秒，触发恢复")
            return True
        return False

    def _navigate_to_chaolian_main(self):
        """导航到超联主界面：检查当前是否在超联，不在则从大厅进入。"""
        if not self.detecting_chaolian():
            if self.detecting_hall():
                self._tap_with_offset(130, 390, offset=1)
                self._sleep(1.5)

    def _execute_tactic(self):
        """执行战术并管理冷却时间（62秒冷却）。"""
        if self.inner_strategy_status == 0:
            logger.info("执行战术")
            self._tap_with_offset(70, 210, offset=1)
            self._sleep(2)
            self._tap_with_offset(270, 380, offset=2)
            self._sleep(2)
            self.inner_strategy_status = -1
            self.loading = time.monotonic()
            logger.info(f"战术执行完毕，开始冷却")
        elif self.inner_strategy_status == -1:
            if self.loading is not None:
                elapsed_time = time.monotonic() - self.loading
                logger.debug(f"冷却中，已过 {elapsed_time:.1f} 秒")
                if elapsed_time >= 62:
                    self.inner_strategy_status = 0
                    self.loading = None
                    logger.info("冷却完毕，战术可再次执行")

    def _check_enter_match(self):
        """检查'开始'或'进入'按钮，点击进入比赛。返回新状态或None。"""
        if self._ocr((700, 580, 120, 40), "开始"):
            self._tap_with_offset(770, 600, offset=3)
            logger.debug("状态变更为：MATCHING")
            return "MATCHING"
        if self._ocr((700, 580, 120, 40), "进入"):
            self._tap_with_offset(770, 600, offset=3)
            logger.info("进入比赛")
            return "INNER"
        return None

    def _setup_match_count(self):
        """初始化比赛计数逻辑。"""
        self.match_count = 0
        if self.config.get('only_thirty_match'):
            self.change_count = 1
        else:
            self.change_count = 0

    def _not_inner_match_simple(self):
        """非比赛内循环（仅排队，不进入比赛画面），用于季前赛和天梯赛。"""
        self.loading = None
        self.status = "FREE"
        self._init_stuck_detection()

        while not stop_event.is_set():
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
            if self._is_stuck(timeout=120):
                break
            self._sleep(0.3)
