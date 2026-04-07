#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from typing import Iterable


USER_AGENT = "skillscan/0.1 (+https://skills.sh)"
MAX_TEXT_CHARS = 4000
MAX_DOC_FILES = 20
MAX_TREE_ENTRIES = 400
HOMEPAGE_URL = "https://skills.sh"
GITHUB_API = "https://api.github.com/repos/{source}"
GITHUB_CACHE: dict[str, dict] = {}
REQUEST_TIMEOUT_SECONDS = 3


@dataclass
class ProjectSummary:
    root: str
    files_scanned: list[str]
    docs_read: list[str]
    structure_sample: list[str]
    languages: list[str]
    frameworks: list[str]
    package_managers: list[str]
    workflows: list[str]
    important_files: list[str]
    missing_areas: list[str]
    keywords: list[str]
    signal_keywords: list[str]
    synopsis: str


@dataclass
class SkillCandidate:
    source: str
    skill_id: str
    name: str
    installs: int
    detail_url: str = ""
    install_command: str = ""
    summary: str = ""
    repo_stars: int | None = None
    repo_updated_at: str | None = None
    repo_pushed_at: str | None = None
    repo_description: str = ""
    repo_topics: list[str] = field(default_factory=list)
    score: float = 0.0
    repo_fit: float = 0.0
    quality: float = 0.0
    popularity: float = 0.0
    freshness: float = 0.0
    overlap_penalty: float = 0.0
    conflict_penalty: float = 0.0
    baseline_boost: float = 0.0
    relevance_penalty: float = 0.0
    why: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    bucket: str = ""


def _read_text(path: Path, limit: int = MAX_TEXT_CHARS) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    return text[:limit]


def _safe_json(path: Path) -> dict:
    try:
        return json.loads(_read_text(path, limit=200_000) or "{}")
    except json.JSONDecodeError:
        return {}


def _tokenize(text: str) -> set[str]:
    tokens: set[str] = set()
    for token in re.findall(r"[a-z0-9][a-z0-9-]{1,40}", text.lower()):
        if token not in STOP_WORDS:
            tokens.add(token)
        if "-" in token:
            for part in token.split("-"):
                if len(part) >= 2 and part not in STOP_WORDS:
                    tokens.add(part)
    return tokens


