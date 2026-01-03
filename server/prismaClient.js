const { PrismaClient } = require('@prisma/client');

const prisma = new PrismaClient();

function serializeWorkflowPayload(data) {
  const out = { ...data };
  if (out.triggerConfig && typeof out.triggerConfig !== 'string') {
    out.triggerConfig = JSON.stringify(out.triggerConfig);
  }
  if (out.steps && typeof out.steps !== 'string') {
    out.steps = JSON.stringify(out.steps);
  }
  return out;
}

function deserializeWorkflow(workflow) {
  if (!workflow) return workflow;
  const out = { ...workflow };
  if (out.triggerConfig && typeof out.triggerConfig === 'string') {
    try { out.triggerConfig = JSON.parse(out.triggerConfig); } catch (e) { /* leave as string */ }
  }
  if (out.steps && typeof out.steps === 'string') {
    try { out.steps = JSON.parse(out.steps); } catch (e) { /* leave as string */ }
  }
  return out;
}

module.exports = { prisma, serializeWorkflowPayload, deserializeWorkflow };
