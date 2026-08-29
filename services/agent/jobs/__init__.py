from services.agent.jobs.analyst import analyst
from services.agent.jobs.collector import collector
from services.agent.jobs.critic import critic
from services.agent.jobs.evaluator import evaluator
from services.agent.jobs.maintenance import garch_refit, model_retrain, weekly_review
from services.agent.jobs.researcher import researcher
from services.agent.jobs.strategist import strategist

__all__ = [
    "analyst",
    "collector",
    "critic",
    "evaluator",
    "garch_refit",
    "model_retrain",
    "researcher",
    "strategist",
    "weekly_review",
]
