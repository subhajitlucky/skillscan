# Skillscan Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a reusable skill that scans a project, researches skills.sh live, ranks candidate skills, and emits an install-ready recommendation report.

**Architecture:** Use one standard-library Python entrypoint that performs a local repo scan, extracts the live skills.sh catalog, enriches shortlisted candidates from skill pages and GitHub metadata, then renders Markdown or JSON output. Keep the skill self-contained so it works on a fresh machine with only `python3`.

**Tech Stack:** Markdown skill metadata, Python 3 standard library, unittest

---

### Task 1: Scaffold the skill files

**Files:**
- Create: `SKILL.md`
- Create: `agents/openai.yaml`
- Create: `references/scoring.md`

### Task 2: Build the local repo scanner

**Files:**
- Create: `scripts/skillscan.py`
- Test: `tests/test_skillscan.py`

### Task 3: Build the live marketplace collector

**Files:**
- Modify: `scripts/skillscan.py`
- Test: `tests/test_skillscan.py`

### Task 4: Add scoring, report rendering, and warnings

**Files:**
- Modify: `scripts/skillscan.py`
- Test: `tests/test_skillscan.py`

### Task 5: Validate and verify

**Files:**
- Modify: `scripts/skillscan.py`
- Test: `tests/test_skillscan.py`
