#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyBox 容器平台 —— 主入口模块

职责：
  1. 启动时检测内置 Python 运行时（./runtime/python.exe）是否存在。
  2. 若存在，将全局环境变量指向内置环境，实现子进程级别的绝对隔离。
  3. 若不存在，输出错误日志并弹出告警窗口。
  4. 初始化主窗口（标题："PyBox 容器平台"）。
"""

import os
import sys
import locale
import logging
from pathlib import Path

# ── 日志配置 ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("PyBox")


# ── 路径工具 ────────────────────────────────────────────────
def get_application_root() -> Path:
    """获取主程序所在目录（兼容 PyInstaller 打包后的路径）。"""
    if getattr(sys, "frozen", False):
        # 打包后的 exe 路径
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_ROOT: Path = get_application_root()
RUNTIME_DIR: Path = APP_ROOT / "runtime"
RUNTIME_EXE: Path = RUNTIME_DIR / "python.exe"


# ══════════════════════════════════════════════════════════════
#  环境检测与隔离
# ══════════════════════════════════════════════════════════════

def check_runtime() -> bool:
    """检测 ./runtime/python.exe 是否存在。"""
    exists = RUNTIME_EXE.is_file()
    logger.info("运行时检测: %s → %s", RUNTIME_EXE, "存在" if exists else "不存在")
    return exists


def configure_environment() -> None:
    """
    将全局环境变量指向内置 Python 运行时，确保子进程绝对隔离。

    核心策略：
      1. 将 ./runtime 及其 Scripts 子目录前置到 PATH 首部。
      2. 设置 PYTHONHOME，使 Python 完全使用内置标准库。
      3. 配置 PYTHONPATH 指向内置 site-packages。
      4. 新增 PYBOX_RUNTIME 标记变量，供子进程识别自身运行环境。
    """
    runtime_str = str(RUNTIME_DIR.resolve())
    scripts_dir = os.path.join(runtime_str, "Scripts")

    # ── PATH：内置运行时优先 ──
    current_path = os.environ.get("PATH", "")
    # 移除可能已存在的重复条目，避免 PATH 无限增长
    path_entries = [
        entry for entry in current_path.split(os.pathsep)
        if entry and RUNTIME_DIR.name not in entry
    ]
    new_path = os.pathsep.join([runtime_str, scripts_dir] + path_entries)
    os.environ["PATH"] = new_path

    # ── PYTHONHOME：强制 Python 使用内置标准库 ──
    os.environ["PYTHONHOME"] = runtime_str

    # ── PYTHONPATH：指向内置 site-packages ──
    site_packages = os.path.join(runtime_str, "Lib", "site-packages")
    os.environ["PYTHONPATH"] = site_packages

    # ── 平台标记：供子进程判断是否运行在 PyBox 容器内 ──
    os.environ["PYBOX_RUNTIME"] = runtime_str
    os.environ["PYBOX_ROOT"] = str(APP_ROOT.resolve())

    logger.info("环境变量已重定向至内置运行时:")
    logger.info("  PATH        → %s;%s;...", runtime_str, scripts_dir)
    logger.info("  PYTHONHOME  → %s", runtime_str)
    logger.info("  PYTHONPATH  → %s", site_packages)


# ══════════════════════════════════════════════════════════════
#  错误提示
# ══════════════════════════════════════════════════════════════

def show_error_dialog(message: str, title: str = "PyBox 启动失败") -> None:
    """
    弹出 PySide6 错误提示窗口。

    若 PySide6 不可用（极端情况），退化为纯控制台输出并尝试系统弹窗。
    """
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        # 确保存在 QApplication 实例（可能尚未创建）
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()
    except ImportError:
        # 连 PySide6 都没有时，仅能依赖控制台输出
        logger.critical("PySide6 不可用，无法弹出错误窗口: %s", message)
        # 尝试调用 Windows 原生弹窗作为最后手段
        _fallback_alert(title, message)
    except Exception as exc:
        logger.critical("弹出错误窗口时发生异常: %s", exc)
        _fallback_alert(title, message)


def _fallback_alert(title: str, message: str) -> None:
    """Windows 原生 MessageBox 兜底弹窗（需要 ctypes）。"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)  # MB_ICONERROR
    except Exception:
        # 静默失败 —— 控制台已输出日志
        pass


