"""
Hash-addressed prompt template registry.

Prompts are registered by name and version, stored as plain strings, and
referenced in traces by their SHA-256 prefix. This ensures traces are
reproducible: the hash tells you exactly which prompt was used, even if the
prompt is later modified.

Usage:
    from orchestration.llmops import register, get, hash_text

    register("adjudicator_system", "v1", SYSTEM_PROMPT_TEXT)
    vp = get("adjudicator_system")
    metadata["prompt_hash"] = vp.hash   # record in NodeResult.metadata
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class VersionedPrompt:
    name: str
    version: str
    template: str
    hash: str  # first 16 hex chars of SHA-256


def hash_text(text: str) -> str:
    """Return the first 16 hex chars of the SHA-256 of *text*."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class PromptRegistry:
    """Global singleton-style registry; use module-level helpers instead."""

    def __init__(self) -> None:
        self._prompts: dict[str, VersionedPrompt] = {}

    def register(self, name: str, version: str, template: str) -> VersionedPrompt:
        """Register *template* under *name* (overwrites existing entry)."""
        vp = VersionedPrompt(
            name=name,
            version=version,
            template=template,
            hash=hash_text(template),
        )
        self._prompts[name] = vp
        return vp

    def get(self, name: str) -> VersionedPrompt:
        """Return the registered prompt for *name*; raise KeyError if absent."""
        try:
            return self._prompts[name]
        except KeyError:
            raise KeyError(f"No prompt registered under '{name}'") from None

    def list_names(self) -> list[str]:
        return sorted(self._prompts)

    def __len__(self) -> int:
        return len(self._prompts)


_registry = PromptRegistry()


def register(name: str, version: str, template: str) -> VersionedPrompt:
    return _registry.register(name, version, template)


def get(name: str) -> VersionedPrompt:
    return _registry.get(name)


def list_names() -> list[str]:
    return _registry.list_names()
