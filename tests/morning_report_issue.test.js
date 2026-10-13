"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {
  ALERT_TITLE,
  handleFailure,
  handleRecovery,
} = require("../scripts/morning_report_issue.js");

function fixture(openIssues = []) {
  const calls = { create: [], comment: [], update: [], paginate: 0 };
  const github = {
    paginate: async () => {
      calls.paginate += 1;
      return openIssues;
    },
    rest: {
      issues: {
        listForRepo: async () => {
          throw new Error("paginate must be used");
        },
        create: async (input) => calls.create.push(input),
        createComment: async (input) => calls.comment.push(input),
        update: async (input) => calls.update.push(input),
      },
    },
  };
  const context = {
    repo: { owner: "owner", repo: "repo" },
    serverUrl: "https://github.com",
    runId: 123,
  };
  return { github, context, calls };
}

test("failure creates one alert when none is open", async () => {
  const { github, context, calls } = fixture();
  await handleFailure({
    github,
    context,
    now: new Date("2026-10-13T00:00:00Z"),
  });

  assert.equal(calls.paginate, 1);
  assert.equal(calls.create.length, 1);
  assert.equal(calls.create[0].title, ALERT_TITLE);
  assert.equal(calls.comment.length, 0);
});

test("repeated failure comments on the existing alert instead of creating one", async () => {
  const { github, context, calls } = fixture([
    { number: 7, title: ALERT_TITLE },
    { number: 8, title: "unrelated" },
    { number: 9, title: ALERT_TITLE, pull_request: {} },
  ]);
  await handleFailure({ github, context });

  assert.equal(calls.create.length, 0);
  assert.equal(calls.comment.length, 1);
  assert.equal(calls.comment[0].issue_number, 7);
  assert.equal(calls.update.length, 0);
});

test("failure keeps one alert and closes historical duplicates", async () => {
  const { github, context, calls } = fixture([
    { number: 7, title: ALERT_TITLE },
    { number: 11, title: ALERT_TITLE },
  ]);
  await handleFailure({ github, context });

  assert.equal(calls.comment[0].issue_number, 7);
  assert.deepEqual(calls.update, [{
    owner: "owner",
    repo: "repo",
    issue_number: 11,
    state: "closed",
    state_reason: "not_planned",
  }]);
});

test("recovery comments on and closes every open alert", async () => {
  const { github, context, calls } = fixture([
    { number: 7, title: ALERT_TITLE },
    { number: 11, title: ALERT_TITLE },
  ]);
  await handleRecovery({ github, context });

  assert.deepEqual(calls.comment.map((call) => call.issue_number), [7, 11]);
  assert.deepEqual(calls.update.map((call) => [call.issue_number, call.state_reason]), [
    [7, "completed"],
    [11, "completed"],
  ]);
});

test("successful check with no alert performs no mutations", async () => {
  const { github, context, calls } = fixture();
  await handleRecovery({ github, context });

  assert.equal(calls.create.length, 0);
  assert.equal(calls.comment.length, 0);
  assert.equal(calls.update.length, 0);
});
