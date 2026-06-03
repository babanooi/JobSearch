"""异步任务管理器 —— ThreadPoolExecutor 限并发，支持取消检查"""
import uuid
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable
from core.logger import get_logger

logger = get_logger(__name__)

MAX_WORKERS = 4  # 最大并发任务数


class TaskCancelledError(Exception):
    """任务被用户取消时抛出，用于终止执行链"""
    pass


class Task:
    """单个任务"""
    def __init__(self, task_id: str, task_type: str):
        self.task_id = task_id
        self.task_type = task_type
        self.status = "pending"      # pending | running | done | failed | cancelled
        self.progress = ""           # 当前阶段描述
        self.result = None           # 完成后的结果
        self.error = None            # 失败信息
        self.created_at = time.time()
        self.finished_at = None
        self._cancel = threading.Event()

    def is_cancelled(self) -> bool:
        """检查任务是否已取消（供执行函数周期性调用）"""
        return self._cancel.is_set()

    def check_cancelled(self):
        """如果已取消则抛出异常，用于中断执行链"""
        if self._cancel.is_set():
            raise TaskCancelledError(f"任务 {self.task_id} 已取消")

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "type": self.task_type,
            "status": self.status,
            "progress": self.progress,
            "finished": self.status in ("done", "failed", "cancelled"),
            **({"result": self.result} if self.result else {}),
            **({"error": self.error} if self.error else {}),
        }


class TaskManager:
    """内存任务队列，ThreadPoolExecutor 限并发，最多保留 100 个已完成任务"""

    def __init__(self, max_finished: int = 100, max_workers: int = MAX_WORKERS):
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()
        self._max_finished = max_finished
        self._pool = ThreadPoolExecutor(max_workers=max_workers)
        logger.info(f"TaskManager 启动: max_workers={max_workers}")

    def create(self, task_type: str) -> Task:
        """创建新任务，返回 Task 对象"""
        tid = str(uuid.uuid4())[:8]
        task = Task(tid, task_type)
        with self._lock:
            self._tasks[tid] = task
            # 清理超量已完成任务
            finished = [t for t in self._tasks.values() if t.status in ("done", "failed", "cancelled")]
            if len(finished) > self._max_finished:
                for t in sorted(finished, key=lambda x: x.finished_at or 0)[:len(finished) - self._max_finished]:
                    del self._tasks[t.task_id]
        logger.debug(f"任务创建: {tid} ({task_type})")
        return task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def run(self, task: Task, func: Callable, *args, **kwargs):
        """提交到线程池执行，自动管理生命周期"""
        def _runner():
            task.status = "running"
            task.progress = "开始执行..."
            try:
                task.result = func(task, *args, **kwargs)
                if task.is_cancelled():
                    task.status = "cancelled"
                else:
                    task.status = "done"
                    task.progress = "完成"
            except TaskCancelledError:
                task.status = "cancelled"
            except Exception as e:
                task.status = "failed"
                task.error = str(e)
                logger.error(f"任务失败: {task.task_id} | {e}")
            task.finished_at = time.time()
            logger.info(f"任务完成: {task.task_id} ({task.status}, {task.finished_at - task.created_at:.1f}s)")

        self._pool.submit(_runner)

    def cancel(self, task_id: str) -> bool:
        """取消任务：设置取消标志，任务节点会在下一次检查时中断"""
        task = self._tasks.get(task_id)
        if task and task.status in ("pending", "running"):
            task._cancel.set()
            task.status = "cancelled"
            task.progress = "正在取消..."
            task.finished_at = time.time()
            logger.info(f"任务取消: {task_id}")
            return True
        return False


task_manager = TaskManager()
