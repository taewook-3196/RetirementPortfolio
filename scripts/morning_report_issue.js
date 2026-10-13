"use strict";

const ALERT_TITLE = "[자동 감시] Morning Report 점검 실패";

async function findOpenAlerts({ github, context }) {
  const issues = await github.paginate(github.rest.issues.listForRepo, {
    owner: context.repo.owner,
    repo: context.repo.repo,
    state: "open",
    per_page: 100,
  });
  return issues.filter(
    (issue) => !issue.pull_request && issue.title === ALERT_TITLE,
  );
}

function workflowRunUrl(context) {
  return `${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;
}

async function handleFailure({ github, context, now = new Date() }) {
  const alerts = await findOpenAlerts({ github, context });
  const body = [
    "배포된 Morning Report 자동 점검에 실패했습니다.",
    "",
    `- 확인 시각(UTC): ${now.toISOString()}`,
    `- Workflow run: ${workflowRunUrl(context)}`,
    "",
    "실패 원인은 workflow 로그에서 확인해 주세요.",
  ].join("\n");

  if (alerts.length === 0) {
    return github.rest.issues.create({
      owner: context.repo.owner,
      repo: context.repo.repo,
      title: ALERT_TITLE,
      body,
    });
  }

  const [primary, ...duplicates] = alerts;
  await github.rest.issues.createComment({
    owner: context.repo.owner,
    repo: context.repo.repo,
    issue_number: primary.number,
    body,
  });
  for (const duplicate of duplicates) {
    await github.rest.issues.update({
      owner: context.repo.owner,
      repo: context.repo.repo,
      issue_number: duplicate.number,
      state: "closed",
      state_reason: "not_planned",
    });
  }
}

async function handleRecovery({ github, context }) {
  const alerts = await findOpenAlerts({ github, context });
  const body = [
    "Morning Report 자동 점검이 복구되었습니다.",
    "",
    `- Workflow run: ${workflowRunUrl(context)}`,
  ].join("\n");

  for (const issue of alerts) {
    await github.rest.issues.createComment({
      owner: context.repo.owner,
      repo: context.repo.repo,
      issue_number: issue.number,
      body,
    });
    await github.rest.issues.update({
      owner: context.repo.owner,
      repo: context.repo.repo,
      issue_number: issue.number,
      state: "closed",
      state_reason: "completed",
    });
  }
}

module.exports = {
  ALERT_TITLE,
  findOpenAlerts,
  handleFailure,
  handleRecovery,
};
