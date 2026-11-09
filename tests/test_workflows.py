"""Every GitHub workflow file must parse: an invalid one fails silently on schedule."""

from pathlib import Path

import pytest
import yaml

WORKFLOWS = sorted((Path(__file__).resolve().parents[1] / ".github" / "workflows").glob("*.yml"))


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_parses_with_named_steps(path):
    wf = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert wf.get("jobs"), f"{path.name} has no jobs"
    for job in wf["jobs"].values():
        for step in job["steps"]:
            assert isinstance(step, dict) and ("run" in step or "uses" in step)
