#!/usr/bin/env node
import { mkdir, writeFile } from 'node:fs/promises'
import { createInterface } from 'node:readline/promises'
import { stdin as input, stdout as output } from 'node:process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const here = dirname(fileURLToPath(import.meta.url))

/** Messenger UI strings — edit here when Facebook restyles the chat info pane. */
const selectors = {
  loginEmail: 'input[name="email"], input#email, input[type="email"]',
  searchMessenger: /search messenger/i,
  messageComposer: /message|aa/i,
  cookieButtons: [
    /allow all cookies/i,
    /decline optional cookies/i,
    /only allow essential cookies/i,
  ],
  dismissButtons: [/^not now$/i, /^block$/i],
  conversationInfo: /conversation information|chat information|chat info|^information$/i,
  seeAll: /^see all$/i,
  chatMembers: /chat members|people in this chat|^people$|^members$/i,
  chatInfoHeading: /^chat info$/i,
}

const CHROME_NAMES =
  /^(chat info|customize chat|group options|media, files and links|privacy & support|see all|add people|search|chat members|people|members|members in this chat)$/i

const STABLE_TICKS = 12
const SCROLL_PAUSE_MS = 700

function parseArgs(argv) {
  const args = {
    url: process.env.MESSENGER_THREAD_URL || '',
    out: join(here, 'out'),
    timeoutMs: 180_000,
  }
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i]
    const next = () => {
      i += 1
      return argv[i]
    }
    if (token === '--url') args.url = next()
    else if (token.startsWith('--url=')) args.url = token.slice('--url='.length)
    else if (token === '--out') args.out = next()
    else if (token.startsWith('--out=')) args.out = token.slice('--out='.length)
    else if (token === '--timeout-ms') args.timeoutMs = Number(next())
    else if (token.startsWith('--timeout-ms=')) args.timeoutMs = Number(token.slice('--timeout-ms='.length))
    else if (token === '--help' || token === '-h') args.help = true
    else throw new Error(`Unknown argument: ${token}`)
  }
  if (!Number.isFinite(args.timeoutMs) || args.timeoutMs <= 0) {
    throw new Error('--timeout-ms must be a positive number')
  }
  return args
}

function usage() {
  return `Usage: node extract.mjs --url 'https://www.messenger.com/t/<THREAD_ID>/' [--out ./out] [--timeout-ms 180000]`
}

