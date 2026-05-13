from core import stop_event
from core.base_strategy import BaseStrategy
from services.logger_service import logger
from core.strategies.dynasty_33 import Dynasty33Strategy
from core.strategies.dynasty_55 import Dynasty55Strategy


class DynastyAll(BaseStrategy):
    """王朝全模式：先跑 33，再跑 55"""

    def _execute(self):
        self.turn_off = self.config.get('turn_off')
        self.dancing = self.config.get('dancing')
        son_config = dict(self.config)
        son_config['turn_off'] = False
        son_config['dancing'] = False
        self.dy_33 = Dynasty33Strategy(self.port, son_config, self.click_offset)
        self.dy_55 = Dynasty55Strategy(self.port, son_config, self.click_offset)

        for sub in (self.dy_33, self.dy_55):
            sub.adb = self.adb
            sub.image = self.image
            sub.screen_size = self.screen_size

        logger.info(f"[端口 {self.port}] 王朝33 开始")
        self.dy_33._execute()
        self.victory_count = self.dy_33.victory_count
        self.failure_count = self.dy_33.failure_count
        logger.info(f"[端口 {self.port}] 王朝33 结束 — 胜利{self.victory_count} 失败{self.failure_count}")

        if stop_event.is_set():
            return

        self._sleep(1)

        logger.info(f"[端口 {self.port}] 王朝55 开始")
        self.dy_55._execute()
        self.victory_count += self.dy_55.victory_count
        self.failure_count += self.dy_55.failure_count
        logger.info(f"[端口 {self.port}] 全部完成 — 胜利{self.victory_count} 失败{self.failure_count}")
        if self.dancing:
            logger.info("开始跳舞")
            self._dancing()
        if self.turn_off:
            self.computer_turn_off()
        logger.info("已完成任务")
        return