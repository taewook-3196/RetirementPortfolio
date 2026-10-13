"""Exercise the workflow's actual github-script body with mocked GitHub APIs."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/morning_report_run_monitor.yml"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_monitor_failure_dedup_recovery_and_stale_events(tmp_path):
    workflow = WORKFLOW.read_text(encoding="utf-8")
    script = workflow.split("          script: |\n", 1)[1]
    script = "\n".join(line[12:] for line in script.splitlines())
    script_file = tmp_path / "monitor.js"
    script_file.write_text(script, encoding="utf-8")

    harness = r"""
const fs = require('node:fs');
const assert = require('node:assert/strict');
const script = fs.readFileSync(process.argv[2], 'utf8');
const execute = new Function('context', 'github', 'core', 'return (async () => {\n' + script + '\n})()');
const issues = [];
const comments = [];
const runs = [];
const github = {
  paginate: async () => issues.filter(i => i.state === 'open'),
  rest: {
    issues: {
      listForRepo: () => {},
      create: async ({title, body}) => {
        issues.push({number: issues.length + 1, title, body, state: 'open'});
      },
      update: async ({issue_number, ...changes}) => {
        Object.assign(issues.find(i => i.number === issue_number), changes);
      },
      createComment: async ({issue_number, body}) => comments.push({issue_number, body}),
    },
    actions: {
      listWorkflowRuns: async () => ({data: {workflow_runs: runs}}),
    },
  },
};
const core = {info: () => {}};
async function event(run_number, conclusion) {
  const run = {id: run_number, run_number, workflow_id: 123, conclusion,
    html_url: 'https://github.com/example/repo/actions/runs/' + run_number};
  await execute({repo: {owner: 'example', repo: 'repo'}, payload: {workflow_run: run}}, github, core);
}
(async () => {
  await event(10, 'failure');
  assert.equal(issues.length, 1);
  assert.equal(issues[0].state, 'open');
  await event(10, 'failure');
  assert.equal(comments.length, 0, 'duplicate failure must not comment');
  await event(11, 'failure');
  assert.equal(issues.length, 1);
  assert.equal(comments.length, 1);
  await event(9, 'success');
  assert.equal(issues[0].state, 'open', 'older success must not close issue');
  await event(12, 'success');
  assert.equal(issues[0].state, 'closed');
  await event(13, 'failure');
  assert.equal(issues.length, 2, 'new failure after recovery opens new issue');
  runs.push({id: 15, run_number: 15});
  await event(14, 'success');
  assert.equal(issues[1].state, 'open', 'stale success must not close latest alert');
  process.stdout.write('monitor mock scenarios passed\n');
})().catch(e => {console.error(e); process.exitCode = 1});
"""
    harness_file = tmp_path / "harness.cjs"
    harness_file.write_text(harness, encoding="utf-8")
    result = subprocess.run(
        ["node", str(harness_file), str(script_file)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
