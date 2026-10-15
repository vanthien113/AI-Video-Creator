"""Load flow-selectors.yaml and turn entries into Playwright locators."""

import re
from pathlib import Path

import yaml

from ..config import ROOT

SELECTORS_FILE = ROOT / "flow-selectors.yaml"


class FlowSelectors:
    def __init__(self, data: dict):
        self.data = data

    @classmethod
    def load(cls, path: Path = SELECTORS_FILE) -> "FlowSelectors":
        with open(path, encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh) or {})

    @property
    def home_url(self) -> str:
        return self.data.get("home_url", "https://flow.google.com/")

    def spec(self, key: str) -> dict:
        if key not in self.data:
            raise KeyError(f"flow-selectors.yaml thiếu mục '{key}'")
        return self.data[key]

    def locate(self, scope, key: str, value: str | int | None = None):
        """Locator for `key`; `scope` is a Page or a Locator."""
        return build_locator(scope, self.spec(key), value)

    def dismiss_specs(self) -> list[dict]:
        return list(self.data.get("dismiss_buttons", []))

    def error_patterns(self) -> dict[str, re.Pattern]:
        return {k: re.compile(v, re.I) for k, v in self.data.get("error_patterns", {}).items()}


def build_locator(scope, spec: dict, value: str | int | None = None):
    def fill(text: str) -> str:
        return text.replace("{value}", str(value)) if value is not None else text

    if "role" in spec:
        kwargs = {}
        if "name" in spec:
            kwargs["name"] = fill(spec["name"])
            kwargs["exact"] = bool(spec.get("exact", False))
        return scope.get_by_role(spec["role"], **kwargs)
    if "css" in spec:
        return scope.locator(fill(spec["css"]))
    if "text" in spec:
        return scope.get_by_text(fill(spec["text"]), exact=bool(spec.get("exact", False)))
    raise ValueError(f"Selector không hợp lệ: {spec}")
