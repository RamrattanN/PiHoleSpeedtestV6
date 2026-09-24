import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLISH_WORKFLOW = ROOT / ".github" / "workflows" / "publish.yml"


class DockerDeferralTests(unittest.TestCase):
    def test_release_event_cannot_publish_docker_image(self):
        workflow = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
        trigger = workflow.split("\non:", 1)[1].split("\nenv:", 1)[0]
        events = re.findall(r"^  ([a-z_]+):", trigger, flags=re.MULTILINE)

        self.assertEqual(events, ["workflow_dispatch"])
        self.assertNotRegex(workflow, r"(?m)^\s*release:")
        self.assertIn(
            "if: github.event_name == 'workflow_dispatch' && "
            "inputs.confirm == 'PUBLISH EXPERIMENTAL IMAGE'",
            workflow,
        )
        self.assertIn("EXPERIMENTAL", workflow)

    def test_no_workflow_runs_when_a_github_release_is_published(self):
        workflows = sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))

        self.assertTrue(workflows)
        for path in workflows:
            with self.subTest(workflow=path.name):
                text = path.read_text(encoding="utf-8")
                trigger = text.split("\non:", 1)[1].split("\njobs:", 1)[0]
                self.assertNotRegex(trigger, r"(?m)^\s*release\s*:")
                self.assertNotRegex(trigger, r"(?m)^\s*-?\s*release\s*$")
                self.assertNotRegex(trigger, r"\[[^\]]*\brelease\b[^\]]*\]")


if __name__ == "__main__":
    unittest.main()
