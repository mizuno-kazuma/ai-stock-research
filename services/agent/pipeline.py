"""6 ジョブのパイプライン。前段の部分失敗でも機能縮退して続行する。"""

from __future__ import annotations

from datetime import date
from typing import Any

from packages.core.interfaces.storage import MemoryRepo, StateRepo, WarehouseRepo
from packages.core.llm.router import LLMRouter
from packages.core.models.ranker import FittedRanker
from services.agent.deps import begin_run, finish_run
from services.agent.jobs.analyst import analyst
from services.agent.jobs.collector import collector
from services.agent.jobs.critic import critic
from services.agent.jobs.evaluator import evaluator
from services.agent.jobs.researcher import researcher
from services.agent.jobs.strategist import strategist
from services.agent.progress import publish_job_finished, publish_job_progress
from services.agent.types import JobResult, PipelineResult


def run_pipeline(
    market: str,
    as_of: date,
    *,
    state: StateRepo,
    warehouse: WarehouseRepo,
    router: LLMRouter | None = None,
    ranker: FittedRanker | None = None,
    collector_steps: dict | None = None,
    memory: MemoryRepo | None = None,
    trigger: str = "schedule",
    **kwargs: Any,
) -> PipelineResult:
    """Collector → Analyst → Researcher → Strategist → Critic → Evaluator。

    prices 必須失敗時のみ全体 failed。LLM キャップは partial で推奨を残す。
    """
    pipeline_id = begin_run(
        state, job_name="pipeline", market=market, trigger=trigger
    )
    jobs: dict[str, JobResult] = {}
    try:
        return _run_pipeline_jobs(
            pipeline_id,
            market,
            as_of,
            state=state,
            warehouse=warehouse,
            router=router,
            ranker=ranker,
            collector_steps=collector_steps,
            memory=memory,
            trigger=trigger,
            kwargs=kwargs,
            jobs=jobs,
        )
    except Exception as exc:
        finish_run(
            state,
            pipeline_id,
            status="failed",
            metrics={"jobs": {k: v.status for k, v in jobs.items()}},
            error=exc,
        )
        publish_job_finished(
            job_run_id=pipeline_id,
            status="failed",
            failed_steps=list(jobs),
        )
        raise


def _run_pipeline_jobs(
    pipeline_id: int,
    market: str,
    as_of: date,
    *,
    state: StateRepo,
    warehouse: WarehouseRepo,
    router: LLMRouter | None,
    ranker: FittedRanker | None,
    collector_steps: dict | None,
    memory: MemoryRepo | None,
    trigger: str,
    kwargs: dict[str, Any],
    jobs: dict[str, JobResult],
) -> PipelineResult:

    phases = ("collector", "analyst", "researcher", "strategist", "critic", "evaluator")

    def _mark(done: int, phase: str) -> None:
        publish_job_progress(
            job_run_id=pipeline_id,
            job_name="pipeline",
            phase=phase,
            completed=done,
            total=len(phases),
        )

    coll = collector(
        market,
        as_of,
        state=state,
        warehouse=warehouse,
        steps=collector_steps,
        trigger=trigger,
        parent_run_id=pipeline_id,
    )
    jobs["collector"] = coll
    _mark(1, "collector")
    if coll.status == "failed":
        finish_run(
            state, pipeline_id, status="failed", metrics={"failed_at": "collector"}
        )
        publish_job_finished(
            job_run_id=pipeline_id,
            status="failed",
            failed_steps=["collector"],
        )
        return PipelineResult(
            status="failed", market=market, as_of=as_of, jobs=jobs
        )

    ana = analyst(
        market,
        as_of,
        state=state,
        warehouse=warehouse,
        ranker=ranker,
        prices=kwargs.get("prices"),
        securities=kwargs.get("securities"),
        financials=kwargs.get("financials"),
        fx=kwargs.get("fx"),
        trigger=trigger,
        parent_run_id=pipeline_id,
    )
    jobs["analyst"] = ana
    _mark(2, "analyst")

    res = researcher(
        market,
        as_of,
        state=state,
        warehouse=warehouse,
        router=router,
        tickers=kwargs.get("tickers"),
        trigger=trigger,
        parent_run_id=pipeline_id,
    )
    jobs["researcher"] = res
    _mark(3, "researcher")

    strat = strategist(
        market,
        as_of,
        state=state,
        warehouse=warehouse,
        memory=memory or state,
        router=router,
        scores=kwargs.get("scores"),
        outcomes=kwargs.get("outcomes"),
        researcher_qual=res.recs,
        trigger=trigger,
        parent_run_id=pipeline_id,
    )
    jobs["strategist"] = strat
    _mark(4, "strategist")

    cri = critic(
        market,
        as_of,
        state=state,
        warehouse=warehouse,
        router=router,
        recs=strat.recs,
        jquants_plan=kwargs.get("jquants_plan", "light"),
        trigger=trigger,
        parent_run_id=pipeline_id,
    )
    jobs["critic"] = cri
    _mark(5, "critic")

    eva = evaluator(
        market,
        as_of,
        state=state,
        warehouse=warehouse,
        memory=memory or state,
        router=router,
        trigger=trigger,
        parent_run_id=pipeline_id,
    )
    jobs["evaluator"] = eva

    statuses = [j.status for j in jobs.values()]
    if all(s == "success" for s in statuses):
        overall = "success"
    elif coll.status == "failed":
        overall = "failed"
    else:
        overall = "partial"
    metrics = {
        "jobs": {k: v.status for k, v in jobs.items()},
        "n_recs": len(strat.recs),
        "llm_capped": bool(
            res.metrics.get("llm_capped") or strat.metrics.get("llm_capped")
        ),
    }
    finish_run(state, pipeline_id, status=overall, metrics=metrics)
    _mark(6, "evaluator")
    publish_job_finished(job_run_id=pipeline_id, status=overall)
    return PipelineResult(
        status=overall, market=market, as_of=as_of, jobs=jobs, metrics=metrics
    )