# ══════════════════════════════════════════════════════════════
#  主窗口
# ══════════════════════════════════════════════════════════════

def create_main_window() -> "WorkbenchWindow":
    """工厂函数：初始化数据库并创建工作台主窗口。"""
    # 确保项目根在 sys.path 中，以便子模块可正常导入
    project_root = str(APP_ROOT)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from core.db_manager import init_db, reset_all_status
    from ui.workbench import WorkbenchWindow

    # 初始化数据库（幂等）
    init_db()
    # 清理上次残留的"运行中"状态
    reset_all_status()

    window = WorkbenchWindow()
    logger.info("工作台主窗口初始化完成。")
    return window


# ══════════════════════════════════════════════════════════════
#  应用程序入口
# ══════════════════════════════════════════════════════════════

def _init_qt_app() -> "QApplication":
    """初始化 QApplication 实例（高 DPI 适配 + 平台插件路径）。"""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt

    # Windows 高 DPI 适配
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)  # type: ignore[attr-defined]
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)  # type: ignore[attr-defined]

    # 若内置运行时包含 Qt 平台插件，提前注入路径
    plugins_dir = RUNTIME_DIR / "plugins"
    if plugins_dir.is_dir():
        QApplication.addLibraryPath(str(plugins_dir.resolve()))

    app = QApplication(sys.argv)
    app.setApplicationName("PyBox")
    app.setApplicationDisplayName("PyBox 容器平台")
    return app


def main() -> int:
    """
    PyBox 主入口流程。

    Returns:
        int: 进程退出码。0 表示正常退出，非 0 表示异常。
    """
    logger.info("=" * 50)
    logger.info("PyBox 容器平台 启动中...")
    logger.info("应用程序根目录: %s", APP_ROOT)

    # ── 步骤 1：环境检测 ──
    if not check_runtime():
        error_msg = (
            f"内置 Python 运行时未找到！\n\n"
            f"预期路径：{RUNTIME_EXE}\n\n"
            f"请确保在程序根目录下放置了完整的 ./runtime/ 文件夹，\n"
            f"其中包含 python.exe 及相关标准库。\n\n"
            f"程序将退出。"
        )
        logger.critical(error_msg.replace("\n", " "))
        show_error_dialog(error_msg)
        return 1

    # ── 步骤 2：隔离环境配置 ──
    try:
        configure_environment()
    except Exception as exc:
        logger.critical("环境配置失败: %s", exc, exc_info=True)
        show_error_dialog(f"环境变量配置失败：\n{exc}")
        return 2

    # ── 步骤 3：初始化 Qt 应用 ──
    try:
        qt_app = _init_qt_app()
    except Exception as exc:
        logger.critical("Qt 应用初始化失败: %s", exc, exc_info=True)
        show_error_dialog(f"Qt 应用初始化失败：\n{exc}")
        return 3

    # ── 步骤 4：创建并展示工作台主窗口 ──
    try:
        workbench = create_main_window()
        workbench.show()
    except Exception as exc:
        logger.critical("主窗口运行异常: %s", exc, exc_info=True)
        show_error_dialog(f"主窗口运行时发生异常：\n{exc}")
        return 4

    logger.info("进入 Qt 事件循环。")
    exit_code = qt_app.exec()
    logger.info("PyBox 容器平台 已正常退出。")
    return exit_code


if __name__ == "__main__":
    # Windows 控制台编码兼容：确保中文日志不乱码
    if sys.platform == "win32":
        try:
            locale.setlocale(locale.LC_ALL, "zh_CN.UTF-8")
        except locale.Error:
            pass  # 若系统不支持，使用默认编码

    sys.exit(main())
