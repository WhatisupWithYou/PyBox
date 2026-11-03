#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyBox 工作台启动器。

直接运行本文件即可启动完整的工作台 UI。
"""

import sys
import logging
from pathlib import Path

# 确保项目根在 sys.path 最前
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from core.db_manager import init_db, reset_all_status
from ui.workbench import WorkbenchWindow


def main() -> int:
    # 日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 初始化数据库（幂等）
    init_db()
    # 启动时清理上次可能残留的"运行中"状态
    reset_all_status()

    # Qt 高 DPI
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("PyBox")
    app.setApplicationDisplayName("PyBox 容器平台")

    window = WorkbenchWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
