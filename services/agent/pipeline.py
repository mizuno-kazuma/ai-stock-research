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
    if coll.status == "failed":
        finish_run(
            state, pipeline_id, status="failed", metrics={"failed_at": "collector"}
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
    return PipelineResult(
        status=overall, market=market, as_of=as_of, jobs=jobs, metrics=metrics
    )