function csvEscape(value) {
  const text = String(value ?? '')
  if (/[",\n\r]/.test(text)) return `"${text.replaceAll('"', '""')}"`
  return text
}

function toCsv(members) {
  const header = ['name', 'profileUrl', 'role', 'photoUrl']
  const rows = members.map((member) =>
    header.map((key) => csvEscape(member[key] ?? '')).join(','),
  )
  return `${header.join(',')}\n${rows.join('\n')}\n`
}

function memberKey(member) {
  const url = (member.profileUrl || '').split('?')[0].replace(/\/$/, '')
  if (url) return `url:${url}`
  return `name:${(member.name || '').trim().toLowerCase()}`
}

function mergeMembers(into, incoming) {
  for (const member of incoming) {
    const name = (member.name || '').trim()
    const profileUrl = (member.profileUrl || '').trim()
    if (!name || CHROME_NAMES.test(name)) continue
    const normalized = {
      name,
      profileUrl,
      role: member.role === 'admin' ? 'admin' : 'member',
      photoUrl: (member.photoUrl || '').trim(),
    }
    const key = memberKey(normalized)
    const existing = into.get(key)
    if (!existing) {
      into.set(key, normalized)
      continue
    }
    if (!existing.photoUrl && normalized.photoUrl) existing.photoUrl = normalized.photoUrl
    if (existing.role !== 'admin' && normalized.role === 'admin') existing.role = 'admin'
  }
}

async function waitForEnter(message) {
  if (!input.isTTY) {
    throw new Error('Login required but stdin is not a TTY. Run this script in a terminal.')
  }
  const rl = createInterface({ input, output })
  try {
    await rl.question(`${message}\nPress Enter here when you are done… `)
  } finally {
    rl.close()
  }
}

async function clickFirstMatch(page, patterns, timeout = 1500) {
  for (const pattern of patterns) {
    const button = page.getByRole('button', { name: pattern }).first()
    if (await button.isVisible({ timeout }).catch(() => false)) {
      await button.click({ timeout }).catch(() => {})
      return true
    }
  }
  return false
}

async function dismissInterruptions(page) {
  await clickFirstMatch(page, selectors.cookieButtons, 2500)
  await clickFirstMatch(page, selectors.dismissButtons, 1500)
}

async function loginFormVisible(page) {
  if (/\/login|checkpoint|recover/i.test(page.url())) return true
  return page.locator(selectors.loginEmail).first().isVisible({ timeout: 1500 }).catch(() => false)
}

async function messengerChromeVisible(page) {
  const search = page.getByPlaceholder(selectors.searchMessenger)
  const composer = page.getByRole('textbox', { name: selectors.messageComposer })
  const heading = page.getByRole('heading').first()
  return (
    (await search.first().isVisible({ timeout: 1500 }).catch(() => false)) ||
    (await composer.first().isVisible({ timeout: 1500 }).catch(() => false)) ||
    ((await heading.isVisible({ timeout: 1500 }).catch(() => false)) && /messenger\.com|facebook\.com\/messages/i.test(page.url()))
  )
}

async function waitUntilLoggedIn(page, timeoutMs) {
  await dismissInterruptions(page)
  if (!(await loginFormVisible(page)) && (await messengerChromeVisible(page))) return
  if (await loginFormVisible(page) || !(await messengerChromeVisible(page))) {
    await waitForEnter('Log in to Messenger in the browser window (including 2FA or checkpoint if shown).')
  }
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    await dismissInterruptions(page)
    if (!(await loginFormVisible(page)) && (await messengerChromeVisible(page))) return
    await page.waitForTimeout(1000)
  }
  throw new Error('Still not logged in after waiting. Complete login and re-run.')
}

async function saveDebug(page, outDir, reason) {
  await mkdir(outDir, { recursive: true })
  const shot = join(outDir, 'debug.png')
  await page.screenshot({ path: shot, fullPage: true }).catch(() => {})
  throw new Error(`${reason} Screenshot: ${shot}`)
}

async function chatInfoPanelVisible(page) {
  const heading = page.getByRole('heading', { name: selectors.chatInfoHeading })
  if (await heading.first().isVisible({ timeout: 800 }).catch(() => false)) return true
  if (await page.getByText(selectors.chatMembers).first().isVisible({ timeout: 500 }).catch(() => false)) return true
  return page.getByText(/^customize chat$/i).first().isVisible({ timeout: 400 }).catch(() => false)
}

async function membersListReady(page) {
  const dialog = page.getByRole('dialog').filter({ hasText: selectors.chatMembers })
  if (await dialog.first().isVisible({ timeout: 800 }).catch(() => false)) return true
  return chatInfoPanelVisible(page)
}

async function clickConversationInfo(page) {
  const labeled = page.getByRole('button', { name: selectors.conversationInfo })
  if (await labeled.first().isVisible({ timeout: 2500 }).catch(() => false)) {
    await labeled.first().click()
    return 'labeled'
  }

  const clicked = await page.evaluate(() => {
    const match = (el) => {
      const label = `${el.getAttribute('aria-label') || ''} ${el.getAttribute('title') || ''}`.toLowerCase()
      return /conversation information|chat information|chat info|conversation details/.test(label)
    }
    const buttons = [...document.querySelectorAll('[role="button"], button')]
    const info = buttons.find(match)
    if (info) {
      info.click()
      return true
    }
    const header = document.querySelector('header, [role="banner"]')
    if (!header) return false
    const headerButtons = [...header.querySelectorAll('[role="button"], button')]
    const last = headerButtons.at(-1)
    if (!last) return false
    last.click()
    return true
  })
  return clicked ? 'header-last' : ''
}

async function clickChatMembersSeeAll(page) {
  return page.evaluate(() => {
    const isSeeAll = (el) => {
      const label = `${el.getAttribute('aria-label') || ''} ${(el.textContent || '').replace(/\s+/g, ' ').trim()}`
      return /^see all$/i.test(label.trim()) || /see all (members|people)/i.test(label)
    }
    const isMembersHeading = (text) =>
      /^(chat members|people in this chat|members)(\s+\d+)?$/i.test(text.trim())

    const headings = [...document.querySelectorAll('h1, h2, h3, h4, span, div, a')].filter((el) => {
      const compact = (el.textContent || '').replace(/\s+/g, ' ').trim()
      return compact.length > 0 && compact.length < 40 && isMembersHeading(compact)
    })

    const tryClickSeeAll = (root) => {
      const match = [...root.querySelectorAll('[role="button"], button, a')].find(isSeeAll)
      if (match) {
        match.click()
        return true
      }
      return false
    }

    for (const heading of headings) {
      let root = heading
      for (let depth = 0; depth < 10 && root; depth += 1) {
        if (tryClickSeeAll(root)) return 'see-all'
        root = root.parentElement
      }
    }

    const membersButton = [...document.querySelectorAll('[role="button"], button, a')].find((el) =>
      /chat members|people in this chat/i.test(`${el.getAttribute('aria-label') || ''} ${el.textContent || ''}`),
    )
    if (membersButton) {
      membersButton.click()
      return 'members-control'
    }
    return ''
  })
}

async function openMembersPane(page, outDir, timeoutMs) {
  page.setDefaultTimeout(Math.min(timeoutMs, 15_000))
  if (await membersListReady(page)) {
    await clickChatMembersSeeAll(page)
    await page.waitForTimeout(800)
    return
  }

  await clickConversationInfo(page)
  await page.waitForTimeout(1200)

  if (!(await chatInfoPanelVisible(page))) {
    await waitForEnter(
      'Open the right-hand Chat info panel in the browser (click the (i) button in the thread header), then press Enter.',
    )
    await page.waitForTimeout(800)
  }

  if (await chatInfoPanelVisible(page)) {
    await clickChatMembersSeeAll(page)
    await page.waitForTimeout(800)
    return
  }

  if (!(await membersListReady(page))) {
    await saveDebug(
      page,
      outDir,
      'Could not open the right-hand Chat info panel. Click the (i) button in the thread header and re-run.',
    )
  }
}

async function harvestVisibleMembers(page) {
  return page.evaluate((chromePatternSource) => {
    const chromeNames = new RegExp(chromePatternSource, 'i')
    const skipPath =
      /^\/(messages|t|e2ee|login|watch|reel|stories|groups|events|marketplace|privacy|help|settings|pages|gaming|ads|jobs|friends|notifications)\b/i

    const isProfileUrl = (href) => {
      try {
        const url = new URL(href, location.origin)
        const host = url.hostname.replace(/^www\./, '').replace(/^web\./, '').replace(/^m\./, '')
        if (!['facebook.com', 'messenger.com'].includes(host)) return false
        const path = url.pathname
        if (skipPath.test(path) || path.includes('/messages/')) return false
        if (path.startsWith('/profile.php')) return true
        if (path.startsWith('/people/')) return true
        if (/^\/user\/\d+/.test(path)) return true
        if (/^\/\d+\/?$/.test(path)) return true
        if (/^\/[A-Za-z0-9.]{2,}\/?$/.test(path)) return true
        return false
      } catch {
        return false
      }
    }

    const photoFrom = (row) => {
      const img = row.querySelector('img')
      if (!img) return ''
      return img.currentSrc || img.src || ''
    }

    const roleFrom = (row) => (/\bAdmin\b/i.test(row.innerText || '') ? 'admin' : 'member')

    const compact = (el) => (el.textContent || '').replace(/\s+/g, ' ').trim()
    const heading = [...document.querySelectorAll('h1, h2, h3, h4, [role="heading"], span, div')].find((el) =>
      /^(chat members|people in this chat)$/i.test(compact(el)),
    )
    let root = heading ? heading.parentElement : null
    if (heading) {
      let node = heading.parentElement
      for (let depth = 0; depth < 16 && node; depth += 1) {
        const added = ((node.innerText || '').match(/Added by /g) || []).length
        const rect = node.getBoundingClientRect()
        if (added >= 1 && rect.left > window.innerWidth * 0.4) {
          root = node
          break
        }
        node = node.parentElement
      }
    }

    const seen = new Map()
    const add = (name, profileUrl, role, photoUrl) => {
      const trimmed = (name || '').trim().split('\n')[0].trim()
      if (!trimmed || chromeNames.test(trimmed) || /^added by /i.test(trimmed) || trimmed.length > 80) return
      const key = `${(profileUrl || '').split('?')[0]}|${trimmed.toLowerCase()}`
      if (seen.has(key)) return
      seen.set(key, { name: trimmed, profileUrl: profileUrl || '', role, photoUrl: photoUrl || '' })
    }

    const nameFromRow = (text) => {
      const lines = (text || '').split('\n').map((line) => line.trim()).filter(Boolean)
      const addedIdx = lines.findIndex((line) => /^added by /i.test(line))
      if (addedIdx >= 1) return lines[addedIdx - 1]
      const compact = (text || '').replace(/\s+/g, ' ').trim()
      const match = compact.match(/^(.*?)(?:\s+Added by\s+.+)$/i)
      return match ? match[1].trim() : ''
    }

    const scope = root || document.body
    const rows = [...scope.querySelectorAll('div, li, a, [role="listitem"], [role="button"]')].filter((el) => {
      const rect = el.getBoundingClientRect()
      if (rect.left < window.innerWidth * 0.45 || rect.width < 80) return false
      const text = el.innerText || ''
      if ((text.match(/Added by /gi) || []).length !== 1) return false
      return Boolean(nameFromRow(text))
    })

    for (const row of rows) {
      const name = nameFromRow(row.innerText || '')
      const link = [...row.querySelectorAll('a[href]')].find((anchor) => isProfileUrl(anchor.href))
      add(name, link ? link.href : '', roleFrom(row), photoFrom(row))
    }

    if (!seen.size) {
      for (const link of scope.querySelectorAll('a[href]')) {
        if (!isProfileUrl(link.href)) continue
        const rect = link.getBoundingClientRect()
        if (rect.left < window.innerWidth * 0.45) continue
        add(link.innerText || link.getAttribute('aria-label') || '', link.href, roleFrom(link), photoFrom(link))
      }
    }

    return [...seen.values()]
  }, CHROME_NAMES.source)
}

async function scrollMembersPane(page) {
  return page.evaluate(() => {
    const compact = (el) => (el.textContent || '').replace(/\s+/g, ' ').trim()
    const heading = [...document.querySelectorAll('h1, h2, h3, h4, [role="heading"], span, div')].find((el) =>
      /^(chat members|people in this chat)$/i.test(compact(el)),
    )
    const start = heading || [...document.querySelectorAll('h1, h2, h3, span, div')].find((el) => /^chat info$/i.test(compact(el)))
    const candidates = []
    let node = start
    while (node && node !== document.body) {
      if (node instanceof HTMLElement) {
        const style = getComputedStyle(node)
        if (/(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight + 20) {
          candidates.push(node)
        }
      }
      node = node.parentElement
    }
    if (!candidates.length) {
      for (const el of document.querySelectorAll('div, aside, [role="complementary"]')) {
        if (!(el instanceof HTMLElement)) continue
        const rect = el.getBoundingClientRect()
        if (rect.left < window.innerWidth * 0.5) continue
        const style = getComputedStyle(el)
        if (!/(auto|scroll)/.test(style.overflowY)) continue
        if (el.scrollHeight <= el.clientHeight + 20) continue
        candidates.push(el)
      }
    }
    candidates.sort((a, b) => b.clientHeight - a.clientHeight)
    const scroller = candidates[0]
    if (!scroller) return { scrolled: false, top: 0, height: 0 }
    const before = scroller.scrollTop
    scroller.scrollTop = Math.min(
      scroller.scrollTop + Math.max(scroller.clientHeight * 0.85, 240),
      scroller.scrollHeight,
    )
    return {
      scrolled: scroller.scrollTop !== before,
      top: scroller.scrollTop,
      height: scroller.scrollHeight,
    }
  })
}

async function collectMembers(page) {
  const members = new Map()
  let stable = 0
  let lastCount = 0
  let lastTop = -1

  mergeMembers(members, await harvestVisibleMembers(page))

  for (let tick = 0; tick < 400 && stable < STABLE_TICKS; tick += 1) {
    const scroll = await scrollMembersPane(page)
    await page.waitForTimeout(SCROLL_PAUSE_MS)
    mergeMembers(members, await harvestVisibleMembers(page))
    const count = members.size
    const unchanged = count === lastCount && (!scroll.scrolled || scroll.top === lastTop)
    stable = unchanged ? stable + 1 : 0
    lastCount = count
    lastTop = scroll.top
    if (tick % 5 === 0) {
      console.log(`Collected ${count} unique members…`)
    }
  }

  return [...members.values()].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }))
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  if (args.help) {
    console.log(usage())
    return
  }
  if (!args.url) {
    throw new Error(`Missing --url (or MESSENGER_THREAD_URL).\n${usage()}`)
  }

  await mkdir(args.out, { recursive: true })
  const authDir = join(here, '.auth')
  await mkdir(authDir, { recursive: true })

  const context = await chromium.launchPersistentContext(authDir, {
    headless: false,
    viewport: { width: 1280, height: 900 },
    locale: 'en-US',
    slowMo: 50,
    args: ['--disable-blink-features=AutomationControlled'],
  })
  context.setDefaultTimeout(args.timeoutMs)

  const page = context.pages()[0] || (await context.newPage())
  try {
    await page.goto(args.url, { waitUntil: 'domcontentloaded' })
    await waitUntilLoggedIn(page, args.timeoutMs)
    if (!page.url().includes('/t/') && !page.url().includes('/messages/')) {
      await page.goto(args.url, { waitUntil: 'domcontentloaded' })
    }
    await dismissInterruptions(page)
    await page.waitForTimeout(1000)
    await page
      .getByRole('button', { name: selectors.conversationInfo })
      .or(page.locator('[aria-label*="Conversation information" i], [aria-label*="Chat information" i], [aria-label*="Chat info" i]'))
      .first()
      .waitFor({ timeout: 20_000 })
      .catch(() => {})
    await openMembersPane(page, args.out, args.timeoutMs)
    const members = await collectMembers(page)
    if (!members.length) {
      await saveDebug(page, args.out, 'Opened the members pane but found no members.')
    }

    const jsonPath = join(args.out, 'members.json')
    const csvPath = join(args.out, 'members.csv')
    await writeFile(jsonPath, `${JSON.stringify(members, null, 2)}\n`)
    await writeFile(csvPath, toCsv(members))

    const admins = members.filter((member) => member.role === 'admin').length
    console.log(`Exported ${members.length} members (${admins} admin).`)
    console.log(`JSON: ${jsonPath}`)
    console.log(`CSV:  ${csvPath}`)
  } finally {
    await context.close()
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error)
  process.exitCode = 1
})
