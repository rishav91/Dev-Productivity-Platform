from __future__ import annotations

import json
from pathlib import Path

SCENARIOS_DIR = Path(__file__).parent.parent.parent / "fixtures" / "scenarios"


def _load_scenario(scenario_id: str) -> dict:
    """Load a scenario file by ID (e.g. '001', 'DEMO-001')."""
    # Try exact filename match first
    for path in SCENARIOS_DIR.glob("*.json"):
        data = json.loads(path.read_text())
        if data.get("scenario_id") == scenario_id:
            return data

    # Try matching by embedded ID in pr_id / ticket_id
    for path in SCENARIOS_DIR.glob("*.json"):
        data = json.loads(path.read_text())
        if (
            data.get("pr", {}).get("pr_id") == scenario_id
            or data.get("ticket", {}).get("ticket_id") == scenario_id
        ):
            return data

    raise FileNotFoundError(f"No scenario found for id={scenario_id!r} in {SCENARIOS_DIR}")
