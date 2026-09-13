import { expect, test, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

async function login(page: Page, role = 'admin') {
  await page.goto('/')
  await page.getByLabel('Demo account role').selectOption(role)
  await page.getByRole('button', { name: 'Enter demo' }).click()
  await expect(page.getByRole('heading', { name: /welcome back/ })).toBeVisible()
  await page.evaluate(() => document.fonts.ready)
}

test('unknown profiles stay unknown through editing, filters, team assignment, and lineups', async ({
  page,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await login(page)
  const name = `Nguyễn Mẫu ${Date.now()}`
  await page.goto('/players')
  await page.getByRole('button', { name: 'Add player', exact: true }).click()
  await page.getByLabel('Full name', { exact: true }).fill(name)
  await expect(page.getByRole('combobox', { name: /Primary team/ })).toHaveValue('')
  await expect(page.getByLabel('Shirt number', { exact: true })).toHaveValue('')
  await page.getByRole('dialog').getByRole('button', { name: 'Add player', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeHidden()
  await page.getByRole('button', { name: 'Unassigned', exact: true }).click()
  const card = page.locator('.player-card').filter({ hasText: name })
  await expect(card).toContainText('Availability unknown')
  await expect(card).toContainText('Not provided')
  await card.click()
  const profilePath = new URL(page.url()).pathname
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
  await expect(page.locator('.profile-facts')).toContainText('Unrated')
  await page.getByRole('button', { name: 'Edit profile', exact: true }).click()
  await page.getByLabel('Nickname', { exact: true }).fill('Mẫu')
  await page.getByRole('button', { name: 'Save profile', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeHidden()
  await page.reload()
  await expect(page.locator('.profile-facts')).toContainText('Unrated')
  const profile = await (await page.request.get(`/api/v1${profilePath}`)).json()
  for (const field of [
    'team_id',
    'positions',
    'jersey',
    'skill',
    'dominant_foot',
    'age_group',
    'availability',
    'preferred_times',
  ]) {
    expect(profile[field], field).toBeNull()
  }
  const exported = await (await page.request.get('/api/v1/export/players')).text()
  expect(exported).toContain(`${name},,Unassigned,,0`)
  await page.goto('/analytics')
  await page.getByLabel('Leaderboard team').selectOption('unassigned')
  await expect(page.locator('.full-leaderboard')).toContainText(name)
  await page.request.post('/api/v1/auth/logout')
  await login(page, 'captain')
  await page.goto(profilePath)
  await expect(page.getByRole('button', { name: 'Edit profile', exact: true })).toBeHidden()
  await page.getByRole('button', { name: 'Assign primary team', exact: true }).click()
  await page.getByRole('combobox', { name: /Primary team/ }).selectOption('2')
  await page.getByRole('button', { name: 'Save team', exact: true }).click()
  await expect(page.locator('.profile-hero .badge')).toHaveText('Young Boys')
  await page.getByRole('button', { name: 'Assign primary team', exact: true }).click()
  await page.getByRole('combobox', { name: /Primary team/ }).selectOption('')
  await page.getByRole('button', { name: 'Save team', exact: true }).click()
  await expect(page.locator('.profile-hero .badge')).toHaveText('Unassigned')
  const matches = await (await page.request.get('/api/v1/matches')).json()
  const match = matches.find((m: { status: string }) => m.status === 'scheduled')
  await page.goto(`/matches/${match.id}`)
  await page.getByRole('button', { name: 'Lineups', exact: true }).click()
  await expect(page.getByText('Auto-balance uses a neutral 5.5/10 estimate', { exact: false })).toBeVisible()
  const bench = page.locator('.bench-player').filter({ hasText: name })
  await expect(bench).toContainText('Unrated')
  await bench.click()
  await page.getByRole('button', { name: 'home position 1:', exact: false }).click()
  await page.getByRole('button', { name: 'Save lineup', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Save lineup', exact: true })).toBeDisabled()
  expect(errors).toEqual([])
})

test('dashboard, RSVP persistence, sharing, theme, and search', async ({ page }) => {
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await login(page)
  await page.getByRole('button', { name: 'Maybe', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Maybe', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await page.reload()
  await expect(page.getByRole('button', { name: 'Maybe', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await page.getByRole('button', { name: 'Share to Messenger', exact: true }).click()
  const summary = page.getByLabel('Shareable summary')
  await expect(summary).toContainText('LEX PICKUP PRO')
  await expect(summary).toContainText('Old Gentlemen')
  await expect(summary).toContainText('/matches/')
  await page.getByRole('button', { name: 'Copy summary', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Copied!', exact: true })).toBeVisible()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain('LEX PICKUP PRO')
  await page.getByRole('button', { name: 'Close dialog' }).click()
  await page.getByRole('button', { name: 'Switch to dark mode' }).click()
  await expect(page.locator('html')).toHaveClass('dark')
  await page.reload()
  await expect(page.locator('html')).toHaveClass('dark')
  await page.getByRole('button', { name: 'Switch to light mode' }).click()
  await page.locator('.search-trigger').click()
  await page.getByLabel('Search players and matches').fill('Duy')
  await page
    .getByRole('dialog')
    .getByRole('link', { name: /Duy Tran/ })
    .click()
  await expect(page.getByRole('heading', { name: 'Duy Tran', exact: true })).toBeVisible()
})

test('all club views render without runtime errors or horizontal page overflow', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await login(page)
  for (const [path, heading] of [
    ['/schedule', 'See you on Saturday.'],
    ['/players', 'Meet the squad.'],
    ['/teams', 'Rivals for 90 minutes. Mates for life.'],
    ['/availability', 'Who’s up for a game?'],
    ['/analytics', 'A little friendly competition.'],
    ['/history', 'Every game has a story.'],
    ['/club', 'A well-run club. A better Saturday.'],
  ]) {
    await page.goto(path)
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), path).toBe(true)
  }
  await page.goto('/schedule')
  await page.getByRole('button', { name: 'Calendar view' }).click()
  await expect(page.locator('.calendar-grid')).toBeVisible()
  expect(errors).toEqual([])
})

test('captain can schedule, edit lineups, complete, and attribute a game', async ({ page }) => {
  await login(page, 'captain')
  await page.getByRole('button', { name: 'Schedule game', exact: true }).click()
  await page.getByLabel('Game name', { exact: true }).fill(`Browser verified game ${Date.now()}`)
  await page.getByRole('dialog').getByRole('button', { name: 'Schedule game', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Match day controls' })).toBeVisible()
  await page.getByRole('button', { name: 'Edit game', exact: true }).click()
  await page.getByLabel('Location', { exact: true }).fill('Browser verified pitch')
  await page.getByRole('button', { name: 'Save game', exact: true }).click()
  await expect(page.getByText('Browser verified pitch', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Going', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Going', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await page.getByRole('button', { name: 'Lineups', exact: true }).click()
  await page.locator('.bench-player').filter({ hasText: 'Alex Parker' }).click()
  await page.getByRole('button', { name: 'home position 1: empty', exact: true }).click()
  await page.locator('.lineup-toolbar').getByRole('button', { name: 'Young Boys', exact: true }).click()
  await page.locator('.bench-player').filter({ hasText: 'David Mitchell' }).click()
  await page.getByRole('button', { name: 'away position 1: empty', exact: true }).click()
  await page.getByRole('button', { name: 'Save lineup' }).click()
  await expect(page.getByRole('button', { name: 'Save lineup' })).toBeDisabled()
  await page.getByRole('button', { name: 'Match day controls' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Save match' }).click()
  await expect(page.getByRole('button', { name: 'Update result' })).toBeVisible()
  await page.getByRole('button', { name: /Match events/ }).click()
  await page.getByRole('button', { name: 'Add event', exact: true }).click()
  await page
    .getByRole('dialog')
    .getByLabel('Player', { exact: true })
    .selectOption({ label: 'Alex Parker · Old Gentlemen' })
  await page.getByRole('dialog').getByRole('button', { name: 'Add event', exact: true }).click()
  await expect(page.locator('.match-event')).toContainText('Alex Parker')
  await page.getByRole('button', { name: 'Update result' }).click()
  await page.getByLabel('Game status').selectOption('completed')
  await page.getByRole('dialog').getByRole('button', { name: 'Save match' }).click()
  await expect(page.getByRole('button', { name: 'Correct result' })).toBeVisible()
  await page.getByRole('button', { name: 'Player ratings', exact: true }).click()
  await page.getByLabel('Rating for David Mitchell').fill('8.5')
  await page.getByRole('button', { name: 'Rate', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Update', exact: true })).toBeVisible()
})

test('administrator invites an existing player and the player claims their profile', async ({ page }) => {
  await login(page)
  const name = `Invited Member ${Date.now()}`
  const created = await page.request.post('/api/v1/players', { data: { name } })
  expect(created.status()).toBe(201)
  await page.goto('/club')
  const email = `member.${Date.now()}@example.com`
  const row = page.getByRole('row').filter({ hasText: name })
  await row.getByRole('button', { name: 'Invite', exact: true }).click()
  await page.getByLabel('Player’s email', { exact: true }).fill(email)
  await page.getByRole('button', { name: 'Create invitation', exact: true }).click()
  const invitation = await page.getByLabel('Personal invitation link').inputValue()
  await page.getByRole('button', { name: 'Close dialog' }).click()
  await page.getByRole('button', { name: 'Account menu' }).click()
  await page.locator('.account-menu').getByRole('button', { name: 'Sign out', exact: true }).click()
  // Navigation must wait for the committed logout; an immediate goto aborts its fetch on slower storage.
  await expect(page).toHaveURL(/\/login$/)
  await page.goto(invitation)
  await expect(page.getByRole('heading', { name: 'Your spot is saved.' })).toBeVisible()
  await page.getByLabel('Email address', { exact: true }).fill(email)
  await page.getByLabel('Password', { exact: true }).fill('BrowserPlayer2026!')
  await page.getByRole('button', { name: 'Create your account', exact: true }).click()
  await expect(page.getByRole('heading', { name: `Hey ${name.split(' ')[0]}, welcome back` })).toBeVisible()
  const me = await page.request.get('/api/v1/auth/me')
  expect((await me.json()).player.name).toBe(name)
})

test('regular players cannot see organizer controls and can update their own profile', async ({ page }) => {
  await login(page, 'player')
  await expect(page.getByRole('button', { name: 'Schedule game', exact: true })).toHaveCount(0)
  await page.goto('/players/6')
  await page.getByRole('button', { name: 'Edit profile' }).click()
  await page
    .getByLabel('Preferred playing times', { exact: true })
    .fill('Saturday mornings and Sunday afternoons')
  await page.getByRole('button', { name: 'Save profile' }).click()
  await expect(page.getByText('Saturday mornings and Sunday afternoons', { exact: true })).toBeVisible()
  await page.goto('/club')
  await expect(page.getByRole('heading', { name: 'Club members & access' })).toHaveCount(0)
  const response = await page.request.post('/api/v1/notes', {
    data: { title: 'Unauthorized', body: 'Not allowed' },
  })
  expect(response.status()).toBe(403)
})

test('dashboard has no serious accessibility violations in either theme', async ({ page }) => {
  await login(page)
  const scan = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()
  const serious = scan.violations.filter((v) => v.impact === 'critical' || v.impact === 'serious')
  expect(
    serious.map((v) => ({ id: v.id, description: v.description, nodes: v.nodes.map((n) => n.target) })),
  ).toEqual([])
  await page.getByRole('button', { name: 'Switch to dark mode' }).click()
  const dark = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()
  expect(
    dark.violations
      .filter((v) => v.impact === 'critical' || v.impact === 'serious')
      .map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })),
  ).toEqual([])
})
