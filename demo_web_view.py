#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web 视图演示 —— 完整演示 "拉起后端 → 加载网页 → 关闭释放" 闭环。

界面：
  ┌───────────────────────────────────────────────────┐
  │  PyBox — Web 视图演示                             │
  ├───────────────────────────────────────────────────┤
  │  脚本: [_______________] [浏览]  端口: [自动]      │
  │  [▶ 启动并加载]  [■ 停止]  状态: 空闲              │
  ├───────────────────────────────────────────────────┤
  │  ┌─ 日志输出 ─────────────────────────────────┐   │
  │  │ > 14:30:01 [INFO] 分配端口: 8080           │   │
  │  │ > 14:30:02 [INFO] Web 服务就绪              │   │
  │  │ > ...                                       │   │
  │  └────────────────────────────────────────────┘   │
  ├───────────────────────────────────────────────────┤
  │  ┌─ Web 视图 ─────────────────────────────────┐   │
  │  │  [🌐 http://127.0.0.1:8080]      [✕ 关闭]  │   │
  │  │                                              │   │
  │  │         QWebEngineView                       │   │
  │  │         (加载中的 spinner / 网页内容)          │   │
  │  │                                              │   │
  │  └──────────────────────────────────────────────┘   │
  └───────────────────────────────────────────────────┘

闭环流程:
  1. 用户选择 server.py，点击"启动并加载"。
  2. 平台自动分配端口，后台启动 python server.py --port {port}。
  3. 轮询探活 http://127.0.0.1:{port}，就绪后 WebViewHost 加载 URL。
  4. 用户点击"停止"或关闭窗口／Tab → 自动 kill 后端进程树，释放端口。

运行方式:
    python demo_web_view.py

依赖:
    pip install PySide6 PySide6-WebEngine
"""

from __future__ import annotations

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

# 确保项目根在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.web_app_runner import WebAppRunner, WebAppState
from core.port_manager import is_port_free

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
    QGroupBox,
    QFileDialog,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QFrame,
)
from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QFont, QTextCursor

logger = logging.getLogger("PyBox.DemoWebView")


# ═══════════════════════════════════════════════════════════════
#  WebViewHost —— 内嵌 Web 视图控件
# ═══════════════════════════════════════════════════════════════

class WebViewHost(QWidget):
    """
    可嵌入的 Web 视图宿主控件。

    封装了 QWebEngineView + WebAppRunner 的完整生命周期：
      - 自动启动后端 → 探活 → 加载网页。
      - 控件销毁／调用 shutdown() 时自动杀死后端进程。

    用法::

        host = WebViewHost()
        host.server_loaded.connect(lambda url: print(f"已加载: {url}"))
        host.load_web_app("path/to/server.py")

        # 放入布局或 Tab
        layout.addWidget(host)

        # 关闭时杀死后端
        host.shutdown()
    """

    server_loaded = Signal(str)
    """网页加载完成信号。携带 URL。"""

    load_failed = Signal(str)
    """加载失败信号。携带错误描述。"""

    closed = Signal()
    """控件关闭／停止信号。"""

    _LOADING_HTML = """
    <!DOCTYPE html>
    <html><head><meta charset="utf-8"><style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            display: flex; flex-direction: column;
            align-items: center; justify-content: center;
            height: 100vh; background: #1e1e1e;
            font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
        }
        .spinner {
            width: 40px; height: 40px;
            border: 3px solid rgba(255,255,255,0.2);
            border-top-color: #007acc;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .msg { color: #aaa; margin-top: 18px; font-size: 14px; }
        .port { color: #4ec9f0; font-weight: bold; }
    </style></head><body>
        <div class="spinner"></div>
        <div class="msg">正在启动后端服务（端口 <span class="port">{port}</span>）...</div>
    </body></html>"""

    _ERROR_HTML = """
    <!DOCTYPE html>
    <html><head><meta charset="utf-8"><style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            display: flex; flex-direction: column;
            align-items: center; justify-content: center;
            height: 100vh; background: #1e1e1e;
            font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
        }
        .icon { font-size: 48px; margin-bottom: 16px; }
        .msg { color: #e74c3c; font-size: 15px; text-align: center; max-width: 400px; }
    </style></head><body>
        <div class="icon">⚠️</div>
        <div class="msg">{message}</div>
    </body></html>"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # WebAppRunner —— 管理后端进程
        self._runner: Optional[WebAppRunner] = None

        # 当前加载的 URL
        self._current_url: str = ""

        # QWebEngineView（延迟创建，确保 QApplication 已存在）
        self._web_view: Optional["QWebEngineView"] = None

        self._init_ui()

    def _init_ui(self) -> None:
        """构建控件 UI 骨架。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 工具栏 ──
        toolbar = QFrame()
        toolbar.setStyleSheet(
            "QFrame { background: #252526; border-bottom: 1px solid #333; }"
        )
        toolbar.setFixedHeight(36)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 4, 8, 4)

        self._url_label = QLabel("🌐  未加载")
        self._url_label.setStyleSheet("color: #aaa; font-size: 12px;")
        toolbar_layout.addWidget(self._url_label)

        toolbar_layout.addStretch()

        self._btn_close_tab = QPushButton("✕  关闭")
        self._btn_close_tab.setFixedHeight(24)
        self._btn_close_tab.setStyleSheet("""
            QPushButton {
                background: transparent; color: #ccc; border: 1px solid #555;
                border-radius: 3px; padding: 2px 10px; font-size: 11px;
            }
            QPushButton:hover { background: #c0392b; color: white; border-color: #c0392b; }
        """)
        self._btn_close_tab.clicked.connect(self.shutdown)
        toolbar_layout.addWidget(self._btn_close_tab)

        layout.addWidget(toolbar)

        # ── QWebEngineView 占位 —— 延迟到首次使用时初始化 ──
        self._web_container = QWidget()
        self._web_container.setStyleSheet("background: #1e1e1e;")
        self._web_container_layout = QVBoxLayout(self._web_container)
        self._web_container_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._web_container, stretch=1)

    # ── 公开方法 ─────────────────────────────────────────────

    def load_web_app(
        self,
        script_path: str,
        port: Optional[int] = None,
        extra_args: Optional[list[str]] = None,
    ) -> None:
        """
        启动后端并加载网页。

        Args:
            script_path: 后端 Python 脚本路径。
            port:        指定端口（None = 自动分配）。
            extra_args:  额外 CLI 参数。
        """
        if self._runner is not None and self._runner.is_running():
            logger.warning("已有 Web 应用在运行中，先停止旧的。")
            self.shutdown()

        # 创建 runner
        self._runner = WebAppRunner()
        self._runner.log_received.connect(self._on_runner_log)
        self._runner.server_ready.connect(self._on_server_ready)
        self._runner.server_error.connect(self._on_server_error)
        self._runner.server_finished.connect(self._on_server_finished)
        self._runner.state_changed.connect(self._on_state_changed)

        # 显示加载页
        allocated_port = port or 0  # 0 表示自动分配，runner 内部会处理
        self._show_loading(allocated_port)

        # 启动
        self._runner.start(
            script_path=script_path,
            port=port,
            extra_args=extra_args,
        )

    def shutdown(self) -> None:
        """关闭 Web 视图，停止后端进程。"""
        if self._runner is not None:
            self._runner.stop()
            self._runner.deleteLater()
            self._runner = None

        if self._web_view is not None:
            self._web_view.setHtml("")
            self._web_view.deleteLater()
            self._web_view = None

        self._current_url = ""
        self._url_label.setText("🌐  未加载")
        self.closed.emit()

    @property
    def current_url(self) -> str:
        return self._current_url

    # ── 内部槽函数 ───────────────────────────────────────────

    def _on_server_ready(self, port: int) -> None:
        """后端就绪 → 用 QWebEngineView 加载 URL。"""
        url = f"http://127.0.0.1:{port}"
        self._current_url = url
        logger.info("加载 Web 页面: %s", url)

        self._ensure_web_view()
        if self._web_view is not None:
            self._web_view.load(QUrl(url))

    def _on_server_error(self, message: str) -> None:
        """后端启动失败 → 显示错误页。"""
        self._ensure_web_view()
        if self._web_view is not None:
            error_html = self._ERROR_HTML.format(message=message)
            self._web_view.setHtml(error_html)
        self.load_failed.emit(message)

    def _on_runner_log(self, text: str) -> None:
        """转发 runner 日志（供外部连接 UI 日志窗口）。"""
        pass  # 由外部通过 runner.log_received 自行连接日志窗

    def _on_server_finished(self, exit_code: int, exit_status: int) -> None:
        logger.info("Web 后端已退出 (code=%d)", exit_code)

    def _on_state_changed(self, state: WebAppState) -> None:
        logger.debug("WebApp 状态: %s", state.name)

    def _ensure_web_view(self) -> None:
        """延迟创建 QWebEngineView（确保 QApplication 已初始化）。"""
        if self._web_view is not None:
            return

        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            from PySide6.QtWebEngineCore import QWebEngineSettings

            self._web_view = QWebEngineView()
            self._web_view.setStyleSheet("background: white;")

            # 启用本地内容访问
            settings = self._web_view.settings()
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
                True,
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
                True,
            )

            # 监听页面加载完成
            self._web_view.loadFinished.connect(self._on_page_loaded)

            self._web_container_layout.addWidget(self._web_view)

        except ImportError as exc:
            error_msg = (
                "PySide6-WebEngine 未安装。\n\n"
                "请执行: pip install PySide6-WebEngine\n\n"
                f"原始错误: {exc}"
            )
            logger.error(error_msg)
            error_label = QLabel(error_msg)
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            error_label.setStyleSheet(
                "color: #e74c3c; font-size: 14px; padding: 40px;"
            )
            error_label.setWordWrap(True)
            self._web_container_layout.addWidget(error_label)

    def _on_page_loaded(self, success: bool) -> None:
        """QWebEngineView 页面加载完成回调。"""
        if success:
            url = self._current_url
            self._url_label.setText(f"🌐  {url}")
            self._url_label.setStyleSheet("color: #4ec9f0; font-size: 12px;")
            self.server_loaded.emit(url)
        else:
            # 页面加载失败但不一定是后端问题（可能是前端 404 等）
            logger.warning("页面加载完成但 reported success=false: %s", self._current_url)

    def _show_loading(self, port: int) -> None:
        """在 WebView 中显示加载等待页。"""
        self._ensure_web_view()
        if self._web_view is not None:
            self._web_view.setHtml(
                self._LOADING_HTML.format(port=port or "自动分配")
            )
            self._url_label.setText(f"⏳  等待后端就绪...")
            self._url_label.setStyleSheet("color: #ffd93d; font-size: 12px;")


# ═══════════════════════════════════════════════════════════════
#  演示主窗口
# ═══════════════════════════════════════════════════════════════

class DemoWindow(QMainWindow):
    """完整的 Web 视图加载演示窗口。"""

    _TITLE = "PyBox — Web 视图演示"
    _DEFAULT_SIZE = (1100, 750)

    def __init__(self) -> None:
        super().__init__()

        self._web_host: Optional[WebViewHost] = None

        self._init_ui()

    def _init_ui(self) -> None:
        self.setWindowTitle(self._TITLE)
        self.resize(*self._DEFAULT_SIZE)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)
        root.setContentsMargins(10, 10, 10, 10)

        # ── 配置区 ──
        config = self._build_config()
        root.addWidget(config)

        # ── 控制栏 ──
        ctrl = self._build_controls()
        root.addLayout(ctrl)

        # ── 上下分栏：日志 + Web 视图 ──
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        # 日志区
        log_group = QGroupBox("后端日志输出")
        log_layout = QVBoxLayout(log_group)
        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setFont(QFont("Consolas", 10))
        self._log_view.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e; color: #b0ffb0;
                border: 1px solid #333; border-radius: 4px; padding: 6px;
            }
        """)
        self._log_view.textChanged.connect(self._scroll_log)
        log_layout.addWidget(self._log_view)
        splitter.addWidget(log_group)

        # Web 视图宿主
        self._web_host = WebViewHost()
        self._web_host.server_loaded.connect(self._on_web_loaded)
        self._web_host.load_failed.connect(self._on_web_failed)
        self._web_host.closed.connect(self._on_web_closed)
        splitter.addWidget(self._web_host)

        splitter.setSizes([180, 500])
        root.addWidget(splitter, stretch=1)

    def _build_config(self) -> QGroupBox:
        group = QGroupBox("Web 应用配置")
        layout = QVBoxLayout(group)
        layout.setSpacing(6)

        # 脚本路径
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("后端脚本:"))
        self._script_edit = QLineEdit()
        self._script_edit.setPlaceholderText("选择 Python 后端脚本（如 sample_server.py）...")
        self._script_edit.setClearButtonEnabled(True)
        path_row.addWidget(self._script_edit, stretch=1)

        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._on_browse)
        path_row.addWidget(browse_btn)
        layout.addLayout(path_row)

        # 端口行
        port_row = QHBoxLayout()
        port_row.addWidget(QLabel("端口号:"))
        self._port_edit = QLineEdit()
        self._port_edit.setPlaceholderText("留空 = 自动分配空闲端口")
        self._port_edit.setMaximumWidth(120)
        self._port_edit.setClearButtonEnabled(True)
        port_row.addWidget(self._port_edit)
        port_row.addStretch()
        layout.addLayout(port_row)

        return group

    def _build_controls(self) -> QHBoxLayout:
        bar = QHBoxLayout()

        self._btn_run = QPushButton("▶  启动并加载")
        self._btn_run.setFixedHeight(34)
        self._btn_run.setStyleSheet("""
            QPushButton {
                background-color: #007acc; color: white; border: none;
                border-radius: 4px; padding: 6px 24px; font-weight: bold;
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
                background-color: #c0392b; color: white; border: none;
                border-radius: 4px; padding: 6px 24px; font-weight: bold;
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

    # ── 槽 ───────────────────────────────────────────────────

    def _on_browse(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择 Python 后端脚本", os.getcwd(),
            "Python 脚本 (*.py);;所有文件 (*.*)",
        )
        if file_path:
            self._script_edit.setText(file_path)

    def _on_run(self) -> None:
        script = self._script_edit.text().strip()
        if not script:
            QMessageBox.warning(self, "提示", "请先选择后端脚本路径。")
            return

        port_text = self._port_edit.text().strip()
        port = None
        if port_text:
            try:
                port = int(port_text)
            except ValueError:
                QMessageBox.warning(self, "提示", "端口号必须是整数。")
                return
            if not is_port_free(port):
                QMessageBox.warning(
                    self, "端口占用",
                    f"端口 {port} 已被占用，请更换或留空自动分配。",
                )

        self._log_view.clear()
        self._append_log("[INFO]", f"启动 Web 应用: {script}", "#4ec9f0")

        # 启动
        self._web_host.load_web_app(script, port=port)

        # 连接 runner 日志
        runner = self._web_host._runner
        if runner is not None:
            runner.log_received.connect(self._on_log_line)
            runner.state_changed.connect(self._on_runner_state)

        self._update_controls(False)

    def _on_stop(self) -> None:
        self._append_log("[INFO]", "用户请求停止 Web 应用...", "#ffd93d")
        self._web_host.shutdown()

    def _on_log_line(self, text: str) -> None:
        color = "#b0ffb0"
        if text.startswith("[STDERR]"):
            color = "#ff6b6b"
        elif "[ERROR]" in text:
            color = "#e74c3c"
        self._append_log("", text, color)

    def _on_web_loaded(self, url: str) -> None:
        self._append_log("[INFO]", f"✅ 网页已加载: {url}", "#2ecc71")
        self._update_controls(False)

    def _on_web_failed(self, message: str) -> None:
        self._append_log("[ERROR]", f"❌ 加载失败: {message}", "#e74c3c")
        self._update_controls(True)

    def _on_web_closed(self) -> None:
        self._update_controls(True)

    def _on_runner_state(self, state: WebAppState) -> None:
        state_map = {
            WebAppState.IDLE:           ("空闲",   "#888"),
            WebAppState.PORT_SEARCHING: ("分配端口", "#ffd93d"),
            WebAppState.STARTING:       ("启动中", "#ffd93d"),
            WebAppState.POLLING:        ("探活中", "#ffd93d"),
            WebAppState.READY:          ("已就绪", "#2ecc71"),
            WebAppState.STOPPING:       ("停止中", "#e74c3c"),
            WebAppState.ERROR:          ("错误",   "#e74c3c"),
            WebAppState.EXITED:         ("已退出", "#4ec9f0"),
        }
        text, color = state_map.get(state, (state.name, "#888"))
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"font-weight: bold; color: {color}; padding: 2px 8px;"
        )

        if state == WebAppState.EXITED:
            self._update_controls(True)

    def _update_controls(self, idle: bool) -> None:
        self._btn_run.setEnabled(idle)
        self._btn_stop.setEnabled(not idle)
        self._script_edit.setEnabled(idle)
        self._port_edit.setEnabled(idle)
        if idle and self._status_label.text() not in ("错误", "已退出"):
            self._status_label.setText("空闲")
            self._status_label.setStyleSheet(
                "font-weight: bold; color: #888; padding: 2px 8px;"
            )

    def _append_log(self, tag: str, message: str, color: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        if tag:
            line = (
                f'<span style="color:#888;">{timestamp}</span> '
                f'<span style="color:{color};font-weight:bold;">{tag}</span> '
                f'<span style="color:{color};">{message}</span>'
            )
        else:
            line = (
                f'<span style="color:#888;">{timestamp}</span> '
                f'<span style="color:{color};">{message}</span>'
            )
        self._log_view.append(line)

    def _scroll_log(self) -> None:
        cursor = self._log_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._log_view.setTextCursor(cursor)

    def closeEvent(self, event) -> None:
        """窗口关闭 → 自动停止后端，释放端口。"""
        if self._web_host is not None:
            self._web_host.shutdown()
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

    # QtWebEngine 需在 QApplication 之前初始化部分上下文
    # 导入即完成初始化
    try:
        import PySide6.QtWebEngineWidgets  # noqa: F401
    except ImportError:
        logger.warning(
            "PySide6-WebEngine 未安装，WebView 将不可用。"
            "请执行: pip install PySide6-WebEngine"
        )

    app = QApplication(sys.argv)
    app.setApplicationName("PyBox-WebDemo")

    window = DemoWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
