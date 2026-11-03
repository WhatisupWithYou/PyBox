#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demo 窗口 —— 演示 AppRunner 的调用方式。

界面布局:
  ┌──────────────────────────────────────────┐
  │  PyBox — AppRunner 演示                   │
  ├──────────────────────────────────────────┤
  │  脚本路径: [______________________] [浏览] │
  │  应用类型: ○ GUI  ● RPA                    │
  │                                           │
  │  [▶ 运行]  [■ 停止]    状态: 空闲          │
  ├──────────────────────────────────────────┤
  │  QTextEdit（只读，黑底绿字，等宽字体）      │
  │  > 12:00:00 [STDOUT] 脚本输出内容...       │
  │  > 12:00:01 [STDERR] 错误输出...           │
  │  > 12:00:02 [INFO]  进程已启动, PID=1234   │
  │  > 12:00:05 [INFO]  进程已退出, code=0     │
  └──────────────────────────────────────────┘

  直接运行本文件即可体验完整交互流程。
"""

from __future__ import annotations

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QRadioButton,
    QButtonGroup,
    QGroupBox,
    QFileDialog,
    QMessageBox,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor, QTextCursor

# 确保项目根目录在 sys.path 中，使 core 包可导入
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.app_runner import AppRunner, AppState, AppType

logger = logging.getLogger("PyBox.Demo")


# ═══════════════════════════════════════════════════════════════
#  演示主窗口
# ═══════════════════════════════════════════════════════════════

class DemoWindow(QMainWindow):
    """演示 AppRunner 用法的交互窗口。"""

    _WINDOW_TITLE = "PyBox — AppRunner 演示"
    _DEFAULT_SIZE = (900, 620)

    def __init__(self) -> None:
        super().__init__()
        self._runner: AppRunner | None = None

        self._init_ui()
        self._connect_runner(None)  # 初始禁用控件

    # ── UI 构建 ─────────────────────────────────────────────

    def _init_ui(self) -> None:
        """构建完整界面布局。"""
        self.setWindowTitle(self._WINDOW_TITLE)
        self.resize(*self._DEFAULT_SIZE)

        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setSpacing(10)
        root_layout.setContentsMargins(12, 12, 12, 12)

        # ── 配置区 ──
        config_group = self._build_config_group()
        root_layout.addWidget(config_group)

        # ── 控制栏 ──
        control_bar = self._build_control_bar()
        root_layout.addLayout(control_bar)

        # ── 日志输出区 ──
        log_group = QGroupBox("实时日志输出")
        log_layout = QVBoxLayout(log_group)

        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setFont(QFont("Consolas", 10))
        self._log_view.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #b0ffb0;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        self._log_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        # 自动滚动到底部
        self._log_view.textChanged.connect(self._scroll_log_to_bottom)
        log_layout.addWidget(self._log_view)

        root_layout.addWidget(log_group, stretch=1)

    def _build_config_group(self) -> QGroupBox:
        """构建脚本路径 & 类型选择区域。"""
        group = QGroupBox("子进程配置")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        # ── 脚本路径行 ──
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("脚本路径:"))

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("选择要运行的 .py 脚本...")
        self._path_edit.setClearButtonEnabled(True)
        path_row.addWidget(self._path_edit, stretch=1)

        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._on_browse)
        path_row.addWidget(browse_btn)

        layout.addLayout(path_row)

        # ── 应用类型行 ──
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("应用类型:"))

        self._type_group = QButtonGroup(self)

        self._radio_gui = QRadioButton("GUI (独立界面应用)")
        self._radio_rpa = QRadioButton("RPA (后台自动化，捕获输出)")
        self._radio_rpa.setChecked(True)

        self._type_group.addButton(self._radio_gui, 0)
        self._type_group.addButton(self._radio_rpa, 1)

        type_row.addWidget(self._radio_gui)
        type_row.addWidget(self._radio_rpa)
        type_row.addStretch()

        layout.addLayout(type_row)
        return group

    def _build_control_bar(self) -> QHBoxLayout:
        """构建运行/停止按钮 & 状态标签。"""
        bar = QHBoxLayout()

        self._btn_run = QPushButton("▶  运行")
        self._btn_run.setFixedHeight(34)
        self._btn_run.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 24px;
                font-weight: bold;
            }
            QPushButton:hover  { background-color: #1a8cde; }
            QPushButton:pressed { background-color: #005f9e; }
            QPushButton:disabled { background-color: #555; color: #999; }
        """)
        self._btn_run.clicked.connect(self._on_run)
        bar.addWidget(self._btn_run)

        self._btn_stop = QPushButton("■  停止")
        self._btn_stop.setFixedHeight(34)
        self._btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #c0392b;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 24px;
                font-weight: bold;
            }
            QPushButton:hover  { background-color: #e74c3c; }
            QPushButton:pressed { background-color: #962d22; }
            QPushButton:disabled { background-color: #555; color: #999; }
        """)
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_stop.setEnabled(False)
        bar.addWidget(self._btn_stop)

        bar.addSpacing(16)

        bar.addWidget(QLabel("状态:"))

        self._status_label = QLabel("空闲")
        self._status_label.setStyleSheet(
            "font-weight: bold; color: #888; padding: 2px 8px;"
        )
        bar.addWidget(self._status_label)

        bar.addStretch()
        return bar

    # ── 槽函数 ──────────────────────────────────────────────

    def _on_browse(self) -> None:
        """浏览选择 Python 脚本文件。"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Python 脚本",
            os.getcwd(),
            "Python 脚本 (*.py);;所有文件 (*.*)",
        )
        if file_path:
            self._path_edit.setText(file_path)

    def _on_run(self) -> None:
        """启动子进程。"""
        script = self._path_edit.text().strip()
        if not script:
            QMessageBox.warning(self, "提示", "请先选择或输入脚本路径。")
            return

        app_type = AppType.RPA if self._radio_rpa.isChecked() else AppType.GUI

        # 创建 AppRunner（每次运行新建一个实例，保证状态干净）
        self._runner = AppRunner(script, app_type)
        self._connect_runner(self._runner)

        success = self._runner.start()
        if not success:
            self._append_log("[ERROR]", "进程启动失败，请检查脚本路径和日志。", "#e74c3c")

    def _on_stop(self) -> None:
        """停止子进程。"""
        if self._runner is not None:
            self._runner.stop_app()

    def _connect_runner(self, runner: AppRunner | None) -> None:
        """将 AppRunner 的信号绑定到 UI 控件。

        每次启动新进程前重新绑定，防止旧信号残留。
        传入 None 时仅重置控件到初始状态。
        """
        # 先断开旧 runner 的所有信号（通过删除引用让 Qt 自动清理）
        if runner is None:
            self._update_controls(AppState.IDLE)
            return

        runner.log_received.connect(self._on_log_line)
        runner.app_started.connect(self._on_app_started)
        runner.app_finished.connect(self._on_app_finished)
        runner.app_error.connect(self._on_app_error)
        runner.state_changed.connect(self._update_controls)

    def _on_log_line(self, text: str) -> None:
        """收到子进程日志行 → 追加到日志视图。"""
        color = "#b0ffb0"  # 默认绿色
        if text.startswith("[STDERR]"):
            color = "#ff6b6b"  # 红色标示错误
        elif "[ERROR]" in text:
            color = "#e74c3c"
        elif "[INFO]" in text or "[WARN]" in text:
            color = "#ffd93d"

        self._append_log("", text, color)

    def _on_app_started(self, pid: int) -> None:
        self._append_log("[INFO]", f"子进程已启动，PID={pid}", "#4ec9f0")

    def _on_app_finished(self, exit_code: int, exit_status: int) -> None:
        status = "正常退出" if exit_status == 0 else "异常崩溃"
        color = "#4ec9f0" if exit_status == 0 else "#ff6b6b"
        self._append_log(
            "[INFO]", f"子进程已结束: exit_code={exit_code}, 状态={status}", color
        )

    def _on_app_error(self, message: str) -> None:
        self._append_log("[ERROR]", message, "#e74c3c")

    def _update_controls(self, state: AppState) -> None:
        """根据 AppRunner 状态更新 UI 控件的启用/禁用。"""
        is_idle = state in (AppState.IDLE, AppState.ERROR, AppState.EXITED)
        is_running = state in (AppState.RUNNING, AppState.STARTING)

        self._btn_run.setEnabled(is_idle)
        self._btn_stop.setEnabled(is_running)
        self._path_edit.setEnabled(is_idle)
        self._radio_gui.setEnabled(is_idle)
        self._radio_rpa.setEnabled(is_idle)

        # 状态标签
        state_text_map = {
            AppState.IDLE:     ("空闲",   "#888"),
            AppState.STARTING: ("启动中", "#ffd93d"),
            AppState.RUNNING:  ("运行中", "#2ecc71"),
            AppState.STOPPING: ("停止中", "#e74c3c"),
            AppState.ERROR:    ("错误",   "#e74c3c"),
            AppState.EXITED:   ("已退出", "#4ec9f0"),
        }
        text, color = state_text_map.get(state, (state.name, "#888"))
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"font-weight: bold; color: {color}; padding: 2px 8px;"
        )

    def _append_log(self, tag: str, message: str, color: str) -> None:
        """向日志视图追加一条带时间戳的彩色日志。"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        if tag:
            line = f'<span style="color:#888;">{timestamp}</span> '
            line += f'<span style="color:{color};font-weight:bold;">{tag}</span> '
            line += f'<span style="color:{color};">{message}</span>'
        else:
            # 原始日志行（如 AppRunner 发出的完整 prefix 行）
            line = (
                f'<span style="color:#888;">{timestamp}</span> '
                f'<span style="color:{color};">{message}</span>'
            )
        self._log_view.append(line)

    def _scroll_log_to_bottom(self) -> None:
        """日志自动滚动到最底部。"""
        cursor = self._log_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._log_view.setTextCursor(cursor)

    def closeEvent(self, event) -> None:
        """窗口关闭时确保子进程被终止。"""
        if self._runner is not None and self._runner.is_running():
            self._runner.stop_app()
        event.accept()


# ═══════════════════════════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════════════════════════

def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    app = QApplication(sys.argv)
    app.setApplicationName("PyBox-Demo")

    window = DemoWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