def _iter_paths(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        yield path


def scan_project(root: Path) -> ProjectSummary:
    files_scanned: list[str] = []
    docs_read: list[str] = []
    structure_sample: list[str] = []
    important_files: list[str] = []
    languages: set[str] = set()
    frameworks: set[str] = set()
    package_managers: set[str] = set()
    workflows: set[str] = set()
    keywords: set[str] = set()
    signal_keywords: set[str] = set()

    readme_files = sorted(root.glob("README*"))
    docs_files = sorted(
        path for path in _iter_paths(root) if path.is_file() and "docs" in path.parts
    )[:MAX_DOC_FILES]
    package_json = root / "package.json"

    for path in sorted(_iter_paths(root)):
        rel = path.relative_to(root).as_posix()
        if len(structure_sample) < MAX_TREE_ENTRIES:
            structure_sample.append(rel)
        if path.is_dir():
            continue
        files_scanned.append(rel)
        lower = path.name.lower()
        if lower.startswith("readme") or path.parent.name == "docs":
            docs_read.append(rel)
        if lower in IMPORTANT_FILES:
            important_files.append(rel)

        suffix = path.suffix.lower()
        if suffix in SUFFIX_LANGUAGE_MAP:
            languages.add(SUFFIX_LANGUAGE_MAP[suffix])

        if lower in FILE_SIGNAL_MAP:
            frameworks.update(FILE_SIGNAL_MAP[lower].get("frameworks", set()))
            workflows.update(FILE_SIGNAL_MAP[lower].get("workflows", set()))
            package_managers.update(FILE_SIGNAL_MAP[lower].get("package_managers", set()))

    for readme in readme_files[:3]:
        keywords.update(_tokenize(_read_text(readme)))

    for doc in docs_files:
        keywords.update(_tokenize(_read_text(doc)))

    if package_json.exists():
        package_managers.add("npm")
        workflows.update({"build"})
        important_files.append("package.json")
        pkg = _safe_json(package_json)
        deps = {
            *pkg.get("dependencies", {}).keys(),
            *pkg.get("devDependencies", {}).keys(),
            *pkg.get("peerDependencies", {}).keys(),
        }
        keywords.update(_tokenize(" ".join(deps)))
        keywords.update(_tokenize(pkg.get("description", "")))
        scripts = pkg.get("scripts", {})
        workflows.update(script_to_workflows(scripts))
        frameworks.update(dep_to_frameworks(deps))
        package_managers.update(lockfile_package_managers(root))
        signal_keywords.update(_tokenize(" ".join(deps)))
        if "typescript" in deps:
            languages.add("TypeScript")
        if "react" in deps:
            languages.add("JavaScript")

    important_files = sorted(set(important_files))
    package_managers.update(lockfile_package_managers(root))
    workflows.update(extra_workflows_from_root(root))

    missing_areas = infer_missing_areas(root, workflows, important_files)
    keywords.update(_tokenize(" ".join(frameworks)))
    keywords.update(_tokenize(" ".join(workflows)))
    keywords.update(_tokenize(" ".join(missing_areas)))
    signal_keywords.update(_tokenize(" ".join(frameworks)))
    signal_keywords.update(_tokenize(" ".join(workflows)))
    signal_keywords.update(_tokenize(" ".join(package_managers)))
    signal_keywords.update(_tokenize(" ".join(languages)))
    signal_keywords.update(_tokenize(" ".join(important_files)))
    signal_keywords.update(_tokenize(" ".join(missing_areas)))
    synopsis = build_synopsis(root, languages, frameworks, workflows, missing_areas)

    return ProjectSummary(
        root=str(root),
        files_scanned=files_scanned,
        docs_read=docs_read[:MAX_DOC_FILES],
        structure_sample=structure_sample,
        languages=sorted(languages),
        frameworks=sorted(frameworks),
        package_managers=sorted(package_managers),
        workflows=sorted(workflows),
        important_files=important_files,
        missing_areas=missing_areas,
        keywords=sorted(keywords),
        signal_keywords=sorted(signal_keywords),
        synopsis=synopsis,
    )


def script_to_workflows(scripts: dict) -> set[str]:
    workflows: set[str] = set()
    lowered = {key.lower(): str(value).lower() for key, value in scripts.items()}
    for key, value in lowered.items():
        blob = f"{key} {value}"
        if "test" in blob:
            workflows.add("testing")
        if "lint" in blob or "eslint" in blob:
            workflows.add("linting")
        if "typecheck" in blob or "tsc" in blob or "mypy" in blob:
            workflows.add("type-checking")
        if "build" in blob:
            workflows.add("build")
        if "dev" in blob or "start" in blob:
            workflows.add("local-development")
        if "storybook" in blob:
            workflows.add("storybook")
        if "playwright" in blob or "cypress" in blob:
            workflows.add("e2e-testing")
    return workflows


def dep_to_frameworks(deps: Iterable[str]) -> set[str]:
    frameworks: set[str] = set()
    dep_set = {dep.lower() for dep in deps}
    for dep, values in DEP_FRAMEWORK_MAP.items():
        if dep in dep_set:
            frameworks.update(values)
    return frameworks


def lockfile_package_managers(root: Path) -> set[str]:
    mapping = {
        "package-lock.json": "npm",
        "pnpm-lock.yaml": "pnpm",
        "yarn.lock": "yarn",
        "bun.lockb": "bun",
        "bun.lock": "bun",
        "poetry.lock": "poetry",
        "uv.lock": "uv",
    }
    found = set()
    for file_name, manager in mapping.items():
        if (root / file_name).exists():
            found.add(manager)
    return found


def extra_workflows_from_root(root: Path) -> set[str]:
    workflows: set[str] = set()
    if (root / "tests").exists() or (root / "test").exists():
        workflows.add("testing")
    if (root / ".github/workflows").exists():
        workflows.add("ci")
    if (root / "Dockerfile").exists() or (root / "docker-compose.yml").exists():
        workflows.add("containers")
    if (root / "terraform").exists() or any(root.glob("*.tf")):
        workflows.add("infrastructure")
    return workflows


def infer_missing_areas(root: Path, workflows: set[str], important_files: list[str]) -> list[str]:
    missing: list[str] = []
    if not list(root.glob("README*")):
        missing.append("project-readme")
    if not (root / "docs").exists():
        missing.append("project-docs")
    if "testing" not in workflows:
        missing.append("automated-tests")
    if "linting" not in workflows:
        missing.append("linting")
    if "type-checking" not in workflows:
        missing.append("type-checking")
    if "ci" not in workflows:
        missing.append("ci-pipeline")
    if not any(
        name == ".env.example"
        or name.endswith("/.env.example")
        or name == ".env.sample"
        or name.endswith("/.env.sample")
        for name in important_files
    ):
        missing.append("environment-template")
    return missing


def build_synopsis(
    root: Path, languages: set[str], frameworks: set[str], workflows: set[str], missing_areas: list[str]
) -> str:
    parts = [f"Project root: {root}."]
    parts.append(
        "Detected stack: "
        + ", ".join(sorted(frameworks or languages) or ["undetermined"])
        + "."
    )
    if workflows:
        parts.append("Workflows: " + ", ".join(sorted(workflows)) + ".")
    if missing_areas:
        parts.append("Missing areas: " + ", ".join(missing_areas[:6]) + ".")
    return " ".join(parts)


def fetch_url(url: str, timeout_seconds: int = REQUEST_TIMEOUT_SECONDS) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8", "ignore")


def fetch_json(url: str, timeout_seconds: int = REQUEST_TIMEOUT_SECONDS) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json, application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8", "ignore"))


def extract_catalog(html: str) -> list[SkillCandidate]:
    decoded = unescape(html.replace('\\"', '"'))
    pattern = re.compile(
        r'{"source":"(?P<source>[^"]+)","skillId":"(?P<skill>[^"]+)","name":"(?P<name>[^"]+)","installs":(?P<installs>\d+)}'
    )
    seen: set[tuple[str, str]] = set()
    candidates: list[SkillCandidate] = []
    for match in pattern.finditer(decoded):
        key = (match.group("source"), match.group("skill"))
        if key in seen:
            continue
        seen.add(key)
        source = match.group("source")
        skill_id = match.group("skill")
        candidates.append(
            SkillCandidate(
                source=source,
                skill_id=skill_id,
                name=match.group("name"),
                installs=int(match.group("installs")),
                detail_url=f"{HOMEPAGE_URL}/{source}/{skill_id}",
            )
        )
    return candidates


def enrich_candidate(candidate: SkillCandidate) -> None:
    try:
        html = fetch_url(candidate.detail_url)
    except Exception:
        candidate.warnings.append("Skill detail page unavailable.")
        return

    cmd_match = re.search(r"npx skills add [^<]+", html)
    if cmd_match:
        candidate.install_command = unescape(cmd_match.group(0).strip())

    summary_match = re.search(r"<div class=\"prose [^\"]*\"><p><strong>(.*?)</strong></p>(.*?)</div>", html, re.S)
    if summary_match:
        candidate.summary = clean_html(summary_match.group(1) + " " + summary_match.group(2))
    else:
        meta_match = re.search(r'<title>(.*?)</title>', html)
        if meta_match:
            candidate.summary = clean_html(meta_match.group(1))

    repo = GITHUB_CACHE.get(candidate.source)
    if repo is None:
        try:
            repo = fetch_json(GITHUB_API.format(source=candidate.source))
            GITHUB_CACHE[candidate.source] = repo
        except urllib.error.HTTPError as exc:
            candidate.warnings.append(f"GitHub metadata unavailable ({exc.code}).")
            return
        except Exception:
            candidate.warnings.append("GitHub metadata unavailable.")
            return

    candidate.repo_stars = repo.get("stargazers_count")
    candidate.repo_updated_at = repo.get("updated_at")
    candidate.repo_pushed_at = repo.get("pushed_at")
    candidate.repo_description = repo.get("description") or ""
    candidate.repo_topics = list(repo.get("topics") or [])


def clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def rank_candidates(project: ProjectSummary, candidates: list[SkillCandidate], top_n: int) -> list[SkillCandidate]:
    max_installs = max((c.installs for c in candidates), default=1)
    signal_tokens = set(project.signal_keywords)
    if not signal_tokens:
        signal_tokens = set(project.keywords)
    framework_tokens = _tokenize(" ".join(project.frameworks + project.languages + project.package_managers))
    workflow_tokens = _tokenize(" ".join(project.workflows))
    profile_tokens = _tokenize(" ".join(project.frameworks + project.workflows + project.languages))

    for candidate in candidates:
        text = " ".join(
            [
                candidate.name,
                candidate.skill_id,
                candidate.summary,
                candidate.repo_description,
                " ".join(candidate.repo_topics),
                candidate.source.replace("/", " "),
            ]
        )
        skill_tokens = _tokenize(text)
        overlap = signal_tokens & skill_tokens
        framework_overlap = framework_tokens & skill_tokens
        workflow_overlap = workflow_tokens & skill_tokens
        framework_score = 0.0
        workflow_score = 0.0
        token_score = 0.0
        if framework_tokens:
            framework_score = 70.0 * (len(framework_overlap) / len(framework_tokens))
        if workflow_tokens:
            workflow_score = 20.0 * (len(workflow_overlap) / len(workflow_tokens))
        if signal_tokens:
            token_score = 10.0 * (len(overlap) / len(signal_tokens))
        repo_fit = min(100.0, framework_score + workflow_score + token_score)
        popularity = 100.0 * math.log(candidate.installs + 1) / math.log(max_installs + 1)
        quality = score_quality(candidate)
        freshness = score_freshness(candidate.repo_pushed_at or candidate.repo_updated_at)
        baseline_boost = score_baseline_alignment(project, candidate, skill_tokens)
        relevance_penalty = score_relevance_penalty(
            project,
            skill_tokens,
            overlap=overlap,
            framework_overlap=framework_overlap,
            workflow_overlap=workflow_overlap,
            profile_tokens=profile_tokens,
        )

        candidate.repo_fit = round(repo_fit, 2)
        candidate.popularity = round(popularity, 2)
        candidate.quality = round(quality, 2)
        candidate.freshness = round(freshness, 2)
        candidate.baseline_boost = round(baseline_boost, 2)
        candidate.relevance_penalty = round(relevance_penalty, 2)
        candidate.score = round(
            (0.4 * repo_fit + 0.2 * quality + 0.15 * popularity + 0.1 * freshness)
            + baseline_boost
            - relevance_penalty,
            2,
        )
        candidate.why = build_why(project, candidate, overlap)

    ranked = sorted(candidates, key=lambda item: item.score, reverse=True)
    apply_overlap_penalties(ranked)
    ranked = sorted(ranked, key=lambda item: item.score, reverse=True)

    for candidate in ranked:
        if candidate.score >= 45:
            candidate.bucket = "install-now"
        elif candidate.score >= 30:
            candidate.bucket = "optional-later"
        else:
            candidate.bucket = "discard"

    selected_limit = max(top_n * 2, 40)
    selected = ranked[:selected_limit]
    return selected


def score_quality(candidate: SkillCandidate) -> float:
    score = 15.0
    if candidate.summary:
        score += min(35.0, len(candidate.summary) / 6)
    if candidate.install_command:
        score += 10.0
    if candidate.repo_description:
        score += min(20.0, len(candidate.repo_description) / 8)
    if candidate.repo_topics:
        score += min(10.0, len(candidate.repo_topics) * 2)
    if candidate.repo_stars is not None:
        score += min(10.0, math.log(candidate.repo_stars + 1, 10) * 4)
    return min(score, 100.0)


def score_freshness(date_str: str | None) -> float:
    if not date_str:
        return 30.0
    try:
        updated = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return 30.0
    days = max((datetime.now(UTC) - updated).days, 0)
    if days <= 7:
        return 100.0
    if days <= 30:
        return 85.0
    if days <= 90:
        return 65.0
    if days <= 180:
        return 45.0
    if days <= 365:
        return 30.0
    return 15.0


def build_why(project: ProjectSummary, candidate: SkillCandidate, overlap: set[str]) -> list[str]:
    reasons = []
    if overlap:
        reasons.append("Matches repo signals: " + ", ".join(sorted(list(overlap))[:5]))
    if candidate.summary:
        reasons.append(candidate.summary[:180])
    if candidate.installs:
        reasons.append(f"Live installs on skills.sh: {candidate.installs}")
    if candidate.baseline_boost > 0:
        reasons.append(f"Baseline quality boost: +{candidate.baseline_boost:.1f}")
    if candidate.relevance_penalty > 0:
        reasons.append(f"Relevance penalty: -{candidate.relevance_penalty:.1f}")
    if candidate.repo_pushed_at:
        reasons.append(f"Source repo recently pushed: {candidate.repo_pushed_at[:10]}")
    return reasons[:4]


def score_baseline_alignment(project: ProjectSummary, candidate: SkillCandidate, skill_tokens: set[str]) -> float:
    boost = 0.0
    skill_id = candidate.skill_id.lower()

    curated_match = any(
        (
            skill_id == marker
            or skill_id.startswith(marker)
            or marker in skill_id
            or marker in candidate.source.lower()
        )
        for marker in WORLD_CLASS_WEB_MARKERS
    )
    if curated_match:
        boost += 7.0

    stack_overlap = skill_tokens & _tokenize(" ".join(project.frameworks + project.languages))
    workflow_overlap = skill_tokens & _tokenize(" ".join(project.workflows))
    if stack_overlap:
        boost += min(4.0, len(stack_overlap) * 1.2)
    if workflow_overlap:
        boost += min(4.0, len(workflow_overlap) * 1.0)

    quality_tokens = skill_tokens & WORLD_CLASS_QUALITY_TOKENS
    if quality_tokens:
        boost += min(3.0, len(quality_tokens) * 0.8)

    return min(boost, 15.0)


def score_relevance_penalty(
    project: ProjectSummary,
    skill_tokens: set[str],
    overlap: set[str],
    framework_overlap: set[str],
    workflow_overlap: set[str],
    profile_tokens: set[str],
) -> float:
    penalty = 0.0
    if project.frameworks and not framework_overlap and not workflow_overlap:
        penalty += 6.0
    if len(overlap) <= 1:
        penalty += 3.0
    if (skill_tokens & OFF_DOMAIN_TOKENS) and not (skill_tokens & profile_tokens):
        penalty += 10.0
    return min(penalty, 18.0)


def apply_overlap_penalties(ranked: list[SkillCandidate]) -> None:
    chosen: list[SkillCandidate] = []
    for candidate in ranked:
        candidate_tokens = _tokenize(
            " ".join([candidate.name, candidate.skill_id, candidate.summary, candidate.repo_description])
        )
        best_overlap = 0.0
        for other in chosen[:8]:
            other_tokens = _tokenize(
                " ".join([other.name, other.skill_id, other.summary, other.repo_description])
            )
            union = candidate_tokens | other_tokens
            overlap = len(candidate_tokens & other_tokens) / max(1, len(union))
            best_overlap = max(best_overlap, overlap)
            if overlap >= 0.55:
                candidate.conflict_penalty = max(candidate.conflict_penalty, 12.0)
                candidate.warnings.append(f"High overlap with {other.source}/{other.skill_id}.")
            elif overlap >= 0.35:
                candidate.overlap_penalty = max(candidate.overlap_penalty, 8.0)
        candidate.score = round(
            candidate.score - candidate.overlap_penalty - candidate.conflict_penalty,
            2,
        )
        if candidate.score > 0:
            chosen.append(candidate)


def recommend_custom_skills(project: ProjectSummary) -> list[dict[str, str]]:
    suggestions: list[dict[str, str]] = []
    if project.missing_areas:
        suggestions.append(
            {
                "name": "repo-onboarding",
                "why": "This repo is missing or thin on documented conventions. A custom onboarding skill can encode project-specific setup, commands, and review expectations.",
            }
        )
    if "ci-pipeline" in project.missing_areas:
        suggestions.append(
            {
                "name": "release-and-ci-guardrails",
                "why": "A repo-specific CI/release skill can capture required checks, deploy steps, and failure triage procedures that generic marketplace skills cannot know.",
            }
        )
    if project.frameworks and len(project.frameworks) >= 2:
        suggestions.append(
            {
                "name": "stack-integration-playbook",
                "why": "A custom skill can encode how this exact stack is wired together and where changes usually belong.",
            }
        )
    return suggestions[:3]


def methodology_note() -> str:
    return (
        "Local signals come from repo structure, README/docs, manifests, and config files. "
        "Live marketplace signals come from skills.sh catalog pages and individual skill pages. "
        "Popularity uses live install counts from skills.sh. Freshness and part of quality are enriched from the source GitHub repo when available. "
        "If a signal is unavailable, the report marks it as inferred or unavailable instead of treating it as exact."
    )


def render_report(project: ProjectSummary, candidates: list[SkillCandidate], top_n: int = 6) -> str:
    install_now = apply_source_diversity(
        [c for c in candidates if c.bucket == "install-now"],
        limit=top_n,
        per_source=2,
    )
    optional_later = apply_source_diversity(
        [c for c in candidates if c.bucket == "optional-later"],
        limit=top_n,
        per_source=2,
    )
    warnings = sorted({warning for c in candidates for warning in c.warnings})
    custom_skills = recommend_custom_skills(project)

    lines = [
        "# Skillscan Report",
        "",
        "## Project Summary",
        project.synopsis,
        "",
        "## Detected Stack",
        f"- Languages: {', '.join(project.languages) or 'None detected'}",
        f"- Frameworks: {', '.join(project.frameworks) or 'None detected'}",
        f"- Package managers: {', '.join(project.package_managers) or 'None detected'}",
        f"- Workflows: {', '.join(project.workflows) or 'None detected'}",
        f"- Missing areas: {', '.join(project.missing_areas) or 'No major gaps detected'}",
        "",
        "## Best Skills To Install Now",
    ]

    if install_now:
        for candidate in install_now:
            lines.extend(format_candidate(candidate))
    else:
        lines.append("- No strong install-now matches found.")

    lines.extend(["", "## Optional Skills For Later"])
    if optional_later:
        for candidate in optional_later:
            lines.extend(format_candidate(candidate))
    else:
        lines.append("- No optional-later matches found.")

    lines.extend(["", "## Custom Skills To Create For This Repo"])
    if custom_skills:
        for skill in custom_skills:
            lines.append(f"- `{skill['name']}`: {skill['why']}")
    else:
        lines.append("- No custom-skill suggestions.")

    lines.extend(["", "## Duplicate Or Conflicting Skill Warnings"])
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- No high-confidence conflicts detected.")

    lines.extend(["", "## Install Commands"])
    commands = []
    for candidate in install_now + optional_later:
        commands.append(resolve_install_command(candidate))
    for command in dict.fromkeys(commands):
        lines.append(f"- `{command}`")

    lines.extend(["", "## Methodology", methodology_note()])
    return "\n".join(lines).strip() + "\n"


def format_candidate(candidate: SkillCandidate) -> list[str]:
    lines = [
        f"- `{candidate.skill_id}` from `{candidate.source}`",
        f"  Score: {candidate.score:.2f} | fit {candidate.repo_fit:.1f} | quality {candidate.quality:.1f} | popularity {candidate.popularity:.1f} | freshness {candidate.freshness:.1f}",
    ]
    if candidate.why:
        lines.append("  Why: " + " | ".join(candidate.why[:3]))
    if candidate.warnings:
        lines.append("  Warning: " + " | ".join(candidate.warnings[:2]))
    command = resolve_install_command(candidate)
    lines.append(f"  Install: `{command}`")
    return lines


def resolve_install_command(candidate: SkillCandidate) -> str:
    command = (candidate.install_command or "").strip()
    if command:
        return command
    if candidate.source.startswith("http://") or candidate.source.startswith("https://"):
        source = candidate.source
    else:
        source = f"https://github.com/{candidate.source}"
    return f"npx skills add {source} --skill {candidate.skill_id}"


def apply_source_diversity(candidates: list[SkillCandidate], limit: int, per_source: int) -> list[SkillCandidate]:
    selected: list[SkillCandidate] = []
    source_count: dict[str, int] = {}
    for candidate in candidates:
        count = source_count.get(candidate.source, 0)
        if count >= per_source:
            continue
        selected.append(candidate)
        source_count[candidate.source] = count + 1
        if len(selected) >= limit:
            break
    return selected


def shortlist_candidates(
    project: ProjectSummary,
    catalog: list[SkillCandidate],
    limit: int = 24,
    include_nonmatching: bool = False,
) -> list[SkillCandidate]:
    project_tokens = set(project.signal_keywords or project.keywords)
    scored = []
    for candidate in catalog:
        text = " ".join([candidate.skill_id, candidate.name, candidate.source.replace("/", " ")])
        tokens = _tokenize(text)
        match_count = len(project_tokens & tokens)
        if match_count == 0 and project.frameworks and not include_nonmatching:
            continue
        priority = (match_count * 2) + math.log(candidate.installs + 1, 10)
        scored.append((priority, candidate))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [candidate for _, candidate in scored[:limit]]


def run(project_root: Path, top_n: int) -> dict:
    project = scan_project(project_root)
    homepage = fetch_url(HOMEPAGE_URL)
    catalog = extract_catalog(homepage)
    if not catalog:
        raise RuntimeError("No skills could be extracted from skills.sh.")

    shortlist_limit = max(40, min(120, top_n * 2))
    include_nonmatching = top_n >= 50
    shortlisted = shortlist_candidates(
        project,
        catalog,
        limit=shortlist_limit,
        include_nonmatching=include_nonmatching,
    )
    enrich_limit = min(len(shortlisted), 20)
    for candidate in shortlisted[:enrich_limit]:
        enrich_candidate(candidate)

    ranked = rank_candidates(project, shortlisted, top_n=top_n)
    return {
        "project": asdict(project),
        "recommendations": [asdict(candidate) for candidate in ranked],
        "report": render_report(project, ranked, top_n=top_n),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan a project and recommend skills from skills.sh.")
    parser.add_argument("--project", default=".", help="Path to the project to scan.")
    parser.add_argument("--top", type=int, default=6, help="Number of top recommendations per bucket.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    result = run(Path(args.project).resolve(), top_n=max(args.top, 1))
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(result["report"])
    return 0


STOP_WORDS = {
    "a",
    "all",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "do",
    "for",
    "has",
    "have",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "the",
    "their",
    "to",
    "which",
    "you",
    "with",
    "from",
    "that",
    "this",
    "your",
    "into",
    "then",
    "them",
    "when",
    "uses",
    "using",
    "used",
    "repo",
    "skill",
    "skills",
    "project",
    "codebase",
}

IGNORE_DIRS = {
    ".agents",
    ".git",
    "node_modules",
    ".next",
    ".turbo",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".venv",
    "venv",
}

IMPORTANT_FILES = {
    ".env.example",
    ".env.sample",
    "package.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "package-lock.json",
    "pyproject.toml",
    "poetry.lock",
    "requirements.txt",
    "cargo.toml",
    "go.mod",
    "pom.xml",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "tsconfig.json",
    "eslint.config.js",
    ".eslintrc",
    ".prettierrc",
    "vitest.config.ts",
    "vite.config.ts",
    "next.config.js",
    "next.config.mjs",
    "jest.config.js",
    "playwright.config.ts",
}

SUFFIX_LANGUAGE_MAP = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
}

FILE_SIGNAL_MAP = {
    "dockerfile": {"workflows": {"containers"}},
    "docker-compose.yml": {"workflows": {"containers"}},
    "docker-compose.yaml": {"workflows": {"containers"}},
    "tsconfig.json": {"workflows": {"type-checking"}, "frameworks": {"TypeScript"}},
    "eslint.config.js": {"workflows": {"linting"}},
    ".eslintrc": {"workflows": {"linting"}},
    "playwright.config.ts": {"workflows": {"e2e-testing"}},
    "vitest.config.ts": {"workflows": {"testing"}},
    "jest.config.js": {"workflows": {"testing"}},
}

DEP_FRAMEWORK_MAP = {
    "next": {"Next.js", "React"},
    "react": {"React"},
    "vue": {"Vue"},
    "nuxt": {"Nuxt"},
    "svelte": {"Svelte"},
    "@angular/core": {"Angular"},
    "express": {"Express"},
    "fastify": {"Fastify"},
    "nestjs": {"NestJS"},
    "django": {"Django"},
    "flask": {"Flask"},
    "vite": {"Vite"},
    "vitest": {"Vitest"},
    "playwright": {"Playwright"},
    "cypress": {"Cypress"},
    "tailwindcss": {"Tailwind CSS"},
    "prisma": {"Prisma"},
    "drizzle-orm": {"Drizzle ORM"},
    "storybook": {"Storybook"},
}

WORLD_CLASS_WEB_MARKERS = {
    "next-best-practices",
    "vercel-react-best-practices",
    "web-design-guidelines",
    "vercel-composition-patterns",
    "systematic-debugging",
    "test-driven-development",
    "requesting-code-review",
    "executing-plans",
    "writing-plans",
    "webapp-testing",
    "playwright",
    "vitest",
    "shadcn",
    "security-best-practices",
    "audit-website",
}

WORLD_CLASS_QUALITY_TOKENS = {
    "testing",
    "test",
    "debugging",
    "review",
    "performance",
    "security",
    "accessibility",
    "ci",
    "type",
    "typescript",
    "playwright",
    "vitest",
    "next",
    "react",
    "web",
}

OFF_DOMAIN_TOKENS = {
    "azure",
    "entra",
    "kusto",
    "cosmosdb",
    "dataverse",
    "fabric",
    "powerbi",
    "lakehouse",
    "copilot-studio",
}


if __name__ == "__main__":
    raise SystemExit(main())
