from core import stop_event
from core.base_strategy import BaseStrategy
from services.logger_service import logger


class FullAutoTaskStrategy(BaseStrategy):
    """全自动任务：按配置顺序依次执行多个子策略"""

    def _execute(self):
        from core.strategies import STRATEGY_MAP  # 延迟导入避免循环引用
        tasks = self.config.get("tasks", [])
        if not tasks:
            logger.warning(f"[端口 {self.port}] 全自动任务列表为空")
            return

        final_dancing = False
        final_turn_off = False

        for i, task in enumerate(tasks):
            if stop_event.is_set():
                break

            mode_id = task["mode_id"]
            sub_opts = dict(task.get("options", {}))

            if sub_opts.pop("dancing", False):
                final_dancing = True
            if sub_opts.pop("turn_off", False):
                final_turn_off = True

            if mode_id not in STRATEGY_MAP:
                logger.warning(f"[端口 {self.port}] 未知模式 {mode_id}，跳过")
                continue

            sub_cls = STRATEGY_MAP[mode_id]
            sub = sub_cls(self.port, sub_opts, self.click_offset)
            sub.adb = self.adb
            sub.image = self.image
            sub.screen_size = self.screen_size

            display = task.get("display_name", mode_id)
            logger.info(f"[端口 {self.port}] 全自动任务 ({i+1}/{len(tasks)}): {display} 开始")
            sub._execute()
            self.victory_count += sub.victory_count
            self.failure_count += sub.failure_count
            logger.info(f"[端口 {self.port}] 全自动任务 ({i+1}/{len(tasks)}): {display} 结束 — "
                        f"胜利{sub.victory_count} 失败{sub.failure_count}")

            if i < len(tasks) - 1 and not stop_event.is_set():
                self._sleep(1)

        if stop_event.is_set():
            return

        if final_dancing:
            logger.info(f"[端口 {self.port}] 全自动任务 — 开始跳舞")
            self._dancing()

        if final_turn_off:
            logger.info(f"[端口 {self.port}] 全自动任务 — 执行关机")
            self.computer_turn_off()

        logger.info(f"[端口 {self.port}] 全自动任务全部完成 — "
                    f"总胜利{self.victory_count} 总失败{self.failure_count}")
