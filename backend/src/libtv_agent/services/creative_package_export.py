"""Read-only response decoration; execution snapshots remain unchanged."""
from __future__ import annotations

from copy import deepcopy

from libtv_agent.creative.package_contract import project_creative_package


def with_creative_package_exports(result: dict) -> dict:
    snapshot = result.get("snapshot", {})
    package_ids = set(snapshot.get("package_contracts", {}))
    current = snapshot.get("package") or {}
    if current.get("package_id"):
        package_ids.add(current["package_id"])
    for package in snapshot.get("storyboard", {}).get("packages", {}).values():
        if package.get("package_id"):
            package_ids.add(package["package_id"])
    exports, errors = {}, {}
    for package_id in sorted(package_ids):
        try:
            exports[package_id] = project_creative_package(snapshot, package_id=package_id)
        except (ValueError, TypeError, KeyError):
            errors[package_id] = "CREATIVE_PACKAGE_EXPORT_UNAVAILABLE"
    return {
        **deepcopy(result),
        "creative_packages": exports,
        "creative_package_errors": errors,
    }
