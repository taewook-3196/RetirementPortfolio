"""Mock the actual watchdog script without touching production GitHub Issues."""

import shutil
import subprocess
from pathlib import Path

import pytest

WATCHDOG = Path(__file__).resolve().parents[1] / ".github/workflows/morning_report_missing_run_watchdog.yml"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_watchdog_missing_run_issue_lifecycle(tmp_path):
    source = WATCHDOG.read_text(encoding="utf-8")
    script = source.split("          script: |\n", 1)[1]
    script = "\n".join(line[12:] for line in script.splitlines())
    script_path = tmp_path / "watchdog.js"
    script_path.write_text(script, encoding="utf-8")

    harness = r"""
const fs = require('node:fs');
const assert = require('node:assert/strict');
const script = fs.readFileSync(process.argv[2], 'utf8');
const execute = new Function('context', 'github', 'core', 'return (async () => {\n' + script + '\n})()');
const issues = [], comments = [], runs = [];
const github = {
  paginate: async (fn) => fn === github.rest.issues.listForRepo
    ? issues.filter(i => i.state === 'open') : runs,
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
    actions: {listWorkflowRuns: () => {}},
  },
};
const context = {repo: {owner: 'example', repo: 'repo'}};
const core = {info: () => {}};
(async () => {
  const dateKey = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new FixedDate());
  const weekday = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Seoul', weekday: 'short',
  }).format(new Date());
  const hour = Number(new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Seoul', hour: '2-digit', hourCycle: 'h23',
  }).format(new Date()));
  const minute = Number(new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Seoul', minute: '2-digit',
  }).format(new Date()));
  if (['Sun','Mon'].includes(weekday) || hour * 60 + minute < 690) {
    process.stdout.write('Skipped: test only runs after cutoff on KST Tue-Sat\n');
    return;
  }
  await execute(context, github, core, FixedDate);
  assert.equal(issues.length, 1, 'missing schedule creates issue');
  await execute(context, github, core);
  assert.equal(issues.length, 1, 'repeat check does not duplicate issue');
  assert.equal(comments.length, 0);
  runs.push({created_at: new FixedDate().toISOString(), event: 'schedule',
    html_url: 'https://github.com/example/repo/actions/runs/1'});
  await execute(context, github, core);
  assert.equal(issues[0].state, 'closed', 'scheduled run closes alert');
  assert.equal(comments.length, 1);
  process.stdout.write('watchdog mock scenarios passed\n');
})().catch(e => {console.error(e); process.exitCode = 1});
"""
    harness_file = tmp_path / "harness.cjs"
    harness_file.write_text(harness, encoding="utf-8")
    result = subprocess.run(
        ["node", str(harness_file), str(script_path)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
