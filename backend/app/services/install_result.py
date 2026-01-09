"""
Install Result Model

统一的结果/状态模型，替代直接使用 dict。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class InstallResult:
    """Capability installation result model"""

    capability_code: Optional[str] = None
    installed: Dict[str, List[str]] = field(default_factory=lambda: {
        "playbooks": [],
        "tools": [],
        "services": [],
        "api_endpoints": [],
        "schema_modules": [],
        "database_models": [],
        "migrations": [],
        "ui_components": [],
        "root_files": []
    })
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    missing_dependencies: Dict[str, List[str]] = field(default_factory=dict)
    degradation_status: Optional[Dict[str, Any]] = None
    playbook_validation: Optional[Dict[str, Any]] = None
    migration_status: Optional[Dict[str, str]] = None
    bootstrap: List[str] = field(default_factory=list)

    def add_error(self, error: str):
        """Add an error message"""
        if error and error not in self.errors:
            self.errors.append(error)

    def add_warning(self, warning: str):
        """Add a warning message"""
        if warning and warning not in self.warnings:
            self.warnings.append(warning)

    def add_installed(self, category: str, item: str):
        """Add an installed item to a category"""
        if category not in self.installed:
            self.installed[category] = []
        if item and item not in self.installed[category]:
            self.installed[category].append(item)

    def extend_installed(self, category: str, items: List[str]):
        """Extend installed items in a category"""
        if category not in self.installed:
            self.installed[category] = []
        for item in items:
            if item and item not in self.installed[category]:
                self.installed[category].append(item)

    def has_errors(self) -> bool:
        """Check if there are any errors"""
        return len(self.errors) > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (for backward compatibility)"""
        result = {
            "capability_code": self.capability_code,
            "installed": self.installed,
            "warnings": self.warnings,
            "errors": self.errors
        }

        if self.missing_dependencies:
            result["missing_dependencies"] = self.missing_dependencies
        if self.degradation_status:
            result["degradation_status"] = self.degradation_status
        if self.playbook_validation:
            result["playbook_validation"] = self.playbook_validation
        if self.migration_status:
            result["migration_status"] = self.migration_status
        if self.bootstrap:
            result["bootstrap"] = self.bootstrap

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InstallResult":
        """Create from dictionary (for backward compatibility)"""
        result = cls(
            capability_code=data.get("capability_code"),
            installed=data.get("installed", {
                "playbooks": [],
                "tools": [],
                "services": [],
                "api_endpoints": [],
                "schema_modules": [],
                "database_models": [],
                "migrations": [],
                "ui_components": [],
                "root_files": []
            }),
            warnings=data.get("warnings", []),
            errors=data.get("errors", []),
            missing_dependencies=data.get("missing_dependencies", {}),
            degradation_status=data.get("degradation_status"),
            playbook_validation=data.get("playbook_validation"),
            migration_status=data.get("migration_status"),
            bootstrap=data.get("bootstrap", [])
        )
        return result


