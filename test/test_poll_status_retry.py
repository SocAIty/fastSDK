"""Poll retries: transport errors and transient HTTP statuses (503/429)."""
import pytest
from meseex.control_flow import PollAgain

from fastsdk.service_interaction.job_tasks import (
    TRANSIENT_POLL_HTTP_STATUSES,
    retry_poll_or_raise,
)


class _Job:
    def __init__(self):
        self._data = {}

    def get_task_data(self):
        return self._data

    def set_task_data(self, data):
        self._data = data


def test_retry_poll_returns_poll_again_then_raises():
    job = _Job()
    for i in range(4):
        again = retry_poll_or_raise(job, RuntimeError(f"blip-{i}"))
        assert isinstance(again, PollAgain)
        assert job.get_task_data()["number_of_polling_errors"] == i + 1

    with pytest.raises(RuntimeError, match="blip-4"):
        retry_poll_or_raise(job, RuntimeError("blip-4"))


def test_503_and_429_are_transient_poll_statuses():
    assert 503 in TRANSIENT_POLL_HTTP_STATUSES
    assert 429 in TRANSIENT_POLL_HTTP_STATUSES
    assert 404 not in TRANSIENT_POLL_HTTP_STATUSES
    assert 401 not in TRANSIENT_POLL_HTTP_STATUSES
