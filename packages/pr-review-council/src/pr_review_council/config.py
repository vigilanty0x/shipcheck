"""Council configuration with fail-closed validation."""

from dataclasses import dataclass

from .models import Severity, ValidationError


@dataclass(frozen=True, slots=True)
class CouncilConfig:
    enabled_reviewers: tuple[str, ...] = (
        "security",
        "reliability",
        "testing",
        "maintainability",
    )
    minimum_successful_reviewers: int = 3
    blocking_severities: tuple[Severity, ...] = (Severity.CRITICAL,)

    def __post_init__(self) -> None:
        if not self.enabled_reviewers:
            raise ValidationError("at least one reviewer must be enabled")
        if len(self.enabled_reviewers) != len(set(self.enabled_reviewers)):
            raise ValidationError("enabled reviewer names must be unique")
        if not 1 <= self.minimum_successful_reviewers <= len(self.enabled_reviewers):
            raise ValidationError("minimum_successful_reviewers is outside the enabled reviewer range")
        if not self.blocking_severities:
            raise ValidationError("at least one blocking severity is required")
