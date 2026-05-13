import os
import json
import datetime
import tkinter.messagebox as messagebox
import threading
import customtkinter as ctk
import psutil
from paths import CONFIG_PATH, MODE_CONFIG_PATH, save_path
from services.logger_service import logger
from core.strategy_manager import StrategyManager, stop_event, get_screen_size, get_strategy_stats
from core.strategies import STRATEGY_MAP
from core.strategies.full_auto import FullAutoTaskStrategy
from ui.theme import THEME
from ui.full_auto_window import FullAutoWindow

# 可用端口
AVAILABLE_PORTS = [16384, 16416, 16448, 16480]
PORT_LABELS = {
    16384: "主模拟器",
    16416: "模拟器 2",
    16448: "模拟器 3",
    16480: "模拟器 4",
}

MULTI_INSTANCE_OPTIONS = ["单开", "双开", "三开", "四开"]


class LogTextBox(ctk.CTkTextbox):
    TAG_COLORS = {
        "INFO": THEME["accent"],
        "DEBUG": "#6C8EBF",
        "WARNING": THEME["warning"],
        "ERROR": THEME["danger"],
    }

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.configure(
            fg_color=THEME["log_bg"],
            text_color=THEME["text"],
            font=("Consolas", 11),
            border_width=0,
            corner_radius=8,
            state="disabled",
        )
        self.tag_config("INFO", foreground=self.TAG_COLORS["INFO"])
        self.tag_config("DEBUG", foreground=self.TAG_COLORS["DEBUG"])
        self.tag_config("WARNING", foreground=self.TAG_COLORS["WARNING"])
        self.tag_config("ERROR", foreground=self.TAG_COLORS["ERROR"])

    def append_log(self, text: str):
        self.configure(state="normal")
        level = "INFO"
        if "[DEBUG]" in text:
            level = "DEBUG"
        elif "[WARNING]" in text:
            level = "WARNING"
        elif "[ERROR]" in text:
            level = "ERROR"
        self.insert("end", text + "\n", level)
        self.see("end")
        self.configure(state="disabled")


