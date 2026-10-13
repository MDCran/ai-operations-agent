import { test, expect } from '@playwright/test'

test('sign in, persist records, run agents, ingest knowledge, approve a change and inspect the workspace', async ({
  page,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const suffix = Date.now().toString()
  await page.goto('/')
  await page
    .getByLabel('Email address')
    .fill(process.env.DEMO_EMAIL || 'owner@example.com')
  await page
    .getByLabel('Password', { exact: true })
    .fill(process.env.DEMO_PASSWORD || 'change-this-local-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Operations overview' }),
  ).toBeVisible()
  await page.getByRole('link', { name: 'Customers', exact: true }).click()
  await page.getByRole('button', { name: 'Add customer' }).click()
  await page.getByLabel('First name').fill('Avery')
  await page.getByLabel('Last name').fill(`Morgan ${suffix}`)
  await page
    .getByLabel('Email', { exact: true })
    .fill(`avery.${suffix}@example.com`)
  await page.getByLabel('Company').fill('Northstar Studio')
  await page.getByRole('button', { name: 'Create record' }).click()
  await expect(
    page.getByText(`avery.${suffix}@example.com`, { exact: true }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Edit Avery' }).first().click()
  await page
    .getByLabel('Email', { exact: true })
    .fill(`updated.${suffix}@example.com`)
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(
    page.getByText('Change submitted for approval. Review it in Approvals.'),
  ).toBeVisible()
  await page.getByRole('link', { name: 'Approvals', exact: true }).click()
  await page
    .locator('.approval-card')
    .filter({ hasText: `updated.${suffix}@example.com` })
    .getByRole('button', { name: 'Approve action' })
    .click()
  await page.getByRole('button', { name: 'Confirm decision' }).click()
  await expect(
    page
      .locator('.approval-card')
      .filter({ hasText: `updated.${suffix}@example.com` }),
  ).toHaveCount(0, { timeout: 20000 })
  await page.getByRole('link', { name: 'Customers', exact: true }).click()
  await expect(
    page.getByText(`updated.${suffix}@example.com`, { exact: true }),
  ).toBeVisible({ timeout: 20000 })
  await page.getByRole('link', { name: 'Documents', exact: true }).click()
  await page.getByRole('button', { name: 'Upload document' }).click()
  await page.locator('input[type=file]').setInputFiles({
    name: `policy-${suffix}.txt`,
    mimeType: 'text/plain',
    buffer: Buffer.from(
      'Our refund policy allows refunds within 30 days of purchase. Contact support with your order reference.',
    ),
  })
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Upload document' })
    .click()
  await expect(
    page
      .getByRole('row')
      .filter({ hasText: `policy-${suffix}.txt` })
      .getByText('ready', { exact: true }),
  ).toBeVisible({ timeout: 30000 })
  await page.getByLabel('Knowledge question').fill('refund policy')
  await page.getByRole('button', { name: 'Search knowledge' }).click()
  await expect(page.locator('.search-results')).toContainText('30 days')
  await page
    .getByRole('link', { name: 'Agent playground', exact: true })
    .click()
  await page
    .getByLabel('Message', { exact: true })
    .fill(`Create ticket: Follow up invoice ${suffix}`)
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.message-assistant')).toContainText(
    'Operation completed',
    { timeout: 30000 },
  )
  await page.getByRole('link', { name: 'Support tickets', exact: true }).click()
  await expect(
    page.getByRole('button', { name: `Follow up invoice ${suffix}` }),
  ).toBeVisible()
  await page.getByRole('link', { name: 'Appointments', exact: true }).click()
  await page.getByRole('button', { name: 'Add appointment' }).click()
  await page.getByLabel('Title', { exact: true }).fill('Project consultation')
  await page
    .getByRole('combobox', { name: 'Customer', exact: true })
    .selectOption({ label: `Avery Morgan ${suffix}` })
  await page
    .getByRole('combobox', { name: 'Appointment type', exact: true })
    .selectOption({ label: 'Consultation' })
  const businessDate = new Date()
  businessDate.setDate(businessDate.getDate() + 7)
  while ([0, 6].includes(businessDate.getDay()))
    businessDate.setDate(businessDate.getDate() + 1)
  await page
    .getByLabel('Business date', { exact: true })
    .fill(businessDate.toISOString().slice(0, 10))
  await page.getByRole('button', { name: 'Check availability' }).click()
  await page.locator('.slots button').first().click()
  await page.getByRole('button', { name: 'Create record' }).click()
  await expect(page.getByText('Record saved successfully.')).toBeVisible()
  for (const link of [
    'Tasks',
    'Knowledge search',
    'Runs & workflows',
    'Team & roles',
    'Organization',
    'AI settings',
    'Audit logs',
    'Analytics',
  ]) {
    await page.getByRole('link', { name: link, exact: true }).click()
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect(page.locator('[role=alert]')).toHaveCount(0)
  }
  await page.getByRole('link', { name: 'Dashboard', exact: true }).click()
  await page.screenshot({
    path: '../../docs/screenshots/dashboard.png',
    fullPage: true,
  })
  await page.getByRole('button', { name: 'Toggle color theme' }).click()
  await page.screenshot({
    path: '../../docs/screenshots/dashboard-dark.png',
    fullPage: true,
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(
    page.getByRole('heading', { name: 'Operations overview' }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('link', { name: 'Tasks', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Tasks', exact: true }),
  ).toBeVisible()
  expect(errors).toEqual([])
})
