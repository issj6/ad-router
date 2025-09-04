import asyncio
import json
import time
from typing import Any, Dict, Optional

from ..utils.logger import info, warning, error, perf_info
from .forwarder import dispatch_click_job


class RedisDebounceManager:
    """基于 Redis 的去抖管理器（多进程/多实例安全）。

    键设计（默认前缀 debounce:）：
      - {prefix}latest:{task_key}  → HASH{ first_submit_ms, order_ts_ms, due_at_ms, job_json, updated_ms }
      - {prefix}due                → ZSET(member=task_key, score=due_at_ms)
      - {prefix}lock:{task_key}    → 短期排他锁，SET NX PX
    """

    def __init__(self, redis_client, key_prefix: str = "debounce:", batch: int = 50) -> None:
        self._redis = redis_client
        self._prefix = key_prefix
        self._due_key = f"{self._prefix}due"
        self._batch = batch
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._lock_ttl_ms = 30000

    async def start(self) -> None:
        self._running = True
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker_loop())
        info("Redis Debounce manager started")

    async def shutdown(self) -> None:
        self._running = False
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except Exception:
                pass
        self._worker_task = None
        info("Redis Debounce manager stopped")

    async def submit_job(self, key: str, order_ts_ms: int, inactivity_ms: int, max_wait_ms: int,
                         job: Dict[str, Any]) -> None:
        latest_key = f"{self._prefix}latest:{key}"
        now_ms = int(time.time() * 1000)
        job_json = json.dumps(job, separators=(",", ":"), ensure_ascii=False)

        # Lua 原子更新 latest 与 due
        script = """
        local latest = KEYS[1]
        local due_z = KEYS[2]
        local task_key = ARGV[1]
        local now_ms = tonumber(ARGV[2])
        local inactivity_ms = tonumber(ARGV[3])
        local max_wait_ms = tonumber(ARGV[4])
        local order_ts_ms = tonumber(ARGV[5])
        local job_json = ARGV[6]

        local first = redis.call('HGET', latest, 'first_submit_ms')
        if not first then
            first = now_ms
            redis.call('HSET', latest, 'first_submit_ms', first)
        end

        local old_order = tonumber(redis.call('HGET', latest, 'order_ts_ms') or '-1')
        if order_ts_ms >= old_order then
            redis.call('HSET', latest, 'order_ts_ms', order_ts_ms)
            redis.call('HSET', latest, 'job_json', job_json)
        end

        local abs_deadline = tonumber(first) + max_wait_ms
        local new_due = now_ms + inactivity_ms
        if new_due > abs_deadline then new_due = abs_deadline end

        redis.call('HSET', latest, 'due_at_ms', new_due)
        redis.call('HSET', latest, 'updated_ms', now_ms)
        redis.call('ZADD', due_z, new_due, task_key)
        return new_due
        """

        try:
            await self._redis.eval(
                script,
                2,
                latest_key,
                self._due_key,
                key,
                now_ms,
                int(inactivity_ms),
                int(max_wait_ms),
                int(order_ts_ms),
                job_json,
            )
        except Exception as e:
            error(f"Redis debounce submit failed: {e}")
            # 降级直接发送
            try:
                await dispatch_click_job(job)
            except Exception as ex:
                error(f"Redis debounce fallback send failed: {ex}")

    async def _worker_loop(self) -> None:
        try:
            while self._running:
                try:
                    popped = await self._redis.zpopmin(self._due_key, count=self._batch)
                except Exception as e:
                    warning(f"zpopmin error: {e}")
                    await asyncio.sleep(0.5)
                    continue

                if not popped:
                    await asyncio.sleep(0.2)
                    continue

                now_ms = int(time.time() * 1000)
                for member, score in popped:
                    try:
                        task_key = member
                        if isinstance(task_key, bytes):
                            task_key = task_key.decode('utf-8', errors='ignore')
                        due_score = int(score)

                        lock_key = f"{self._prefix}lock:{task_key}"
                        got = False
                        try:
                            got = await self._redis.set(lock_key, "1", nx=True, px=self._lock_ttl_ms)
                        except Exception as e:
                            warning(f"lock error: {e}")
                        if not got:
                            # 其他实例已处理
                            continue

                        latest_key = f"{self._prefix}latest:{task_key}"
                        data = await self._redis.hgetall(latest_key)
                        if not data:
                            await self._redis.delete(lock_key)
                            continue

                        due_at_ms = int(data.get("due_at_ms", "0"))
                        if due_at_ms > now_ms:
                            # 被延期，重新入队
                            try:
                                await self._redis.zadd(self._due_key, {task_key: due_at_ms})
                            finally:
                                await self._redis.delete(lock_key)
                            continue

                        job_json = data.get("job_json")
                        if not job_json:
                            await self._redis.delete(lock_key)
                            continue
                        try:
                            job = json.loads(job_json)
                        except Exception as e:
                            warning(f"job_json parse error: {e}")
                            await self._redis.delete(lock_key)
                            continue

                        # 执行发送
                        try:
                            await dispatch_click_job(job)
                        except Exception as e:
                            error(f"dispatch_click_job failed: {e}")
                        finally:
                            try:
                                await self._redis.delete(latest_key)
                            finally:
                                await self._redis.delete(lock_key)
                    except Exception as loop_err:
                        warning(f"debounce loop item error: {loop_err}")

                # 小憩，避免空转
                await asyncio.sleep(0.05)

        except asyncio.CancelledError:
            return
        except Exception as e:
            error(f"debounce worker loop crashed: {e}")


_singleton: Optional[RedisDebounceManager] = None


def get_manager() -> RedisDebounceManager:
    """获取 Redis 去抖管理器单例。"""
    global _singleton
    if _singleton is not None:
        return _singleton
    from ..config import CONFIG
    settings = CONFIG.get("settings", {})
    redis_conf = settings.get("redis") or {}
    import redis.asyncio as redis
    client = redis.Redis(
        host=redis_conf.get("host"),
        port=int(redis_conf.get("port", 6379)),
        password=redis_conf.get("password") or None,
        db=int(redis_conf.get("db", 0)),
        decode_responses=True,
    )
    _singleton = RedisDebounceManager(client)
    return _singleton


