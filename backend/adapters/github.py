from __future__ import annotations

import json
from pathlib import Path

from backend.adapters.base import _load_scenario
from backend.schemas.models import PRData, SignalExtractor, SourceType


class GitHubPRExtractor(SignalExtractor):
    source_type = SourceType.github_pr

    async def extract(self, source_id: str) -> PRData:
        """
        Load PRData from a fixture scenario file.

        source_id may be:
          - A scenario ID like "001" or "002"
          - A PR ID like "PR-DEMO-001" (matched by pr.pr_id in the scenario)
        """
        scenario = _load_scenario(source_id)
        return PRData.model_validate(scenario["pr"])


def load_pr_by_id(pr_id: str) -> PRData:
    """Convenience function for use inside nodes without instantiating the class."""
    extractor = GitHubPRExtractor()
    import asyncio
    return asyncio.get_event_loop().run_until_complete(extractor.extract(pr_id))
