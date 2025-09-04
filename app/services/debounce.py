import asyncio
import time
from dataclasses import dataclass
from typing import Callable, Awaitable, Dict, Optional


@dataclass
class _DebouncePayload:
    """承载一次发送所需的信息。"""
    order_ts_ms: int
    send_factory: Callable[[], Awaitable[None]]


@dataclass
class _DebounceState:
    """某个 (ad_id, device_key) 的去抖状态。"""
    first_submit_ms: int
    due_at_ms: int
    payload: _DebouncePayload
    task: Optional[asyncio.Task]


class DebounceManager:
    """基于内存、事件循环的去抖管理器。

    语义：同一 key 在 inactivity_ms 静默期内仅发送最后一次；等待不超过 max_wait_ms。
    """

    def __init__(self) -> None:
        self._states: Dict[str, _DebounceState] = {}
        self._lock = asyncio.Lock()
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def shutdown(self) -> None:
        self._running = False
        async with self._lock:
            states = list(self._states.values())
            self._states.clear()
        for st in states:
            try:
                if st.task and not st.task.done():
                    st.task.cancel()
            except Exception:
                pass

    async def submit(self, key: str, order_ts_ms: int, inactivity_ms: int, max_wait_ms: int,
                     send_factory: Callable[[], Awaitable[None]]) -> None:
        """提交一次点击；仅在静默期后发送最后一次。"""
        if not self._running:
            # 未启动则直接发送（降级）
            await send_factory()
            return

        now_ms = int(time.time() * 1000)
        async with self._lock:
            st = self._states.get(key)
            if st is None:
                due = min(now_ms + inactivity_ms, now_ms + max_wait_ms)
                new_state = _DebounceState(
                    first_submit_ms=now_ms,
                    due_at_ms=due,
                    payload=_DebouncePayload(order_ts_ms=order_ts_ms, send_factory=send_factory),
                    task=None,
                )
                self._states[key] = new_state
                new_state.task = asyncio.create_task(self._wait_and_fire(key))
                return

            # 若乱序旧点击（order_ts 更小），忽略更新，仅刷新 due_at 以 inactivity 语义为准
            if order_ts_ms >= st.payload.order_ts_ms:
                st.payload = _DebouncePayload(order_ts_ms=order_ts_ms, send_factory=send_factory)

            # 计算新的 due_at：受 max_wait 上限约束
            absolute_deadline = st.first_submit_ms + max_wait_ms
            new_due = min(now_ms + inactivity_ms, absolute_deadline)
            st.due_at_ms = new_due

            # 重新调度：取消原任务并重建
            if st.task and not st.task.done():
                st.task.cancel()
            st.task = asyncio.create_task(self._wait_and_fire(key))

    async def _wait_and_fire(self, key: str) -> None:
        try:
            while True:
                async with self._lock:
                    st = self._states.get(key)
                    if st is None:
                        return
                    wait_ms = max(0, st.due_at_ms - int(time.time() * 1000))
                if wait_ms > 0:
                    try:
                        await asyncio.sleep(wait_ms / 1000.0)
                    except asyncio.CancelledError:
                        return
                # 到期后二次确认（避免竞态）
                async with self._lock:
                    st = self._states.get(key)
                    if st is None:
                        return
                    if int(time.time() * 1000) < st.due_at_ms:
                        # 被推迟了，继续等待
                        continue
                    payload = st.payload
                    # 发送前从状态表删除，避免重复
                    self._states.pop(key, None)
                # 执行发送（不持有锁）
                await payload.send_factory()
                return
        except asyncio.CancelledError:
            return
        except Exception:
            # 静默失败；上层日志在 send_factory 内部处理
            return


_singleton: Optional[DebounceManager] = None


def get_manager() -> DebounceManager:
    global _singleton
    if _singleton is None:
        _singleton = DebounceManager()
    return _singleton


