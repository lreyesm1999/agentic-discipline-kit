"""The documents every dialect renders, compared whole.

Existing tests assert that a title or a body appears somewhere in the generated
surface, so the surrounding document was free to change: the heading an agent
scans for, the row format that carries a discipline's name, the sentence that
says where the full text lives, or the trimming that keeps the body intact. Each
case compares the rendered document against the template it is supposed to be.
"""

from __future__ import annotations

from pathlib import Path

from agentic_discipline.adapters import _index, _rules, _skill_document, sync_adapters
from agentic_discipline.bootstrap import find_contract_root
from agentic_discipline.skills import Discipline, load_disciplines

CORE = "# Constitution\n\n- Prove it or report UNKNOWN.\n- Never weaken a gate.\n"


def _discipline(
    title: str = "Sample Discipline",
    name: str = "agentic-sample",
    when_to_use: str = "When the sample applies.",
) -> Discipline:
    return Discipline(
        id="sample",
        name=name,
        title=title,
        description="What the discipline is for.",
        when_to_use=when_to_use,
        globs=("src/**",),
        always=False,
        phase="build",
        body="\n  Body first line.\n\nBody last line.\n\n\n",
        slug="sample",
    )


def test_the_constitution_loses_only_its_own_title() -> None:
    # The rules sit under a heading the document supplies, so the source title goes.
    assert _rules(CORE) == "- Prove it or report UNKNOWN.\n- Never weaken a gate."
    assert _rules("- Only a rule.\n") == "- Only a rule."


def test_the_index_lists_each_discipline_and_says_where_the_text_lives() -> None:
    first, second = _discipline(), _discipline(title="Second", name="agentic-second")

    rendered = _index([first, second], CORE, ".agentic/skills/")

    assert rendered == (
        "# Agentic Discipline\n\n"
        "## Non-negotiables\n\n"
        "- Prove it or report UNKNOWN.\n"
        "- Never weaken a gate.\n\n"
        "## Disciplines\n\n"
        f"- **{first.title}** (`{first.name}`) - {first.summary}\n"
        f"- **{second.title}** (`{second.name}`) - {second.summary}\n\n"
        "The full text of each discipline lives in `.agentic/skills/`.\n"
    )


def test_a_skill_document_carries_the_body_untrimmed_at_its_end() -> None:
    discipline = _discipline()

    rendered = _skill_document(discipline, CORE)

    assert rendered == (
        f"# {discipline.title}\n\n"
        f"{discipline.description}\n\n"
        f"**When to use.** {discipline.when_to_use}\n\n"
        "\n  Body first line.\n\nBody last line.\n\n"
        "## Non-negotiables\n\n"
        "- Prove it or report UNKNOWN.\n"
        "- Never weaken a gate.\n\n"
        "## Deterministic checks\n\n"
        "Measurable claims are proved by execution, not narration. "
        "When the CLI is available:\n\n"
        "```bash\n"
        "agentic-discipline quality --config agentic.config.json\n"
        "agentic-discipline verify <VERIFIER-ID>\n"
        "```\n"
    )


def test_a_discipline_without_a_trigger_gets_the_documented_fallback() -> None:
    rendered = _skill_document(_discipline(when_to_use=""), CORE)

    assert "**When to use.** See the trigger conditions below.\n" in rendered


def test_each_surface_points_at_the_directory_that_holds_its_full_text(tmp_path: Path) -> None:
    # An index pointing at the wrong directory sends the agent to an empty path.
    project = tmp_path / "project"
    project.mkdir()

    sync_adapters(project, ["generic", "gemini", "copilot"])

    canonical = "The full text of each discipline lives in `.agentic/skills/`."
    assert canonical in (project / "AGENTS.md").read_text(encoding="utf-8")
    assert canonical in (project / "GEMINI.md").read_text(encoding="utf-8")
    assert "The full text of each discipline lives in `.github/instructions/`." in (
        project / ".github" / "copilot-instructions.md"
    ).read_text(encoding="utf-8")


def test_the_real_index_names_every_installed_discipline(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    sync_adapters(project, ["generic"])

    agents = (project / "AGENTS.md").read_text(encoding="utf-8")
    for discipline in load_disciplines(find_contract_root()):
        assert f"- **{discipline.title}** (`{discipline.name}`) - {discipline.summary}" in agents


def test_the_chatgpt_bundle_joins_every_discipline_under_its_heading(tmp_path: Path) -> None:
    disciplines = load_disciplines(find_contract_root())
    sync_adapters(tmp_path, ["chatgpt"])

    bundle = (tmp_path / ".agentic" / "export" / "chatgpt" / "agentic-discipline.md").read_text(
        encoding="utf-8"
    )

    assert bundle.startswith("# Agentic Discipline - ChatGPT bundle\n\n")
    assert bundle.count("\n\n---\n\n") == len(disciplines) - 1
    # Each section's body is trimmed at its end, so no blank run precedes a separator.
    assert "\n\n\n---" not in bundle
    for item in disciplines:
        assert f"## {item.title}\n\n{item.summary}\n\n{item.body.rstrip()}" in bundle
    # Consecutive sections meet at exactly one rule.
    for current, following in zip(disciplines, disciplines[1:], strict=False):
        assert f"{current.body.rstrip()}\n\n---\n\n## {following.title}\n\n" in bundle
