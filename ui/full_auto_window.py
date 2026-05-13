import customtkinter as ctk
from ui.theme import THEME


class FullAutoWindow(ctk.CTkToplevel):
    """全自动任务配置弹窗"""

    def __init__(self, master, mode_config: dict, saved_tasks: list = None,
                 callback_on_start=None, callback_on_save=None):
        super().__init__(master)
        self.title("全自动任务配置")
        self.geometry("620x680")
        self.resizable(False, False)
        self.configure(fg_color=THEME["bg"])

        self.mode_config = mode_config
        self.callback_on_start = callback_on_start
        self.callback_on_save = callback_on_save

        self.task_queue: list = []
        self.task_option_vars: dict = {}

        self._dynasty_var = ctk.StringVar(value="")
        self._chaolian_vars: dict[str, ctk.BooleanVar] = {}

        self._build_ui()

        if saved_tasks:
            self._load_tasks(saved_tasks)

        self.grab_set()
        self.lift()

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color=THEME["panel_bg"], corner_radius=0, height=42)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="全自动任务配置",
            font=("Microsoft YaHei UI", 16, "bold"),
            text_color=THEME["accent"],
        ).pack(side="left", padx=16, pady=10)

        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=THEME["border"],
            scrollbar_button_hover_color=THEME["accent"],
        )
        scroll.pack(fill="both", expand=True, padx=10, pady=8)

        self._build_dynasty_section(scroll)
        self._build_separator(scroll)
        self._build_chaolian_section(scroll)
        self._build_separator(scroll)
        self._build_queue_section(scroll)
        self._build_buttons()

    def _build_separator(self, parent):
        ctk.CTkFrame(parent, fg_color=THEME["border"], height=1).pack(fill="x", pady=6)

    def _section_label(self, parent, text: str, color: str):
        ctk.CTkLabel(
            parent, text=text,
            font=("Microsoft YaHei UI", 12, "bold"),
            text_color=color,
        ).pack(anchor="w", pady=(4, 6))

    def _build_dynasty_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._section_label(frame, "王朝模式（单选）", THEME["gold"])

        dynasty_ids = [mid for mid, info in self.mode_config.items() if info.get("group") == "dynasty"]
        for mode_id in dynasty_ids:
            info = self.mode_config[mode_id]
            rb = ctk.CTkRadioButton(
                frame, text=info["display_name"],
                variable=self._dynasty_var, value=mode_id,
                fg_color=THEME["gold"], hover_color=THEME["gold"],
                text_color=THEME["subtext"], font=("Microsoft YaHei UI", 11),
                radiobutton_width=16, radiobutton_height=16,
            )
            rb.pack(anchor="w", padx=12, pady=2)

        ctk.CTkButton(
            frame, text="添加到队列",
            command=self._on_add_dynasty,
            fg_color=THEME["gold"], hover_color="#D4942F",
            text_color=THEME["bg"], font=("Microsoft YaHei UI", 10),
            width=90, height=26, corner_radius=6,
        ).pack(anchor="w", padx=12, pady=(4, 0))
        frame.pack(fill="x")

    def _build_chaolian_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._section_label(frame, "超级联赛模式（多选）", THEME["purple"])

        chaolian_ids = [mid for mid, info in self.mode_config.items() if info.get("group") == "chaolian"]
        for mode_id in chaolian_ids:
            info = self.mode_config[mode_id]
            var = ctk.BooleanVar(value=False)
            self._chaolian_vars[mode_id] = var
            cb = ctk.CTkCheckBox(
                frame, text=info["display_name"],
                variable=var,
                fg_color=THEME["purple"], hover_color=THEME["purple"],
                text_color=THEME["subtext"], font=("Microsoft YaHei UI", 11),
                checkbox_width=16, checkbox_height=16,
            )
            cb.pack(anchor="w", padx=12, pady=2)

        ctk.CTkButton(
            frame, text="添加到队列",
            command=self._on_add_chaolian,
            fg_color=THEME["purple"], hover_color="#7C3AED",
            text_color="#FFFFFF", font=("Microsoft YaHei UI", 10),
            width=90, height=26, corner_radius=6,
        ).pack(anchor="w", padx=12, pady=(4, 0))
        frame.pack(fill="x")

    def _build_queue_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._section_label(frame, "任务队列（按顺序执行）", THEME["accent"])
        self._queue_scroll = ctk.CTkScrollableFrame(
            frame, fg_color=THEME["bg"], corner_radius=8,
            scrollbar_button_color=THEME["border"],
            scrollbar_button_hover_color=THEME["accent"],
            height=220,
        )
        self._queue_scroll.pack(fill="x", pady=(0, 4))
        self._empty_label = ctk.CTkLabel(
            self._queue_scroll, text="暂无任务，请从上方添加",
            font=("Microsoft YaHei UI", 11),
            text_color=THEME["subtext"],
        )
        self._empty_label.pack(pady=20)
        frame.pack(fill="x")

    def _build_buttons(self):
        bar = ctk.CTkFrame(self, fg_color=THEME["panel_bg"], corner_radius=0, height=50)
        bar.pack(fill="x", side="bottom", padx=0, pady=0)
        bar.pack_propagate(False)

        ctk.CTkButton(
            bar, text="保存配置",
            command=self._on_save,
            fg_color=THEME["border"], hover_color=THEME["accent"],
            text_color=THEME["text"], font=("Microsoft YaHei UI", 11),
            width=100, height=32, corner_radius=6,
        ).pack(side="right", padx=(6, 12), pady=9)

        ctk.CTkButton(
            bar, text="开始执行",
            command=self._on_start,
            fg_color=THEME["accent"], hover_color="#00B894",
            text_color=THEME["bg"], font=("Microsoft YaHei UI", 11, "bold"),
            width=100, height=32, corner_radius=6,
        ).pack(side="right", padx=(0, 6), pady=9)

    # ==================== 队列操作 ====================

    def _on_add_dynasty(self):
        mode_id = self._dynasty_var.get()
        if not mode_id:
            return
        if any(t["mode_id"] == mode_id for t in self.task_queue):
            return
        info = self.mode_config[mode_id]
        task = {
            "mode_id": mode_id,
            "display_name": info["display_name"],
            "group": "dynasty",
            "options": {opt["id"]: opt.get("default", False) for opt in info.get("options", [])},
        }
        self.task_queue.append(task)
        self._rebuild_queue_ui()

    def _on_add_chaolian(self):
        for mode_id, var in self._chaolian_vars.items():
            if not var.get():
                continue
            if any(t["mode_id"] == mode_id for t in self.task_queue):
                continue
            info = self.mode_config[mode_id]
            task = {
                "mode_id": mode_id,
                "display_name": info["display_name"],
                "group": "chaolian",
                "options": {opt["id"]: opt.get("default", False) for opt in info.get("options", [])},
            }
            self.task_queue.append(task)
        self._rebuild_queue_ui()

    def _on_remove_from_queue(self, idx: int):
        if 0 <= idx < len(self.task_queue):
            self.task_queue.pop(idx)
        self._rebuild_queue_ui()

    def _on_move_up(self, idx: int):
        if idx > 0:
            self.task_queue[idx], self.task_queue[idx - 1] = self.task_queue[idx - 1], self.task_queue[idx]
        self._rebuild_queue_ui()

    def _on_move_down(self, idx: int):
        if idx < len(self.task_queue) - 1:
            self.task_queue[idx], self.task_queue[idx + 1] = self.task_queue[idx + 1], self.task_queue[idx]
        self._rebuild_queue_ui()

    def _rebuild_queue_ui(self):
        for w in self._queue_scroll.winfo_children():
            w.destroy()
        self.task_option_vars.clear()

        if not self.task_queue:
            self._empty_label = ctk.CTkLabel(
                self._queue_scroll, text="暂无任务，请从上方添加",
                font=("Microsoft YaHei UI", 11),
                text_color=THEME["subtext"],
            )
            self._empty_label.pack(pady=20)
            return

        group_colors = {"dynasty": THEME["gold"], "chaolian": THEME["purple"]}

        for idx, task in enumerate(self.task_queue):
            mode_id = task["mode_id"]
            info = self.mode_config.get(mode_id, {})
            group = task.get("group", "")
            bar_color = group_colors.get(group, THEME["border"])

            row = ctk.CTkFrame(
                self._queue_scroll, fg_color=THEME["panel_bg"], corner_radius=6,
                border_width=1, border_color=THEME["border"],
            )
            row.pack(fill="x", padx=2, pady=2)

            top = ctk.CTkFrame(row, fg_color="transparent")
            top.pack(fill="x", padx=6, pady=(4, 0))

            indicator = ctk.CTkFrame(top, fg_color=bar_color, width=4, corner_radius=2)
            indicator.pack(side="left", padx=(0, 6), pady=2)

            ctk.CTkLabel(
                top, text=f"#{idx + 1}. {task['display_name']}",
                font=("Microsoft YaHei UI", 11, "bold"),
                text_color=bar_color,
            ).pack(side="left")

            ctk.CTkButton(
                top, text="上移", width=36, height=20, corner_radius=4,
                fg_color=THEME["border"], hover_color=THEME["accent"],
                text_color=THEME["subtext"], font=("Microsoft YaHei UI", 9),
                command=lambda i=idx: self._on_move_up(i),
            ).pack(side="right", padx=1)

            ctk.CTkButton(
                top, text="下移", width=36, height=20, corner_radius=4,
                fg_color=THEME["border"], hover_color=THEME["accent"],
                text_color=THEME["subtext"], font=("Microsoft YaHei UI", 9),
                command=lambda i=idx: self._on_move_down(i),
            ).pack(side="right", padx=1)

            ctk.CTkButton(
                top, text="删除", width=36, height=20, corner_radius=4,
                fg_color="transparent", hover_color=THEME["danger"],
                text_color=THEME["danger"], font=("Microsoft YaHei UI", 9),
                border_width=1, border_color=THEME["danger"],
                command=lambda i=idx: self._on_remove_from_queue(i),
            ).pack(side="right", padx=1)

            options = info.get("options", [])
            if options:
                opts_frame = ctk.CTkFrame(row, fg_color="transparent")
                opts_frame.pack(fill="x", padx=12, pady=(2, 6))

                opt_vars = {}
                for opt in options:
                    var = ctk.BooleanVar(value=task["options"].get(opt["id"], opt.get("default", False)))
                    opt_vars[opt["id"]] = var
                    cb = ctk.CTkCheckBox(
                        opts_frame, text=opt["display_name"],
                        variable=var,
                        fg_color=THEME["border"], hover_color=bar_color,
                        text_color=THEME["subtext"], font=("Microsoft YaHei UI", 9),
                        checkbox_width=14, checkbox_height=14,
                    )
                    cb.pack(side="left", padx=(0, 8), pady=2)

                self.task_option_vars[idx] = opt_vars

    # ==================== 保存 / 启动 ====================

    def _collect_tasks(self) -> list:
        result = []
        for idx, task in enumerate(self.task_queue):
            opts = dict(task["options"])
            if idx in self.task_option_vars:
                for opt_id, var in self.task_option_vars[idx].items():
                    opts[opt_id] = var.get()
            result.append({
                "mode_id": task["mode_id"],
                "display_name": task["display_name"],
                "group": task["group"],
                "options": opts,
            })
        return result

    def _on_save(self):
        tasks = self._collect_tasks()
        if self.callback_on_save:
            self.callback_on_save(tasks)
        self.destroy()

    def _on_start(self):
        tasks = self._collect_tasks()
        if not tasks:
            return
        if self.callback_on_start:
            self.callback_on_start(tasks)
        self.destroy()

    def _load_tasks(self, saved_tasks: list):
        self.task_queue = []
        for t in saved_tasks:
            task = {
                "mode_id": t.get("mode_id", ""),
                "display_name": t.get("display_name", ""),
                "group": t.get("group", ""),
                "options": dict(t.get("options", {})),
            }
            self.task_queue.append(task)
        self._rebuild_queue_ui()
