import asyncio
from types import SimpleNamespace

from apps.api.app.services.jobs import enqueue_research_run


def test_arq_submission_is_idempotent_and_closes_pool():
    class Pool:
        closed = False
        request = None

        async def enqueue_job(self, function, run_id, **kwargs):
            self.request = (function, run_id, kwargs)
            return SimpleNamespace(job_id=kwargs["_job_id"])

        async def aclose(self):
            self.closed = True

    pool = Pool()

    async def factory(redis_url):
        assert redis_url == "redis://fixture"
        return pool

    job_id = asyncio.run(enqueue_research_run("redis://fixture", "run-1", factory))
    assert job_id == "research:run-1"
    assert pool.request == ("run_research", "run-1", {"_job_id": "research:run-1"})
    assert pool.closed is True
