"""后台工作线程封装.

设计要点（避坑）：
1. **Worker 强引用**：QThread.moveToThread 不创建父子关系，必须把 worker 挂到
   thread 的 Python 属性上，否则 Python GC 会先回收 worker，QThread 调不到 run().
2. **跨线程信号路由**：worker 的 Signal connect 到 *任意 Python callable* +
   Qt.QueuedConnection 时，PySide6 对 callable 的线程亲和度判定不可靠，回调可能
   在 worker 线程执行。解决：统一通过 AsyncRunner（QObject 实例，归属于 parent
   所在线程，即 GUI 线程）做 Signal→Signal 中转。
   - worker.signal → AsyncRunner.signal（跨线程，自动 queued）
   - AsyncRunner.signal → 最终 callable（同线程，直连，callable 必然在 GUI 线程跑）
"""
from __future__ import annotations
import inspect
from typing import Any, Callable

from PySide6.QtCore import QObject, Qt, QThread, Signal


class _Worker(QObject):
    """后台线程里跑的对象."""

    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, fn: Callable[..., Any], *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            try:
                sig = inspect.signature(self._fn)
                if "progress" in sig.parameters and "progress" not in self._kwargs:
                    self._kwargs["progress"] = self.progress.emit
            except (TypeError, ValueError):
                pass
            result = self._fn(*self._args, **self._kwargs)
            self.finished.emit(result)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class AsyncRunner(QObject):
    """中转 QObject — 把 worker 信号 *安全地* 投递到 GUI 线程的 callable.

    关键：AsyncRunner 创建在 GUI 线程（继承 parent 的 thread affinity），它的
    Signal 在 GUI 线程被 emit，因此连到这些 Signal 的 callable 一定在 GUI 线程跑.
    """

    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self._thread: QThread | None = None

    def start(self, fn: Callable[..., Any], *args,
              on_success: Callable[[Any], None] | None = None,
              on_error: Callable[[str], None] | None = None,
              on_progress: Callable[[str], None] | None = None,
              **kwargs) -> QThread:
        if on_success is not None:
            self.finished.connect(on_success)
        if on_error is not None:
            self.failed.connect(on_error)
        if on_progress is not None:
            self.progress.connect(on_progress)

        thread = QThread(self)
        worker = _Worker(fn, *args, **kwargs)
        worker.moveToThread(thread)
        thread._cb_worker = worker  # type: ignore[attr-defined] — 防 GC

        thread.started.connect(worker.run)
        # Signal → Signal：跨线程 Qt 自动 queued 到 self（GUI 线程）
        worker.finished.connect(self.finished)
        worker.failed.connect(self.failed)
        worker.progress.connect(self.progress)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self.deleteLater)

        thread.start()
        self._thread = thread
        return thread


def run_async(parent: QObject, fn: Callable[..., Any],
              on_success: Callable[[Any], None],
              on_error: Callable[[str], None],
              *args,
              on_progress: Callable[[str], None] | None = None,
              **kwargs) -> QThread:
    """跑后台任务 — 所有回调保证在 GUI 线程执行.

    parent: 必须是 GUI 线程上的 QObject（用于 AsyncRunner 的线程亲和度）.
    """
    runner = AsyncRunner(parent)
    return runner.start(fn, *args,
                        on_success=on_success,
                        on_error=on_error,
                        on_progress=on_progress,
                        **kwargs)
