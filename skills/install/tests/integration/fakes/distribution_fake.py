"""Distribution fake — sf-distribution's contract surface as consumed by sf-install.

Mirrors what Stage 2 + Stage 6 consume from sf-distribution: the pinned-version
registry (read at Stage 2 to know which plugins + versions to install; re-read at
Stage 6 to regenerate LICENSES.md) and a thin LICENSES.md rendering helper.

The real surface is currently SKILL.md docs + shell scripts in
skills/sf-doctor/scripts/. When distribution-2 ships a Python entry point this
fake adapts; signature lives in test_contract_drift.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PluginPin:
    name: str
    version: str
    marketplace: str
    id: str
    spdx_license: str
    license_summary: str
    homepage_url: str


@dataclass(frozen=True)
class PinnedRegistry:
    schema_version: int
    framework_version: str
    plugins: tuple[PluginPin, ...]


_DEFAULT_PLUGINS = (
    PluginPin(
        name="context-mode",
        version="1.4.0",
        marketplace="mksglu/context-mode",
        id="context-mode@context-mode",
        spdx_license="ELv2",
        license_summary="Elastic License v2 — not permissive for SaaS distribution.",
        homepage_url="https://github.com/mksglu/context-mode",
    ),
    PluginPin(
        name="claude-mem",
        version="2.1.3",
        marketplace="thedotmack/claude-mem",
        id="claude-mem",
        spdx_license="Apache-2.0",
        license_summary="Apache 2.0 — permissive with patent grant.",
        homepage_url="https://github.com/thedotmack/claude-mem",
    ),
    PluginPin(
        name="superpowers",
        version="5.1.0",
        marketplace="claude-plugins-official",
        id="superpowers@claude-plugins-official",
        spdx_license="MIT",
        license_summary="MIT — fully permissive.",
        homepage_url="https://github.com/obra/superpowers",
    ),
    PluginPin(
        name="skill-creator",
        version="1.0.5",
        marketplace="anthropics/skills",
        id="skill-creator@anthropic-agent-skills",
        spdx_license="Apache-2.0",
        license_summary="Apache 2.0 — permissive with patent grant.",
        homepage_url="https://github.com/anthropics/skills",
    ),
    PluginPin(
        name="context7",
        version="0.9.2",
        marketplace="claude-plugins-official",
        id="context7@claude-plugins-official",
        spdx_license="MIT",
        license_summary="MIT — fully permissive.",
        homepage_url="https://context7.com",
    ),
    PluginPin(
        name="claude-md-management",
        version="1.0.1",
        marketplace="claude-plugins-official",
        id="claude-md-management@claude-plugins-official",
        spdx_license="MIT",
        license_summary="MIT — fully permissive.",
        homepage_url="https://example.com",
    ),
)


class DistributionFake:
    """Pluggable fake for the distribution contract surface."""

    def __init__(self) -> None:
        self._registry = PinnedRegistry(
            schema_version=1,
            framework_version="1.0.0",
            plugins=_DEFAULT_PLUGINS,
        )
        self._licenses_md_content: str = ""
        self.calls: list[tuple] = []

    # ----- contract surface -----

    def read_pinned_registry(self) -> PinnedRegistry:
        self.calls.append(("read_pinned_registry",))
        return self._registry

    def regenerate_licenses_md(self, wiki_root) -> str:
        """Render LICENSES.md content from the current pinned registry.

        Stage 6 calls this; the install orchestrator handles the write (no
        overwrite without explicit approval, per ADR-017).
        """
        self.calls.append(("regenerate_licenses_md", wiki_root))
        lines = ["# Stack Licenses", ""]
        lines.append("## Required plugins")
        lines.append("")
        for plugin in self._registry.plugins:
            lines.append(
                f"- **`{plugin.name}@{plugin.version}`** "
                f"(`{plugin.spdx_license}`) — {plugin.license_summary} "
                f"[{plugin.homepage_url}]({plugin.homepage_url})"
            )
        lines.append("")
        rendered = "\n".join(lines) + "\n"
        self._licenses_md_content = rendered
        return rendered

    # ----- injection helpers -----

    def inject_registry(self, registry: PinnedRegistry) -> None:
        self._registry = registry

    def inject_framework_version(self, version: str) -> None:
        self._registry = PinnedRegistry(
            schema_version=self._registry.schema_version,
            framework_version=version,
            plugins=self._registry.plugins,
        )

    def last_licenses_md(self) -> str:
        return self._licenses_md_content

    def call_names(self) -> list[str]:
        return [c[0] for c in self.calls]
