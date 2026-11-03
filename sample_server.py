#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
示例 Web 后端 —— 用于测试 PyBox 容器平台的 Web 应用加载功能。

使用方式:
    python sample_server.py --port 8080

启动后在 http://127.0.0.1:8080 提供一个简单的 Web 页面，
输出 HTML 内容并在控制台打印访问日志。
纯标准库实现，无第三方依赖。
"""

import argparse
import json
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime


# ═══════════════════════════════════════════════════════════════
#  HTTP 请求处理器
# ═══════════════════════════════════════════════════════════════

_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PyBox 示例应用</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            display: flex; align-items: center; justify-content: center;
            color: #e0e0e0;
        }
        .card {
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px;
            padding: 48px 40px;
            text-align: center;
            backdrop-filter: blur(12px);
            max-width: 520px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.4);
        }
        .card .icon { font-size: 56px; margin-bottom: 16px; }
        .card h1 { font-size: 26px; font-weight: 600; margin-bottom: 10px; color: #fff; }
        .card .ver { font-size: 13px; color: #7ec8e3; margin-bottom: 20px; }
        .card .info { font-size: 14px; color: #aaa; line-height: 1.8; }
        .card .info span { color: #ffd93d; font-weight: bold; }
        .card .time { font-size: 12px; color: #666; margin-top: 24px; }
        button {
            margin-top: 20px; padding: 10px 28px;
            background: #007acc; color: white; border: none;
            border-radius: 6px; font-size: 14px; cursor: pointer;
        }
        button:hover { background: #1a8cde; }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">📦</div>
        <h1>PyBox 容器平台</h1>
        <div class="ver">示例 Web 应用 v1.0</div>
        <div class="info">
            后端端口: <span>{port}</span><br>
            服务端时间: <span>{time}</span><br>
            请求计数: <span>{count}</span>
        </div>
        <div class="time">Powered by Python http.server</div>
        <button onclick="location.reload()">🔄 刷新</button>
    </div>
</body>
</html>"""


class SampleHandler(BaseHTTPRequestHandler):
    """处理 HTTP 请求，返回动态 HTML 页面。"""

    request_count = 0

    def do_GET(self) -> None:
        """处理 GET 请求。"""
        SampleHandler.request_count += 1

        # API 端点：返回 JSON 状态
        if self.path == "/api/status":
            self._send_json({
                "status": "running",
                "port": self.server.server_port,
                "uptime": round(time.time() - self.server.start_time, 1),
                "requests": SampleHandler.request_count,
            })
            return

        # API 端点：健康检查
        if self.path == "/api/health":
            self._send_json({"healthy": True})
            return

        # 默认：返回 HTML 页面
        html = _TEMPLATE.format(
            port=self.server.server_port,
            time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            count=SampleHandler.request_count,
        )
        self._send_html(html)

    def do_POST(self) -> None:
        """处理 POST 请求 —— 模拟 RPA 接收指令。"""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b"{}"
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {}

        print(f"[API] POST {self.path} | payload={data}", flush=True)
        self._send_json({"received": True, "action": data.get("action", "none")})

    def log_message(self, format, *args) -> None:
        """重写日志方法，输出到 stdout 供 PyBox 平台捕获。"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(
            f"[{timestamp}] {self.client_address[0]} - {format % args}",
            flush=True,
        )

    def _send_html(self, content: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


# ═══════════════════════════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(description="PyBox 示例 Web 后端")
    parser.add_argument(
        "--port", type=int, default=8000,
        help="监听端口（默认 8000）",
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1",
        help="监听地址（默认 127.0.0.1）",
    )
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), SampleHandler)
    server.start_time = time.time()  # type: ignore[attr-defined]

    print(f"[PyBox-Sample] 服务启动于 http://{args.host}:{args.port}", flush=True)
    print(f"[PyBox-Sample] 按 Ctrl+C 停止服务", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[PyBox-Sample] 服务已停止。", flush=True)
        server.server_close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
