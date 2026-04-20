from __future__ import annotations

from backend.adapters.base import _load_scenario
from backend.schemas.models import SignalExtractor, SlackThreadData, SourceType


class SlackThreadExtractor(SignalExtractor):
    source_type = SourceType.slack_thread

    async def extract(self, source_id: str) -> SlackThreadData | None:
        """
        Load SlackThreadData from a fixture scenario file.

        Returns None when the scenario has no Slack thread (slack: null).
        """
        scenario = _load_scenario(source_id)
        slack_raw = scenario.get("slack")
        if slack_raw is None:
            return None
        return SlackThreadData.model_validate(slack_raw)
