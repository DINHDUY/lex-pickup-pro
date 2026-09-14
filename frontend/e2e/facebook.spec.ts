import { expect, test, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const candidate = {
  id: 30,
  name: 'Nguyễn Existing Player',
  nickname: 'Mẫu',
  photo_url: '',
  team_id: 1,
  team_name: 'Old Gentlemen',
}
const session = {
  name: 'Different Facebook Name',
  email: 'member@example.com',
  expires_at: '2099-01-01T00:00:00Z',
  status: 'selection',
  invited_player_id: null,
  completed_player_id: null,
}

async function setup(page: Page, state = session) {
  await page.route('**/api/v1/auth/onboarding', (route) => route.fulfill({ json: state }))
  await page.route('**/api/v1/auth/onboarding/players?*', (route) => {
    const search = new URL(route.request().url()).searchParams.get('search') || ''
    const players = candidate.name.toLowerCase().includes(search.toLowerCase()) ? [candidate] : []
    return route.fulfill({ json: { total: players.length, players } })
  })
}

test('Facebook member searches, confirms an unclaimed profile, and enters the club', async ({ page }) => {
  await setup(page)
  await page.route('**/api/v1/auth/onboarding/claim', async (route) => {
    expect(route.request().postDataJSON()).toEqual({ player_id: candidate.id })
    // OAuth and claim transport are mocked here; real binding is covered by provider contract tests.
    // Give the simulated Facebook clients their own IP budget, separate from password-login tests.
    const login = await page.request.post('/api/v1/auth/login', {
      headers: { 'X-Forwarded-For': '198.51.100.60' },
      data: { email: 'player@lexpickup.club', password: 'PickupPro2026!' },
    })
    expect(login.ok()).toBeTruthy()
    await route.fulfill({ json: await login.json() })
  })
  await page.goto('/onboarding/claim-profile')
  await expect(page.getByRole('heading', { name: 'Choose your player profile' })).toBeVisible()
  await expect(page.getByText(session.email, { exact: true })).toBeVisible()
  await page.getByLabel('Search profiles').fill('not present')
  await expect(page.getByText('No profiles found.', { exact: false })).toBeVisible()
  await page.getByLabel('Search profiles').fill('Nguyễn')
  await page.getByRole('button', { name: /Select Nguyễn/ }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText(session.email)
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await dialog.getByRole('button', { name: 'This is my profile' }).click()
  await expect(page).toHaveURL('/')
  await expect(page.getByRole('heading', { name: /welcome back/i })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: /welcome back/i })).toBeVisible()
})

test('competing profile claim refreshes choices and cancellation returns to login', async ({ page }) => {
  await setup(page)
  await page.route('**/api/v1/auth/onboarding/claim', async (route) => {
    await page.route('**/api/v1/auth/onboarding/players?*', (candidates) =>
      candidates.fulfill({ json: { total: 0, players: [] } }),
    )
    await route.fulfill({
      status: 409,
      json: { detail: 'This profile is no longer available. Please choose another profile.' },
    })
  })
  await page.route('**/api/v1/auth/onboarding/cancel', async (route) => {
    await page.unroute('**/api/v1/auth/onboarding')
    await route.fulfill({ status: 204 })
  })
  await page.goto('/onboarding/claim-profile')
  await page.getByRole('button', { name: /Select Nguyễn/ }).click()
  await page.getByRole('button', { name: 'This is my profile' }).click()
  await expect(page.getByRole('dialog')).toBeHidden()
  await expect(page.getByRole('alert')).toContainText('no longer available')
  await expect(page.getByText('0 unclaimed profiles')).toBeVisible()
  await page.getByRole('button', { name: 'My profile is missing or already claimed' }).click()
  await expect(
    page.getByText('Ask a club administrator to add your roster profile', { exact: false }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(page).toHaveURL('/login')
  await expect(page.getByRole('heading', { name: 'Back for another game?' })).toBeVisible()
})

test('existing account can connect Facebook with password confirmation', async ({ page }) => {
  await setup(page, { ...session, status: 'link_required', email: 'admin@lexpickup.club' })
  await page.route('**/api/v1/auth/onboarding/link', async (route) => {
    expect(route.request().postDataJSON()).toEqual({ password: 'PickupPro2026!' })
    // Give the simulated Facebook clients their own IP budget, separate from password-login tests.
    const login = await page.request.post('/api/v1/auth/login', {
      headers: { 'X-Forwarded-For': '198.51.100.60' },
      data: { email: 'admin@lexpickup.club', password: 'PickupPro2026!' },
    })
    expect(login.ok()).toBeTruthy()
    await route.fulfill({ json: await login.json() })
  })
  await page.goto('/onboarding/claim-profile')
  await expect(page.getByRole('heading', { name: 'Connect your existing account' })).toBeVisible()
  await page.getByLabel('Existing account password').fill('PickupPro2026!')
  await page.getByRole('button', { name: 'Connect Facebook', exact: true }).click()
  await expect(page.getByRole('heading', { name: /welcome back/i })).toBeVisible()
})

test('expired onboarding offers Facebook retry and login keeps password access', async ({ page }) => {
  await page.goto('/onboarding/claim-profile')
  await expect(page.getByRole('heading', { name: 'Sign in to choose your profile' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Continue with Facebook' })).toHaveAttribute(
    'href',
    '/api/v1/auth/facebook/login',
  )
  await page.route('**/api/v1/config', (route) =>
    route.fulfill({
      json: { facebook_auth_enabled: true, registration_enabled: false, demo_enabled: false },
    }),
  )
  await page.goto('/login?facebook_error=Facebook+did+not+share+an+email+address.')
  await expect(page.getByRole('alert')).toContainText('did not share an email')
  await page.getByRole('button', { name: 'Sign in with email and password' }).click()
  await expect(page.getByLabel('Email address')).toBeVisible()
  await expect(page.getByLabel('Password', { exact: true })).toBeVisible()
})
