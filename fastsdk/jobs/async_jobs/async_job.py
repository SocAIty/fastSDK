import asyncio
from concurrent.futures import Future
from datetime import datetime
import traceback

class AsyncJob:

    def __init__(
            self,
            future: Future,
            coro,
            coro_timeout: int = 60,
            delay: float = None
    ):
        self._future = future
        self._coro = coro
        self.coro_timeout = coro_timeout
        self.delay = delay

        self.created_at = datetime.utcnow()
        self.future_result_received_at = None
        self.coroutine_executed_at = None

    @property
    def result(self):
        """
        :return: The server_response of the coroutine if it is done. Or None if it is not done.
        """
        if self._future is None:
            return None

        if not self._future.done():
            return None

        if self.error is not None:
            return None

        self.future_result_received_at = datetime.utcnow()
        future_result = self._future.result()

        return future_result

    @property
    def error(self):
        if self._future is None:
            return None
        if not self._future.done():
            return None
        return self._future.exception()

    async def run(self):
        try:
            self.coroutine_executed_at = datetime.utcnow()
            if self.delay is not None:
                await asyncio.sleep(self.delay)

            result = await self._coro
            self.future_result_received_at = datetime.utcnow()
            self._future.set_result(result)
        except Exception as e:
            result = None
            #traceback.print_exc()
            #print(e.__traceback__)
            self._future.set_exception(e)

        return result

    def get_execution_time(self):
        """
        The interval_sec it took/takes to execute the job in seconds.
        """
        # still running
        if self.future_result_received_at is None:
            return datetime.utcnow() - self.created_at

        return self.future_result_received_at - self.created_at
