# skillscan

`skillscan` is a single-skill repository for the open agent skills ecosystem.

It inspects a software project, reads important files such as `README`, `docs`, manifests, configs, CI, and repo structure, then visits `skills.sh` live to recommend the best skill stack for that project.

## Install

If this repository is published at `subhajitlucky/skillscan`, the install command is:

```bash
npx skills add subhajitlucky/skillscan
```

That works because the `skills` CLI discovers a skill from the repository root when the root contains a valid `SKILL.md`.

## What The Skill Does

After installation, an agent using `skillscan` should:

1. Scan the current project deeply.
2. Read high-signal files such as `README*`, `docs/**`, `package.json`, lockfiles, CI configs, Docker files, test configs, lint configs, and framework configs.
3. Infer the stack, workflows, and missing areas.
4. Visit `skills.sh` live.
5. Rank candidate skills by repo fit, quality, popularity, freshness, and overlap.
6. Output a clean report with:
   - best skills to install now
   - optional skills for later
   - custom skills to create for the repo
   - duplicate or conflicting skill warnings
   - install commands

## Local Development

Run the scanner against the current repo:

```bash
python3 scripts/skillscan.py --project "$PWD"
```

Run tests:

```bash
python3 -m unittest discover -s tests -v
```

Validate the skill metadata:

```bash
python3 /home/subhajit/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```

## Publish Checklist

- Push this repo to a public GitHub repository.
- Keep `SKILL.md` at the repository root.
- Keep `README.md` at the repository root.
- Set the GitHub repo description so the listing is clearer on GitHub and in external references.
- Share the install command `npx skills add subhajitlucky/skillscan`.

According to the current `skills.sh` FAQ, skills appear on the leaderboard automatically through anonymous install telemetry when users run `npx skills add <owner/repo>`.
