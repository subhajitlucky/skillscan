---
name: skillscan
description: Scan an entire software project, inspect important files such as README files, docs, package manifests, configs, CI, and repo structure, then visit skills.sh live to recommend the best skill stack for that repo. Use when Codex needs to understand a codebase quickly, identify setup gaps, rank marketplace skills by repo fit, quality, popularity, freshness, and overlap, and produce a report with install-now skills, optional-later skills, custom-skill suggestions, conflict warnings, and install commands.
---

# Skillscan

Inspect the current project first, then research the live marketplace, then produce a recommendation report.

## Default Behavior

- Treat the current working directory as the project to scan unless the user points to another path.
- Prefer running:

```bash
python3 scripts/skillscan.py --project "$PWD"
```

- If the user asks for structured output or wants to feed results into another tool, run with `--json`.
- If `skills.sh` or GitHub metadata cannot be reached, continue with the local repo scan and say clearly which marketplace signals were unavailable.

## Run

From the skill directory, run:

```bash
python3 scripts/skillscan.py --project /absolute/path/to/project
```

Use `--top 8` to change how many recommendations are shown and `--json` if a downstream tool needs structured output.

## Workflow

1. Scan the target repo deeply.
2. Read important files when present:
   - `README*`
   - `docs/**`
   - `package.json`, lockfiles, `pyproject.toml`, `Cargo.toml`, `go.mod`, `pom.xml`
   - framework, test, lint, typecheck, Docker, CI, and infra configs
3. Infer:
   - languages and frameworks
   - package manager and build tooling
   - testing, linting, typing, CI, container, and deployment workflows
   - obvious missing areas
4. Visit `skills.sh` live and collect candidate skills.
5. Enrich shortlisted candidates with skill-page summaries and GitHub repo metadata when available.
6. Rank candidates by:
   - repo fit
   - quality
   - popularity
   - freshness
   - overlap/conflict penalties
7. Return a clean report with:
   - best skills to install now
   - optional skills for later
   - custom skills to create for this repo
   - why each choice was made
   - duplicate/conflicting skill warnings
   - install commands

## Output Requirements

Always include:

- a short project summary
- detected stack and workflows
- missing areas or weak spots
- a methodology note stating which marketplace signals were available live and which were inferred

If marketplace data is partial, say so explicitly instead of implying false precision.

## What To Say

Keep the output decision-oriented:

- summarize the repo in a few lines
- recommend a small install-now set rather than a long list
- explain why each recommendation fits this repo now
- separate future or lower-confidence ideas into the optional section
- warn about duplicate or competing skills before suggesting both

## Heuristics

- Prefer skills whose name, summary, and source align with the detected stack and workflows.
- Penalize near-duplicates so the install-now list stays small and usable.
- Treat freshness as a weaker signal than repo fit.
- Suggest custom skills when the repo has team-specific workflows or gaps that generic marketplace skills are unlikely to cover.