class MainWindow(ctk.CTk):
    VERSION = "1.0.0"

    def __init__(self):
        super().__init__()

        self.title("全明星街球派对自动化")
        self.geometry("1100x700")
        self.resizable(False, False)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # 加载配置
        self.settings = self._load_settings()
        self.mode_config = self._load_mode_config()

        # 运行状态
        self.manager: StrategyManager = None
        self._worker_threads: list = []
        self._midnight_timer: threading.Timer = None

        # 模式复选框引用
        self.mode_vars: dict = {}
        self.mode_option_vars: dict = {}
        self.mode_group_vars: dict = {}
        self.port_comboxes: list = []
        self.port_labels: list = []

        self._build_ui()
        self._restore_settings()

    # ==================== 配置读写 ====================

    def _load_settings(self) -> dict:
        try:
            # 优先读取用户保存的配置（打包后写入 ~\.qmxChaoLian）
            saved_path = save_path('config/settings.json')
            if os.path.exists(saved_path):
                with open(saved_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            # 开发/打包后读取内置资源文件
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {
            "multi_instance_count": 1,
            "ports": [16384],
            "click_offset": 10,
            "strategy_options": {},
            "midnight_enabled": False,
        }

    def _load_mode_config(self) -> dict:
        try:
            if os.path.exists(MODE_CONFIG_PATH):
                with open(MODE_CONFIG_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"modes": {}}

    def _save_settings(self):
        try:
            save_dir = os.path.dirname(save_path('config/settings.json'))
            os.makedirs(save_dir, exist_ok=True)
            with open(save_path('config/settings.json'), "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"保存配置失败: {e}")

    # ==================== UI 构建 ====================

    def _build_ui(self):
        self.configure(fg_color=THEME["bg"])

        # 标题栏
        self._build_header()

        # 主内容区
        content = ctk.CTkFrame(self, fg_color=THEME["bg"], corner_radius=0)
        content.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # 左侧控制面板
        self._build_control_panel(content)

        # 右侧：仪表盘 + 日志
        self._build_right_panel(content)

        self.after(0, self._poll_log_queue)
        self.after(1000, self._poll_dashboard)
        # 初始化仪表盘端口
        self.after(500, self._init_dashboard_port)

        logger.info("UI 初始化完成")

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=THEME["panel_bg"], corner_radius=0, height=50)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)

        title = ctk.CTkLabel(
            header,
            text="全明星街球派对自动化",
            font=("Microsoft YaHei UI", 18, "bold"),
            text_color=THEME["accent"],
        )
        title.pack(side="left", padx=20, pady=12)

        version = ctk.CTkLabel(
            header,
            text=f"v{self.VERSION}",
            font=("Consolas", 11),
            text_color=THEME["subtext"],
        )
        version.pack(side="right", padx=20, pady=12)

        sep = ctk.CTkFrame(header, fg_color=THEME["border"], height=1)
        sep.pack(side="bottom", fill="x")

    def _build_control_panel(self, parent):
        panel = ctk.CTkFrame(parent, fg_color=THEME["panel_bg"], corner_radius=12,width = 320)
        panel.pack(side="left", fill="both", padx=(0, 10), pady=0, ipadx=12, ipady=12)
        panel.pack_propagate(False)

        panel_title = ctk.CTkLabel(
            panel, text="控制面板",
            font=("Microsoft YaHei UI", 14, "bold"),
            text_color=THEME["text"]
        )
        panel_title.pack(anchor="w", pady=(12, 8), padx=12)

        scroll = ctk.CTkScrollableFrame(
            panel, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=THEME["border"],
            scrollbar_button_hover_color=THEME["accent"],
        )
        scroll.pack(fill="both", expand=True, padx=6, pady=4)

        self._build_port_section(scroll)
        self._build_separator(scroll)
        self._build_mode_section(scroll)
        self._build_separator(scroll)
        self._build_option_section(scroll)
        self._build_separator(scroll)
        self._build_offset_section(scroll)
        self._build_midnight_section(scroll)
        self._build_separator(scroll)
        self._build_error_label(scroll)
        self._build_buttons(scroll)

    def _build_port_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")

        label = ctk.CTkLabel(
            frame, text="多开设置",
            font=("Microsoft YaHei UI", 12, "bold"),
            text_color=THEME["text"]
        )
        label.pack(anchor="w", pady=(0, 6))

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(row, text="多开数量:", font=("Microsoft YaHei UI", 11), text_color=THEME["subtext"]).pack(side="left")

        self.multi_var = ctk.StringVar(value="单开")

        self.multi_menu = ctk.CTkOptionMenu(
            row, values=MULTI_INSTANCE_OPTIONS,
            variable=self.multi_var,
            command=self._on_multi_changed,
            fg_color=THEME["panel_bg"],
            button_color=THEME["border"],
            button_hover_color=THEME["accent"],
            text_color=THEME["text"],
            dropdown_fg_color=THEME["panel_bg"],
            dropdown_hover_color=THEME["border"],
            dropdown_text_color=THEME["text"],
            font=("Microsoft YaHei UI", 11),
            width=100,
        )
        self.multi_menu.pack(side="right")

        frame.pack(fill="x")

        # 端口下拉框容器
        self.port_container = ctk.CTkFrame(frame, fg_color="transparent")
        self.port_container.pack(fill="x", pady=(4, 0))

        # 测试连接行
        test_row = ctk.CTkFrame(frame, fg_color="transparent")
        test_row.pack(fill="x", pady=(6, 0))

        self.test_btn = ctk.CTkButton(
            test_row, text="测试连接",
            command=self._test_connections,
            fg_color=THEME["accent"],
            hover_color=THEME["gold"],
            text_color=THEME["text"],
            font=("Microsoft YaHei UI", 10),
            width=80, height=28,
            corner_radius=6,
        )
        self.test_btn.pack(side="left")

        self.test_result_label = ctk.CTkLabel(
            test_row, text="", font=("Microsoft YaHei UI", 10),
            text_color=THEME["subtext"], anchor="w"
        )
        self.test_result_label.pack(side="left", padx=(8, 0))

        self._rebuild_port_comboxes(1)

    def _rebuild_port_comboxes(self, count: int):
        for w in self.port_container.winfo_children():
            w.destroy()
        self.port_comboxes.clear()
        self.port_labels.clear()

        for i in range(count):
            row = ctk.CTkFrame(self.port_container, fg_color="transparent")
            row.pack(fill="x", pady=2)

            lbl = ctk.CTkLabel(
                row, text=f"端口 {i + 1}:",
                font=("Microsoft YaHei UI", 11),
                text_color=THEME["subtext"],
                width=60,
                anchor="e"
            )
            lbl.pack(side="left", padx=(0, 4))
            self.port_labels.append(lbl)

            port_strs = [str(p) for p in AVAILABLE_PORTS]
            cb = ctk.CTkComboBox(
                row, values=port_strs,
                command=lambda v, idx=i: self._on_port_changed(idx),
                fg_color=THEME["bg"],
                button_color=THEME["border"],
                button_hover_color=THEME["accent"],
                text_color=THEME["text"],
                dropdown_fg_color=THEME["panel_bg"],
                dropdown_text_color=THEME["text"],
                font=("Consolas", 11),
                width=120,
                state="readonly",
            )
            cb.pack(side="left")
            self.port_comboxes.append(cb)

        # 设置默认值
        defaults = {1: [16384], 2: [16384, 16416], 3: [16384, 16416, 16448], 4: [16384, 16416, 16448, 16480]}
        vals = defaults.get(count, [16384])
        for cb, val in zip(self.port_comboxes, vals):
            cb.set(str(val))

        self._validate_ports()

    def _build_separator(self, parent):
        sep = ctk.CTkFrame(parent, fg_color=THEME["border"], height=1)
        sep.pack(fill="x", pady=10, ipady=1)

    def _build_mode_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")

        label = ctk.CTkLabel(
            frame, text="模式选择",
            font=("Microsoft YaHei UI", 12, "bold"),
            text_color=THEME["text"]
        )
        label.pack(anchor="w", pady=(0, 6))

        modes = self.mode_config.get("modes", {})

        # 单选按钮组：互斥选择，王朝 vs 超级联赛
        self.mode_selected_var = ctk.StringVar(value="")  # "" | "dynasty" | "chaolian"

        # 王朝模式组
        dynasty_bar = ctk.CTkFrame(frame, fg_color=THEME["gold"], width=4, corner_radius=2)
        dynasty_bar.pack(side="left", padx=(0, 8), pady=2)

        dynasty_group = ctk.CTkFrame(frame, fg_color="transparent")
        dynasty_group.pack(side="left", fill="x")

        rb1 = ctk.CTkRadioButton(
            dynasty_group, text="王朝模式",
            variable=self.mode_selected_var, value="dynasty",
            command=lambda: self._on_mode_selected(),
            fg_color=THEME["gold"], hover_color=THEME["gold"],
            text_color=THEME["gold"], font=("Microsoft YaHei UI", 11, "bold"),
            radiobutton_width=18, radiobutton_height=18,
        )
        rb1.pack(anchor="w", pady=(0, 4))

        dynasty_options = ctk.CTkFrame(dynasty_group, fg_color="transparent")
        dynasty_options.pack(anchor="w", padx=20, pady=(0, 6))
        self.dynasty_sub_var = ctk.StringVar(value="")
        self.dynasty_options_frame = dynasty_options

        for mode_id in self._get_mode_ids_by_group("dynasty"):
            mode_info = modes.get(mode_id, {})
            c = ctk.CTkRadioButton(
                dynasty_options, text=mode_info.get("display_name", mode_id),
                variable=self.dynasty_sub_var, value=mode_id,
                command=self._on_any_mode_changed,
                fg_color=THEME["border"], hover_color=THEME["gold"],
                text_color=THEME["subtext"], font=("Microsoft YaHei UI", 10),
                radiobutton_width=14, radiobutton_height=14,
            )
            c.pack(anchor="w", pady=1)

        # 超级联赛模式组
        chaoji_bar = ctk.CTkFrame(frame, fg_color=THEME["purple"], width=4, corner_radius=2)
        chaoji_bar.pack(side="left", padx=(0, 8), pady=2)

        chaoji_match = ctk.CTkFrame(frame, fg_color="transparent")
        chaoji_match.pack(side="left", fill="x")

        rb2 = ctk.CTkRadioButton(
            chaoji_match, text="超级联赛模式",
            variable=self.mode_selected_var, value="chaolian",
            command=lambda: self._on_mode_selected(),
            fg_color=THEME["purple"], hover_color=THEME["purple"],
            text_color=THEME["purple"], font=("Microsoft YaHei UI", 11, "bold"),
            radiobutton_width=18, radiobutton_height=18,
        )
        rb2.pack(anchor="w", pady=(0, 4))

        chaoji_options = ctk.CTkFrame(chaoji_match, fg_color="transparent")
        chaoji_options.pack(anchor="w", padx=20, pady=(0, 6))
        self.chaoji_sub_var = ctk.StringVar(value="")
        self.chaoji_options_frame = chaoji_options

        for mode_id in self._get_mode_ids_by_group("chaolian"):
            mode_info = modes.get(mode_id, {})
            c = ctk.CTkRadioButton(
                chaoji_options, text=mode_info.get("display_name", mode_id),
                variable=self.chaoji_sub_var, value=mode_id,
                command=self._on_any_mode_changed,
                fg_color=THEME["border"], hover_color=THEME["purple"],
                text_color=THEME["subtext"], font=("Microsoft YaHei UI", 10),
                radiobutton_width=14, radiobutton_height=14,
            )
            c.pack(anchor="w", pady=1)

        # 初始隐藏所有子选项
        self._update_sub_options_visibility()

        frame.pack(fill="x")

    def _build_option_section(self, parent):
        """策略选项（选中模式后显示的子复选框）"""
        self.option_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.option_frame.pack(fill="x")
        # 由 _on_any_mode_changed 动态填充

    def _build_offset_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")

        ctk.CTkLabel(
            frame, text="偏差点击:",
            font=("Microsoft YaHei UI", 11),
            text_color=THEME["subtext"],
        ).pack(side="left")

        self.offset_var = ctk.StringVar(value=str(self.settings.get("click_offset", 10)))

        offset_entry = ctk.CTkEntry(
            frame,
            textvariable=self.offset_var,
            width=70,
            fg_color=THEME["bg"],
            border_color=THEME["border"],
            text_color=THEME["text"],
            font=("Consolas", 11),
            justify="center",
        )
        offset_entry.pack(side="right")
        offset_entry.bind("<FocusOut>", lambda e: self._save_offset())

        frame.pack(fill="x", pady=(0, 8))

    def _build_midnight_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")

        self.midnight_var = ctk.BooleanVar(value=self.settings.get("midnight_enabled", False))

        cb = ctk.CTkCheckBox(
            frame, text="凌晨 12:01 以后执行",
            variable=self.midnight_var,
            command=self._on_midnight_changed,
            fg_color=THEME["border"], hover_color=THEME["accent"],
            text_color=THEME["subtext"],
            font=("Microsoft YaHei UI", 11),
            checkbox_width=18, checkbox_height=18,
        )
        cb.pack(anchor="w")

        frame.pack(fill="x", pady=(0, 8))

    def _build_error_label(self, parent):
        self.error_label = ctk.CTkLabel(
            parent, text="",
            font=("Microsoft YaHei UI", 11, "bold"),
            text_color=THEME["danger"],
            wraplength=300,
            justify="left",
            anchor="w",
        )
        self.error_label.pack(fill="x", pady=(0, 6))

    def _build_buttons(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")

        self.full_auto_btn = ctk.CTkButton(
            frame, text="全自动任务",
            command=self._on_open_full_auto,
            fg_color=THEME["purple"],
            hover_color="#7C3AED",
            text_color="#FFFFFF",
            font=("Microsoft YaHei UI", 13, "bold"),
            height=40, corner_radius=8,
        )
        self.full_auto_btn.pack(fill="x", pady=(0, 6))

        self.start_btn = ctk.CTkButton(
            frame, text="开始执行",
            command=self._on_start,
            fg_color=THEME["accent"],
            hover_color="#00B894",
            text_color="#0D1B2A",
            font=("Microsoft YaHei UI", 13, "bold"),
            height=40, corner_radius=8,
        )
        self.start_btn.pack(fill="x", pady=(0, 6))

        self.stop_btn = ctk.CTkButton(
            frame, text="停止执行",
            command=self._on_stop,
            fg_color=THEME["danger"],
            hover_color="#E55A5A",
            text_color="#FFFFFF",
            font=("Microsoft YaHei UI", 13, "bold"),
            height=40, corner_radius=8,
            state="disabled",
        )
        self.stop_btn.pack(fill="x")

        frame.pack(fill="x")

    def _build_right_panel(self, parent):
        """右侧面板：仪表盘(上) + 日志(下)"""
        panel = ctk.CTkFrame(parent, fg_color=THEME["panel_bg"], corner_radius=12)
        panel.pack(side="right", fill="both", expand=True, padx=0, pady=0)

        self._build_dashboard(panel)

        sep = ctk.CTkFrame(panel, fg_color=THEME["border"], height=1)
        sep.pack(fill="x", padx=10)

        self._build_log_panel(panel)

    def _build_dashboard(self, parent):
        """构建信息仪表盘"""
        self.dashboard_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.dashboard_frame.pack(fill="x", padx=8, pady=(8, 4))

        # 端口选择器容器
        self.dashboard_tabs_frame = ctk.CTkFrame(self.dashboard_frame, fg_color="transparent")
        self.dashboard_tabs_frame.pack(fill="x", pady=(2, 4))

        self._dashboard_port = None
        self._dashboard_tab_buttons: dict = {}

        # 卡片区域：两行，每行三个卡片，用 pack 排列
        card_defs = [
            ("连接状态", "c_status"),
            ("CPU占用", "c_cpu"),
            ("分辨率", "c_resolution"),
            ("当前模式", "c_mode"),
            ("胜利次数", "c_victory"),
            ("失败次数", "c_failure"),
        ]

        self.dashboard_cards = {}
        for row_idx in range(2):
            row_frame = ctk.CTkFrame(self.dashboard_frame, fg_color="transparent")
            row_frame.pack(fill="x", pady=2)
            for col_idx in range(3):
                idx = row_idx * 3 + col_idx
                title, key = card_defs[idx]

                card = ctk.CTkFrame(row_frame, fg_color=THEME["bg"], corner_radius=8)
                card.pack(side="left", fill="x", expand=True, padx=3)

                ctk.CTkLabel(
                    card, text=title,
                    font=("Microsoft YaHei UI", 9),
                    text_color=THEME["subtext"],
                ).pack(pady=(8, 0))

                val = ctk.CTkLabel(
                    card, text="--",
                    font=("Consolas", 13, "bold"),
                    text_color=THEME["text"],
                )
                val.pack(pady=(0, 8))

                self.dashboard_cards[key] = val

    def _refresh_dashboard_tabs(self, ports: list):
        """重建仪表盘端口切换标签"""
        for w in self.dashboard_tabs_frame.winfo_children():
            w.destroy()
        self._dashboard_tab_buttons.clear()

        if not ports:
            return

        for port in ports:
            label = PORT_LABELS.get(port, str(port))
            btn = ctk.CTkButton(
                self.dashboard_tabs_frame, text=label,
                command=lambda p=port: self._switch_dashboard_port(p),
                fg_color=THEME["border"],
                hover_color=THEME["accent"],
                text_color=THEME["subtext"],
                font=("Microsoft YaHei UI", 10),
                width=80, height=26, corner_radius=6,
            )
            btn.pack(side="left", padx=3)
            self._dashboard_tab_buttons[port] = btn

        self._switch_dashboard_port(ports[0])

    def _switch_dashboard_port(self, port: int):
        """切换仪表盘显示端口"""
        self._dashboard_port = port
        for p, btn in self._dashboard_tab_buttons.items():
            if p == port:
                btn.configure(fg_color=THEME["accent"], text_color=THEME["bg"])
            else:
                btn.configure(fg_color=THEME["border"], text_color=THEME["subtext"])

    def _init_dashboard_port(self):
        """初始化仪表盘端口（在 UI 构建完成后调用）"""
        ports = self._get_ports()
        if ports:
            self._dashboard_port = ports[0]

    def _poll_dashboard(self):
        """每秒轮询更新仪表盘数据"""
        try:
            port = self._dashboard_port
            if port is None:
                ports = self._get_ports()
                port = ports[0] if ports else None

            if port is not None:
                stats = get_strategy_stats(port)

                # 连接状态
                status = stats.get("status", "")
                if status == "运行中":
                    self.dashboard_cards["c_status"].configure(text="已连接", text_color=THEME["accent"])
                else:
                    # 检查是否有屏幕尺寸记录（说明曾连接过）
                    size = get_screen_size(port)
                    if size:
                        self.dashboard_cards["c_status"].configure(text="已连接", text_color=THEME["accent"])
                    else:
                        self.dashboard_cards["c_status"].configure(text="未连接", text_color=THEME["danger"])

                # CPU
                cpu = psutil.cpu_percent()
                if cpu < 25:
                    cpu_color = THEME["accent"]
                elif cpu < 50:
                    cpu_color = THEME["warning"]
                else:
                    cpu_color = THEME["danger"]
                self.dashboard_cards["c_cpu"].configure(text=f"{cpu:.0f}%", text_color=cpu_color)

                # 分辨率
                size = get_screen_size(port)
                if size:
                    self.dashboard_cards["c_resolution"].configure(text=f"{size[0]}x{size[1]}", text_color=THEME["text"])
                else:
                    self.dashboard_cards["c_resolution"].configure(text="--", text_color=THEME["subtext"])

                # 当前模式
                mode = stats.get("mode", "--")
                if mode == "--":
                    self.dashboard_cards["c_mode"].configure(text="--", text_color=THEME["subtext"])
                else:
                    self.dashboard_cards["c_mode"].configure(text=mode, text_color=THEME["text"])

                # 胜利
                victory = stats.get("victory", 0)
                self.dashboard_cards["c_victory"].configure(text=str(victory), text_color=THEME["accent"])

                # 失败
                failure = stats.get("failure", 0)
                self.dashboard_cards["c_failure"].configure(text=str(failure), text_color=THEME["danger"])
        except Exception:
            pass
        finally:
            self.after(1000, self._poll_dashboard)

    def _build_log_panel(self, parent):
        panel = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        panel.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.pack(fill="x", pady=(8, 8))

        title = ctk.CTkLabel(
            header, text="运行日志",
            font=("Microsoft YaHei UI", 14, "bold"),
            text_color=THEME["text"]
        )
        title.pack(side="left")

        self.clear_btn = ctk.CTkButton(
            header, text="清空",
            command=self._on_clear_log,
            fg_color="transparent",
            hover_color=THEME["border"],
            text_color=THEME["subtext"],
            font=("Microsoft YaHei UI", 10),
            width=50, height=24, corner_radius=4,
            border_width=1, border_color=THEME["border"],
        )
        self.clear_btn.pack(side="right")

        self.log_box = LogTextBox(panel, wrap="word", height=1)
        self.log_box.pack(fill="both", expand=True, padx=4, pady=(0, 4))

    # ==================== 事件处理 ====================

    def _on_multi_changed(self, value: str):
        count_map = {"单开": 1, "双开": 2, "三开": 3, "四开": 4}
        count = count_map.get(value, 1)
        self._rebuild_port_comboxes(count)
        self._save_current_settings()

    def _on_port_changed(self, idx: int):
        self._validate_ports()
        self._save_current_settings()

    def _validate_ports(self):
        ports = [int(cb.get()) for cb in self.port_comboxes]
        if len(ports) != len(set(ports)):
            self.error_label.configure(text="端口不能重复！")
            if hasattr(self, "start_btn"):
                self.start_btn.configure(state="disabled")
            return False
        else:
            if hasattr(self, "error_label"):
                self.error_label.configure(text="")
            if hasattr(self, "start_btn") and not self.manager:
                self.start_btn.configure(state="normal")
            return True

    def _on_mode_selected(self):
        """模式组单选按钮切换"""
        # 切换组时清空另一组的子选择
        if self.mode_selected_var.get() == "dynasty":
            self.chaoji_sub_var.set("")
        else:
            self.dynasty_sub_var.set("")
        self._update_sub_options_visibility()
        self._on_any_mode_changed()

    def _update_sub_options_visibility(self):
        """根据选中的模式组显示/隐藏对应子选项"""
        selected = self.mode_selected_var.get()
        self.dynasty_options_frame.pack_forget()
        self.chaoji_options_frame.pack_forget()
        if selected == "dynasty":
            self.dynasty_options_frame.pack(anchor="w", padx=20, pady=(0, 6))
        elif selected == "chaolian":
            self.chaoji_options_frame.pack(anchor="w", padx=20, pady=(0, 6))

    def _on_any_mode_changed(self):
        self._rebuild_option_section()
        self._save_current_settings()

    def _rebuild_option_section(self):
        for w in self.option_frame.winfo_children():
            w.destroy()

        enabled_modes = self._get_enabled_modes()
        if not enabled_modes:
            return

        modes = self.mode_config.get("modes", {})
        for mode_id in enabled_modes:
            mode_info = modes.get(mode_id, {})
            options = mode_info.get("options", [])

            mode_label = ctk.CTkLabel(
                self.option_frame, text=f"  {mode_info.get('display_name', mode_id)} 选项:",
                font=("Microsoft YaHei UI", 10, "bold"),
                text_color=THEME["subtext"],
                anchor="w",
            )
            mode_label.pack(anchor="w", pady=(4, 2))

            for opt in options:
                opt_var = ctk.StringVar(value=opt["id"])
                self.mode_option_vars.setdefault(mode_id, {})
                self.mode_option_vars[mode_id][opt["id"]] = ctk.BooleanVar(
                    value=opt.get("default", False)
                )

                cb = ctk.CTkCheckBox(
                    self.option_frame, text=opt["display_name"],
                    variable=self.mode_option_vars[mode_id][opt["id"]],
                    fg_color=THEME["border"], hover_color=THEME["accent"],
                    text_color=THEME["subtext"],
                    font=("Microsoft YaHei UI", 10),
                    checkbox_width=16, checkbox_height=16,
                    command=self._save_current_settings,
                )
                cb.pack(anchor="w", padx=20)

    def _build_mode_option_var(self, mode_id: str, opt_id: str):
        var = ctk.BooleanVar(value=False)
        if mode_id not in self.mode_option_vars:
            self.mode_option_vars[mode_id] = {}
        self.mode_option_vars[mode_id][opt_id] = var
        return var

    def _save_offset(self):
        try:
            val = int(self.offset_var.get())
            self.settings["click_offset"] = val
            self._save_settings()
        except ValueError:
            self.offset_var.set(str(self.settings.get("click_offset", 10)))

    def _on_midnight_changed(self):
        self.settings["midnight_enabled"] = self.midnight_var.get()
        self._save_settings()
        self._schedule_midnight()

    def _on_clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("0.0", "end")
        self.log_box.configure(state="disabled")

    def _poll_log_queue(self):
        """定时从日志队列中取出消息并显示，防止从非主线程直接操作 Tkinter。"""
        try:
            messages = logger.drain_queue()
            for formatted_msg, level in messages:
                self.log_box.append_log(formatted_msg)
        except Exception:
            pass
        finally:
            # 根据队列积压动态调整轮询间隔，有积压时加快，空闲时放慢
            delay = 100 if logger.get_queue_size() > 10 else 300
            self.after(delay, self._poll_log_queue)

    # ==================== 核心逻辑 ====================

    def _get_mode_ids_by_group(self, group: str) -> list:
        """根据 group 从 mode_config.json 动态获取该组所有子模式的 mode_id"""
        modes = self.mode_config.get("modes", {})
        return [
            mid for mid, info in modes.items()
            if info.get("group") == group
        ]

    def _get_enabled_modes(self) -> list:
        selected_group = self.mode_selected_var.get()
        if selected_group == "dynasty" and self.dynasty_sub_var.get():
            return [self.dynasty_sub_var.get()]
        if selected_group == "chaolian" and self.chaoji_sub_var.get():
            return [self.chaoji_sub_var.get()]
        return []

    def _get_ports(self) -> list:
        return [int(cb.get()) for cb in self.port_comboxes]

    def _test_connections(self):
        """后台线程检测所有端口连接状态，弹窗展示结果"""
        ports = self._get_ports()
        if not ports:
            messagebox.showwarning("提示", "请先配置端口")
            return

        self.test_btn.configure(state="disabled", text="检测中…")
        self.test_result_label.configure(text="")

        def worker():
            from services.adb_service import ADBService
            ok, fail = [], []
            for port in ports:
                try:
                    adb = ADBService(port=port)
                    if adb.connect():
                        ok.append(str(port))
                        adb.disconnect()
                    else:
                        fail.append(str(port))
                except Exception:
                    fail.append(str(port))

            def done():
                self.test_btn.configure(state="normal", text="测试连接")
                if not ok and not fail:
                    messagebox.showinfo("连接测试", "没有可检测的端口")
                    return
                lines = []
                if ok:
                    lines.append(f"连接成功 ({len(ok)}): {', '.join(ok)}")
                if fail:
                    lines.append(f"连接失败 ({len(fail)}): {', '.join(fail)}")
                title = "全部成功" if not fail else "部分失败"
                messagebox.showinfo(title, "\n".join(lines))

                self.test_result_label.configure(
                    text=f"成功 {len(ok)} / 失败 {len(fail)}",
                    text_color="green" if not fail else "orange",
                )

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _get_click_offset(self) -> int:
        try:
            return int(self.offset_var.get())
        except ValueError:
            return 10

    def _save_current_settings(self):
        multi_map = {"单开": 1, "双开": 2, "三开": 3, "四开": 4}
        self.settings["multi_instance_count"] = multi_map.get(self.multi_var.get(), 1)
        self.settings["ports"] = self._get_ports()
        self.settings["selected_group"] = self.mode_selected_var.get()
        self.settings["selected_mode"] = (
            self.dynasty_sub_var.get() or self.chaoji_sub_var.get()
        )
        # 同步 UI 勾选状态到 strategy_options
        self.settings["strategy_options"] = {
            mode_id: {opt_id: var.get() for opt_id, var in opts.items()}
            for mode_id, opts in self.mode_option_vars.items()
        }
        self._save_settings()

    def _restore_settings(self):
        s = self.settings
        count = s.get("multi_instance_count", 1)
        self.multi_var.set({1: "单开", 2: "双开", 3: "三开", 4: "四开"}.get(count, "单开"))
        self._rebuild_port_comboxes(count)

        ports = s.get("ports", [16384])
        for cb, port in zip(self.port_comboxes, ports):
            if port in AVAILABLE_PORTS:
                cb.set(str(port))

        self.offset_var.set(str(s.get("click_offset", 10)))
        self.midnight_var.set(s.get("midnight_enabled", False))

        # 恢复模式组选择
        selected_group = s.get("selected_group", "")
        if selected_group in ("dynasty", "chaolian"):
            self.mode_selected_var.set(selected_group)
            self._update_sub_options_visibility()
        else:
            self.mode_selected_var.set("")
            self._update_sub_options_visibility()

        dynasty_ids = self._get_mode_ids_by_group("dynasty")
        street_ids = self._get_mode_ids_by_group("chaolian")
        # 恢复子模式选择
        selected_mode = s.get("selected_mode", "")
        if selected_mode in dynasty_ids:
            self.dynasty_sub_var.set(selected_mode)
        elif selected_mode in street_ids:
            self.chaoji_sub_var.set(selected_mode)

        self._schedule_midnight()

    def _on_start(self):
        if self.manager and self.manager.is_running():
            return

        modes = self._get_enabled_modes()
        if not modes:
            self.error_label.configure(text="请至少选择一个模式！")
            return

        if not self._validate_ports():
            return

        self.error_label.configure(text="")
        ports = self._get_ports()
        click_offset = self._get_click_offset()
        options = self.settings.get("strategy_options", {})

        self._save_current_settings()

        logger.info("=" * 50)
        logger.info("全明星街球派对自动化脚本启动")
        logger.info(f"版本: {self.VERSION}")
        logger.info(f"端口: {ports}")
        logger.info(f"模式: {modes}")
        logger.info(f"偏差点击: {click_offset}")
        logger.info("=" * 50)

        self.manager = StrategyManager(ports)

        # 构建策略类列表
        strategy_classes = []
        for mode_id in modes:
            if mode_id in STRATEGY_MAP:
                strategy_cls = STRATEGY_MAP[mode_id]
                mode_opts = dict(options.get(mode_id, {}))
                # 为策略注入配置（用默认参数捕获当前值，防止闭包陷阱）
                def make_strategy(cls, opts, offset_val=click_offset):
                    class Configured(cls):
                        def __init__(self, port):
                            super().__init__(port, opts, offset_val)
                            self._strategy_name = cls.__name__
                    return Configured
                strategy_classes.append(make_strategy(strategy_cls, mode_opts))
            else:
                logger.warning(f"未找到策略: {mode_id}")

        self.manager.start(strategy_classes)

        self._refresh_dashboard_tabs(ports)

        self.start_btn.configure(state="disabled", text="执行中...")
        self.stop_btn.configure(state="normal")
        self.full_auto_btn.configure(state="disabled")

        # 引导线程：等待屏幕尺寸 → 监控运行 → 清理
        self._bootstrap = threading.Thread(
            target=self._run_bootstrap,
            args=(ports,),
            daemon=True,
            name="BootstrapThread"
        )
        self._bootstrap.start()

    def _on_sizes_ready(self, sizes: dict):
        """所有端口屏幕尺寸获取完毕后，在日志中汇总打印"""
        lines = []
        for port, size in sizes.items():
            lines.append(f"  端口 {port}: {size[0]}x{size[1]}")
        logger.info("屏幕分辨率:\n" + "\n".join(lines))

    def _run_bootstrap(self, expected_ports):
        """后台引导线程：等待屏幕尺寸 → 监控运行 → 清理"""
        import time
        from core.strategy_manager import get_all_screen_sizes

        # 阶段 1：等待屏幕尺寸
        for _ in range(30):
            if stop_event.is_set():
                break
            sizes = get_all_screen_sizes()
            if all(p in sizes for p in expected_ports):
                self.after(0, lambda s=sizes: self._on_sizes_ready(s))
                break
            time.sleep(0.5)

        # 阶段 2：等待管理器停止
        while self.manager and self.manager.is_running():
            time.sleep(0.5)

        # 阶段 3：清理
        self.after(0, self._on_execution_finished)

    def _on_execution_finished(self):
        if self.manager is None:
            return  # 已清理，防止 bootstrap 与 stop 回调重复触发
        self.start_btn.configure(state="normal", text="开始执行")
        self.stop_btn.configure(state="disabled", text="停止执行")
        self.full_auto_btn.configure(state="normal")
        self.manager = None
        logger.info("执行完成")

    def _on_stop(self):
        if not self.manager or not self.manager.is_running():
            return
        logger.info("正在停止...")
        self.stop_btn.configure(state="disabled", text="停止中...")
        self.manager.stop(on_finished=lambda: self.after(0, self._on_execution_finished))

    def _on_open_full_auto(self):
        saved = self.settings.get("full_auto_task", {}).get("tasks", [])
        FullAutoWindow(
            master=self,
            mode_config=self.mode_config.get("modes", {}),
            saved_tasks=saved,
            callback_on_start=self._on_full_auto_start,
            callback_on_save=self._on_full_auto_save,
        )

    def _on_full_auto_start(self, task_list: list):
        if not self._validate_ports():
            return
        self.error_label.configure(text="")

        self._on_full_auto_save(task_list)

        ports = self._get_ports()
        click_offset = self._get_click_offset()

        logger.info("=" * 50)
        logger.info("全自动任务启动")
        logger.info(f"端口: {ports}")
        logger.info(f"任务数: {len(task_list)}")
        for i, t in enumerate(task_list):
            logger.info(f"  {i+1}. {t.get('display_name', t['mode_id'])}")
        logger.info("=" * 50)

        self.manager = StrategyManager(ports)

        def make_full_auto(tasks, offset_val=click_offset):
            config = {"tasks": tasks}
            class ConfiguredFullAuto(FullAutoTaskStrategy):
                def __init__(self, port):
                    super().__init__(port, config, offset_val)
                    self._strategy_name = "FullAutoTask"
            return ConfiguredFullAuto

        strategy_classes = [make_full_auto(task_list)]
        self.manager.start(strategy_classes)

        self._refresh_dashboard_tabs(ports)
        self.start_btn.configure(state="disabled", text="执行中...")
        self.stop_btn.configure(state="normal")
        self.full_auto_btn.configure(state="disabled")

        self._bootstrap = threading.Thread(
            target=self._run_bootstrap,
            args=(ports,),
            daemon=True,
            name="BootstrapThread"
        )
        self._bootstrap.start()

    def _on_full_auto_save(self, task_list: list):
        self.settings["full_auto_task"] = {"tasks": task_list}
        self._save_settings()
        logger.info("全自动任务配置已保存")

    def _schedule_midnight(self):
        if hasattr(self, "_midnight_timer") and self._midnight_timer:
            self._midnight_timer.cancel()

        if not self.midnight_var.get():
            return

        now = datetime.datetime.now()
        target = now.replace(hour=0, minute=1, second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)

        delay = (target - now).total_seconds()
        logger.info(f"已设置凌晨执行，定时 {delay:.0f} 秒后启动")

        def _delayed_start():
            logger.info("凌晨时间已到，开始执行")
            self.after(0, self._on_start)

        self._midnight_timer = threading.Timer(delay, _delayed_start)
        self._midnight_timer.daemon = True
        self._midnight_timer.start()

    def destroy(self):
        if hasattr(self, "_midnight_timer") and self._midnight_timer:
            self._midnight_timer.cancel()
        if self.manager:
            self.manager.stop()
        super().destroy()
