"""Persistent, serialized MCP client for the local SolidWorks automation server."""
from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
from datetime import timedelta
import os
from pathlib import Path
import sys
import threading
from typing import Any

DEFAULT_REPOSITORY = Path(__file__).resolve().parents[1] / "vendor" / "solidworks-automation-skill"


class McpBridgeError(RuntimeError):
    """The MCP connection or an MCP request failed."""


class McpBridge:
    """Expose blocking methods while one dedicated thread owns the MCP session.

    The stdio and ClientSession context managers are entered and exited in the
    same asyncio task. Every CAD request is consumed by that task serially.
    Creating a bridge does not connect to or start SolidWorks.
    """

    def __init__(
        self,
        repository: str | Path = DEFAULT_REPOSITORY,
        python_executable: str | Path | None = None,
        timeout: float = 180,
        connect_timeout: float = 35,
        output_root: str | Path | None = None,
    ) -> None:
        self.repository = Path(repository).expanduser().resolve()
        bundled_python = self.repository / ".venv" / "Scripts" / "python.exe"
        self.python_executable = str(
            python_executable or (bundled_python if bundled_python.is_file() else sys.executable)
        )
        self.timeout = float(timeout)
        self.connect_timeout = float(connect_timeout)
        self.output_root = Path(output_root).resolve() if output_root else None
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._closed = False
        self._startup_error: BaseException | None = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue | None = None
        self._pending: set[concurrent.futures.Future] = set()

    def _ensure_started(self) -> None:
        with self._lock:
            if self._closed:
                raise McpBridgeError("MCP 连接已关闭。")
            if self._thread is None:
                server = self.repository / "mcp-server" / "server.py"
                if not server.is_file():
                    raise McpBridgeError(f"没有找到上游 MCP 服务：{server}")
                self._thread = threading.Thread(
                    target=self._thread_main, name="robomaster-mcp", daemon=True
                )
                self._thread.start()
        if not self._ready.wait(self.connect_timeout):
            raise McpBridgeError("MCP 初始化超时；请检查上游 Python 环境和服务依赖。")
        if self._startup_error is not None:
            raise McpBridgeError(
                "MCP 服务连接失败：" + self._error_text(self._startup_error)
            ) from self._startup_error
        if self._thread is None or not self._thread.is_alive():
            raise McpBridgeError("MCP 服务已经退出，请重新创建连接。")

    @staticmethod
    def _error_text(error: BaseException) -> str:
        exceptions = getattr(error, "exceptions", None)
        if exceptions:
            return "; ".join(McpBridge._error_text(item) for item in exceptions)[:800]
        return (str(error) or type(error).__name__)[:800]

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._serve())
        except BaseException as error:
            self._startup_error = error
        finally:
            self._ready.set()
            with self._lock:
                pending = tuple(self._pending)
            for future in pending:
                if not future.done():
                    future.set_exception(
                        McpBridgeError(
                            "MCP 服务已经退出："
                            + (
                                self._error_text(self._startup_error)
                                if self._startup_error else "连接已关闭"
                            )
                        )
                    )

    async def _serve(self) -> None:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as error:
            raise McpBridgeError(
                "当前后端 Python 缺少 mcp；请使用上游 .venv 或安装项目依赖。"
            ) from error

        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        environment = os.environ.copy()
        environment.update(PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        if self.output_root:
            environment["SW_MCP_OUTPUT_ROOT"] = str(self.output_root)
            environment["SW_MCP_QUEUE_DIR"] = str(self.output_root.parent / "mcp_queue")
        parameters: dict[str, Any] = {
            "command": self.python_executable,
            "args": [str(self.repository / "mcp-server" / "server.py")],
            "cwd": str(self.repository),
            "env": environment,
        }
        # MCP releases differ: only supply Windows flags if explicitly supported.
        fields = getattr(StdioServerParameters, "model_fields", {})
        if os.name == "nt" and "creationflags" in fields:
            import subprocess
            parameters["creationflags"] = subprocess.CREATE_NO_WINDOW
        params = StdioServerParameters(**parameters)
        with open(os.devnull, "w", encoding="utf-8") as error_log:
            async with stdio_client(params, errlog=error_log) as streams:
                async with ClientSession(
                    streams[0], streams[1],
                    read_timeout_seconds=timedelta(seconds=self.timeout),
                ) as session:
                    await asyncio.wait_for(session.initialize(), self.connect_timeout)
                    self._ready.set()
                    while True:
                        request = await self._queue.get()
                        if request is None:
                            return
                        operation, payload, future = request
                        if future.cancelled():
                            continue
                        try:
                            if operation == "list":
                                tools: list[dict[str, Any]] = []
                                cursor = None
                                while True:
                                    result = await session.list_tools(cursor=cursor)
                                    for tool in result.tools:
                                        item = tool.model_dump(mode="json", by_alias=True)
                                        tools.append({
                                            "name": item["name"],
                                            "description": item.get("description") or "",
                                            "inputSchema": item.get("inputSchema") or {},
                                        })
                                    cursor = getattr(result, "nextCursor", None)
                                    if not cursor:
                                        break
                                value = tools
                            else:
                                result = await session.call_tool(
                                    payload[0], payload[1],
                                    read_timeout_seconds=timedelta(seconds=self.timeout),
                                )
                                value = result.model_dump(
                                    mode="json", by_alias=True, exclude_none=True
                                )
                            if not future.done():
                                future.set_result(value)
                        except Exception as error:
                            if not future.done():
                                future.set_exception(
                                    McpBridgeError("MCP 请求失败：" + self._error_text(error))
                                )
                        finally:
                            with self._lock:
                                self._pending.discard(future)

    def _submit(self, operation: str, payload: Any = None) -> Any:
        self._ensure_started()
        future: concurrent.futures.Future = concurrent.futures.Future()
        with self._lock:
            if self._closed or self._loop is None or self._queue is None:
                raise McpBridgeError("MCP 连接已关闭。")
            self._pending.add(future)
            try:
                self._loop.call_soon_threadsafe(
                    self._queue.put_nowait, (operation, payload, future)
                )
            except RuntimeError as error:
                self._pending.discard(future)
                raise McpBridgeError("MCP 事件循环已退出。") from error
        try:
            return future.result(timeout=self.timeout + self.connect_timeout)
        except concurrent.futures.TimeoutError as error:
            # An in-flight CAD operation must not be repeated automatically.
            raise McpBridgeError(
                "MCP 请求等待超时；操作可能仍在执行，请先检查当前 CAD 状态再决定重试。"
            ) from error

    def list_tools(self) -> list[dict[str, Any]]:
        return self._submit("list")

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        if not isinstance(name, str) or not name:
            raise ValueError("MCP 工具名不能为空。")
        if arguments is not None and not isinstance(arguments, dict):
            raise TypeError("MCP 工具参数必须是 JSON 对象。")
        return self._submit("call", (name, arguments or {}))

    def close(self) -> None:
        """Finish an in-flight request and close the owned session safely."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            loop, queue, thread = self._loop, self._queue, self._thread
            if loop is not None and queue is not None:
                with contextlib.suppress(RuntimeError):
                    loop.call_soon_threadsafe(queue.put_nowait, None)
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5)

    def __enter__(self) -> "McpBridge":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
