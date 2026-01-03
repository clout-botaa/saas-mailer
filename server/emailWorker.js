const { Worker, Queue } = require('bullmq');
const IORedis = require('ioredis');
const { PrismaClient } = require('@prisma/client');

const prisma = new PrismaClient();
const connection = new IORedis(process.env.REDIS_URL || 'redis://127.0.0.1:6379');
const queue = new Queue('emailQueue', { connection });

// Placeholder: implement real Gmail API sending using user's refresh token
async function sendEmailViaGmail(user, lead, html, attachments) {
  // In a production implementation, exchange refresh token for access token
  // then call Gmail API to send the message. Here we simulate possible limit errors.
  if (process.env.SIMULATE_LIMIT === '1') {
    // artificially trigger a limit error for testing
    const e = new Error('Daily Limit Exceeded');
    e.code = 403;
    throw e;
  }
  // Simulate success
  return { ok: true };
}

const { google } = require('googleapis');

function makeRawMessage({ to, from, subject, html }) {
  const boundary = '----=_boundary_' + Date.now();
  const messageParts = [];
  messageParts.push(`From: ${from}`);
  messageParts.push(`To: ${to}`);
  messageParts.push(`Subject: ${subject}`);
  messageParts.push('MIME-Version: 1.0');
  messageParts.push(`Content-Type: multipart/alternative; boundary="${boundary}"`);
  messageParts.push('');
  messageParts.push(`--${boundary}`);
  messageParts.push('Content-Type: text/html; charset=UTF-8');
  messageParts.push('Content-Transfer-Encoding: 7bit');
  messageParts.push('');
  messageParts.push(html);
  messageParts.push(`--${boundary}--`);
  const raw = messageParts.join('\r\n');
  return Buffer.from(raw)
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

async function sendReportEmail(user, subject, body) {
  // Send a short report to the user (stub). Replace with real send logic.
  console.log(`REPORT -> ${user.email}: ${subject} - ${body}`);
}

async function pruneCampaignLogs(userId) {
  // Keep logs only for the 4 most recent campaigns of the user; delete older campaign logs
  const oldCampaigns = await prisma.campaign.findMany({
    where: { userId },
    orderBy: { createdAt: 'desc' },
    skip: 4 // campaigns after the first 4
  });
  const ids = oldCampaigns.map(c => c.id);
  if (ids.length) {
    await prisma.log.deleteMany({ where: { campaignId: { in: ids } } });
  }
}

const worker = new Worker('emailQueue', async job => {
  const { campaignId, leads, templateHtml, attachments } = job.data;
  const campaign = await prisma.campaign.findUnique({ where: { id: campaignId } });
  if (!campaign) throw new Error('Campaign not found: ' + campaignId);
  const user = await prisma.user.findUnique({ where: { id: campaign.userId } });
  if (!user) throw new Error('User not found for campaign: ' + campaignId);

  for (let i = 0; i < leads.length; i++) {
    const lead = leads[i];
    try {
      await sendEmailViaGmail(user, lead, templateHtml, attachments);
      await prisma.campaign.update({
        where: { id: campaignId },
        data: { sentCount: { increment: 1 } }
      });
      await prisma.log.create({ data: { campaignId, status: 'SENT', message: `Sent to ${lead.email}` } });
    } catch (err) {
      // Limit handling: Gmail Daily Limit Exceeded
      if (err && (err.code === 403 || (err.message && err.message.includes('Daily Limit')))) {
        const remaining = leads.slice(i);
        // Pause campaign and add delayed job for remainder (24h)
        const resumeAt = Date.now() + 24 * 60 * 60 * 1000;
        await prisma.campaign.update({ where: { id: campaignId }, data: { status: 'PAUSED' } });
        await queue.add('emailJob', { campaignId, leads: remaining, templateHtml, attachments }, { delay: 24 * 60 * 60 * 1000 });
        await prisma.log.create({ data: { campaignId, status: 'PAUSED', message: 'Daily limit hit — campaign paused and rescheduled' } });
        await sendReportEmail(user, 'Daily Limit Reached — Campaign Paused', `Paused. Will resume at ${new Date(resumeAt).toISOString()}`);
        return; // stop processing this job
      }
      // log transient error for this lead and continue
      await prisma.log.create({ data: { campaignId, status: 'FAILED', message: `Failed for ${lead.email}: ${err.message || err}` } });
    }
  }

  // All leads processed successfully
  await prisma.campaign.update({ where: { id: campaignId }, data: { status: 'COMPLETED' } });
  await prisma.log.create({ data: { campaignId, status: 'COMPLETED', message: `Campaign ${campaignId} completed` } });
  await sendReportEmail(user, 'Campaign Completed', `Campaign ${campaignId} completed successfully.`);
  await pruneCampaignLogs(user.id);
}, { connection });

worker.on('failed', (job, err) => {
  console.error('Job failed', job.id, err && err.message);
});

module.exports = { worker, queue };
