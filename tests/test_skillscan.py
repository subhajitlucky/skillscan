from __future__ import annotations

import importlib.util
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "skillscan.py"
SPEC = importlib.util.spec_from_file_location("skillscan_module", MODULE_PATH)
skillscan = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = skillscan
SPEC.loader.exec_module(skillscan)


class SkillscanTests(unittest.TestCase):
    def test_extract_catalog_from_embedded_homepage_payload(self) -> None:
        html = r"""
        <script>self.__next_f.push([1,"{\"source\":\"wshobson/agents\",\"skillId\":\"security-requirement-extraction\",\"name\":\"security-requirement-extraction\",\"installs\":7471},{\"source\":\"vercel-labs/agent-skills\",\"skillId\":\"next-best-practices\",\"name\":\"next-best-practices\",\"installs\":9800}]"])</script>
        """
        candidates = skillscan.extract_catalog(html)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].source, "wshobson/agents")
        self.assertEqual(candidates[1].installs, 9800)

    def test_scan_project_detects_stack_and_missing_areas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Demo\nA Next app\n", encoding="utf-8")
            (root / "package.json").write_text(
                textwrap.dedent(
                    """
                    {
                      "description": "Next app",
                      "dependencies": {
                        "next": "15.0.0",
                        "react": "19.0.0",
                        "typescript": "5.0.0"
                      },
                      "devDependencies": {
                        "eslint": "9.0.0",
                        "playwright": "1.0.0"
                      },
                      "scripts": {
                        "dev": "next dev",
                        "lint": "eslint .",
                        "test:e2e": "playwright test"
                      }
                    }
                    """
                ).strip(),
                encoding="utf-8",
            )
            (root / "tsconfig.json").write_text("{}", encoding="utf-8")
            summary = skillscan.scan_project(root)
            self.assertIn("Next.js", summary.frameworks)
            self.assertIn("React", summary.frameworks)
            self.assertIn("testing", summary.workflows)
            self.assertIn("linting", summary.workflows)
            self.assertIn("project-docs", summary.missing_areas)

    def test_render_report_includes_install_command(self) -> None:
        project = skillscan.ProjectSummary(
            root="/tmp/demo",
            files_scanned=[],
            docs_read=[],
            structure_sample=[],
            languages=["TypeScript"],
            frameworks=["Next.js"],
            package_managers=["npm"],
            workflows=["testing"],
            important_files=["package.json"],
            missing_areas=["ci-pipeline"],
            keywords=["next", "testing"],
            synopsis="Demo project.",
        )
        candidate = skillscan.SkillCandidate(
            source="vercel-labs/agent-skills",
            skill_id="next-best-practices",
            name="next-best-practices",
            installs=1000,
            install_command="npx skills add https://github.com/vercel-labs/agent-skills --skill next-best-practices",
            summary="Useful for Next.js apps.",
            score=80,
            repo_fit=90,
            quality=70,
            popularity=60,
            freshness=80,
            bucket="install-now",
            why=["Matches Next.js"],
        )
        report = skillscan.render_report(project, [candidate])
        self.assertIn("Best Skills To Install Now", report)
        self.assertIn("next-best-practices", report)
        self.assertIn("npx skills add https://github.com/vercel-labs/agent-skills --skill next-best-practices", report)


if __name__ == "__main__":
    unittest.main()
