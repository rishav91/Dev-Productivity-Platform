from __future__ import annotations

from backend.adapters.base import _load_scenario
from backend.schemas.models import SignalExtractor, SourceType, TicketData


class JiraTicketExtractor(SignalExtractor):
    source_type = SourceType.jira_ticket

    async def extract(self, source_id: str) -> TicketData:
        """
        Load TicketData from a fixture scenario file.

        source_id may be a scenario ID or a ticket ID like "PROJ-441".
        """
        scenario = _load_scenario(source_id)
        return TicketData.model_validate(scenario["ticket"])
