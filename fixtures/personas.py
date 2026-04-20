from dataclasses import dataclass


@dataclass
class TeamMember:
    id: str
    avg_review_days: float
    stddev: float
    name: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.id.replace("eng_", "").capitalize()


@dataclass
class Component:
    name: str
    blocker_rate: float
    common_blocker: str


TEAM_PERSONAS: list[TeamMember] = [
    TeamMember(id="eng_alice", avg_review_days=1.5, stddev=0.8),    # fast reviewer
    TeamMember(id="eng_bob",   avg_review_days=6.2, stddev=2.1),    # consistent bottleneck
    TeamMember(id="eng_carol", avg_review_days=2.8, stddev=1.2),
    TeamMember(id="eng_dave",  avg_review_days=3.1, stddev=0.9),
    TeamMember(id="eng_eve",   avg_review_days=4.5, stddev=1.8),    # slow on reviews
    TeamMember(id="eng_frank", avg_review_days=2.0, stddev=0.6),
]

TEAM_MEMBER_IDS: list[str] = [m.id for m in TEAM_PERSONAS]

COMPONENTS: list[Component] = [
    Component(name="payments",  blocker_rate=0.60, common_blocker="review_bottleneck"),
    Component(name="auth",      blocker_rate=0.40, common_blocker="unclear_requirements"),
    Component(name="api",       blocker_rate=0.25, common_blocker="scope_creep"),
    Component(name="dashboard", blocker_rate=0.10, common_blocker="none"),
    Component(name="infra",     blocker_rate=0.30, common_blocker="dependency_block"),
]

COMPONENT_NAMES: list[str] = [c.name for c in COMPONENTS]

# Reviewer pool per component — some members specialize in certain areas
COMPONENT_REVIEWERS: dict[str, list[str]] = {
    "payments":  ["eng_bob", "eng_alice", "eng_carol"],
    "auth":      ["eng_alice", "eng_dave", "eng_bob"],
    "api":       ["eng_frank", "eng_carol", "eng_eve"],
    "dashboard": ["eng_carol", "eng_frank", "eng_dave"],
    "infra":     ["eng_dave", "eng_eve", "eng_alice"],
}

# Representative file paths per component for realistic PR data
COMPONENT_FILES: dict[str, list[str]] = {
    "payments":  [
        "payments/processor.py", "payments/webhook.py", "payments/models.py",
        "payments/validators.py", "payments/utils.py", "payments/tests/test_processor.py",
    ],
    "auth":      [
        "auth/middleware.py", "auth/tokens.py", "auth/permissions.py",
        "auth/models.py", "auth/oauth.py", "auth/tests/test_tokens.py",
    ],
    "api":       [
        "api/routes.py", "api/serializers.py", "api/pagination.py",
        "api/throttling.py", "api/tests/test_routes.py",
    ],
    "dashboard": [
        "dashboard/views.py", "dashboard/charts.py", "dashboard/filters.py",
        "dashboard/tests/test_views.py",
    ],
    "infra":     [
        "infra/deploy.yml", "infra/k8s/deployment.yaml", "infra/terraform/main.tf",
        "infra/scripts/migrate.sh", "infra/monitoring/alerts.yaml",
    ],
}
