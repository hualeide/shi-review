/**
 * 真实 Chromium。虚构 items/config，外网 abort。
 * 运行：沿用已有 NODE_PATH 里的 playwright，不要 npm install。
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const { chromium } = require('playwright');

const SCORES = 'shi-review-scores-v2';
const REVIEWER = 'shi-reviewer-name';

const ITEMS = [
  {
    id: 'fake-1',
    kind: 'chat_record',
    title: '虚构条目',
    time: 1700000000,
    sender: '甲',
    thread: [{ sender: '甲', time: 1700000000, text: '假正文', media: [] }],
  },
];

const STATIC = {
  '/index.html': ['text/html; charset=utf-8', 'index.html'],
  '/app.js': ['text/javascript; charset=utf-8', 'app.js'],
  '/styles.css': ['text/css; charset=utf-8', 'styles.css'],
};

let browser;

async function openPage(init, arg) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (err) => errors.push(String(err)));
  page.on('dialog', (dialog) => dialog.accept('假人'));
  if (init) await context.addInitScript(init, arg);
  await page.route('**/*', async (route) => {
    const u = new URL(route.request().url());
    if (u.pathname === '/data/items.json') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: ITEMS }),
      });
      return;
    }
    if (u.pathname === '/config.js') {
      await route.fulfill({
        status: 200,
        contentType: 'application/javascript',
        body: 'window.SHI_SCORE={};',
      });
      return;
    }
    const file = STATIC[u.pathname];
    if (file) {
      await route.fulfill({
        status: 200,
        contentType: file[0],
        body: fs.readFileSync(path.join(__dirname, file[1])),
      });
      return;
    }
    await route.abort();
  });
  await page.goto('http://127.0.0.1:9/index.html');
  return { context, page, errors };
}

test.before(async () => {
  browser = await chromium.launch({ headless: true });
});

test.after(async () => {
  await browser?.close();
});

test('读取被拒绝时答题卡仍出来', async () => {
  const { context, page, errors } = await openPage(() => {
    Storage.prototype.getItem = function () {
      throw new DOMException('denied', 'SecurityError');
    };
  });
  try {
    await page.waitForSelector('#answerSheet .cell', { timeout: 2000 }).catch(() => {});
    assert.equal(await page.locator('#answerSheet .cell').count(), 1);
    assert.equal(await page.locator('#stage .loading').count(), 0);
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
});

test('写入被拒绝时仍能看详情并保持未保存', async () => {
  const { context, page, errors } = await openPage(() => {
    localStorage.setItem('shi-reviewer-name', '假人');
    Storage.prototype.setItem = function () {
      throw new DOMException('quota', 'QuotaExceededError');
    };
  });
  try {
    await page.waitForSelector('.cell[data-id="fake-1"]');
    await page.locator('.cell[data-id="fake-1"]').click();
    await page.waitForSelector('#detailBar:not([hidden])', { timeout: 2000 }).catch(() => {});
    assert.equal(await page.locator('#detailBar:not([hidden])').count(), 1);
    assert.equal(await page.locator('h2').innerText(), '虚构条目');
    await page.evaluate(() => {
      window.submitScoreRemote = async () => ({ ok: true, detail: 'fake' });
    });
    await page.locator('#scores button[data-score="3"]').click();
    await page.waitForFunction(() => document.querySelector('.current-score')?.textContent?.includes('已标：3'));
    await page.waitForTimeout(50);
    const sync = page.locator('#syncStatus');
    assert.match(await sync.innerText(), /未保存|仅本页/);
    assert.equal(await sync.getAttribute('data-ok'), '0');
    assert.doesNotMatch(await sync.innerText(), /已标记/);
    await page.locator('#btnBackSheet').click();
    await page.waitForSelector('#answerSheet');
    assert.equal(await page.locator('.cell[data-id="fake-1"].is-marked').count(), 1);
    await page.locator('.cell[data-id="fake-1"]').click();
    await page.waitForSelector('.current-score');
    assert.match(await page.locator('.current-score').innerText(), /已标：3/);
    assert.equal(await page.evaluate((key) => localStorage.getItem(key), SCORES), null);
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
});

test('坏 JSON 不当成分数对象', async () => {
  const bad = ['null', '[]', '"nope"', '{bad'];
  for (const raw of bad) {
    const { context, page } = await openPage((value) => {
      localStorage.setItem('shi-review-scores-v2', value);
    }, raw);
    try {
      await page.waitForSelector('#answerSheet .cell', { timeout: 2000 }).catch(() => {});
      assert.equal(await page.locator('#answerSheet .cell').count(), 1, raw);
      assert.equal(await page.locator('#stage .loading').count(), 0, raw);
      assert.equal(await page.locator('.cell.is-marked').count(), 0, raw);
    } finally {
      await context.close();
    }
  }
});

test('合法存储跨刷新，详情可往返', async () => {
  const seed = () => {
    if (sessionStorage.getItem('seeded')) return;
    localStorage.setItem(
      'shi-review-scores-v2',
      JSON.stringify({ 'fake-1': { id: 'fake-1', score: 4, skip: false, reviewer: '假人' } }),
    );
    localStorage.setItem('shi-reviewer-name', '假人');
    sessionStorage.setItem('seeded', '1');
  };
  const { context, page, errors } = await openPage(seed);
  try {
    await page.waitForSelector('.cell[data-id="fake-1"].is-marked');
    await page.locator('.cell[data-id="fake-1"]').click();
    await page.waitForSelector('.current-score');
    assert.match(await page.locator('.current-score').innerText(), /已标：4/);
    await page.locator('#btnBackSheet').click();
    await page.waitForSelector('#answerSheet');
    await page.reload();
    await page.waitForSelector('.cell[data-id="fake-1"].is-marked');
    await page.evaluate(() => {
      window.submitScoreRemote = async () => ({ ok: true, detail: 'fake' });
    });
    await page.locator('.cell[data-id="fake-1"]').click();
    await page.locator('#scores button[data-score="2"]').click();
    await page.waitForFunction(() => document.querySelector('#syncStatus')?.textContent === '已标记');
    assert.equal(await page.locator('#syncStatus').getAttribute('data-ok'), '1');
    await page.reload();
    await page.waitForSelector('.cell[data-id="fake-1"].is-marked');
    await page.locator('.cell[data-id="fake-1"]').click();
    await page.waitForSelector('.current-score');
    assert.match(await page.locator('.current-score').innerText(), /已标：2/);
    const stored = await page.evaluate((key) => JSON.parse(localStorage.getItem(key)), SCORES);
    assert.equal(stored['fake-1'].score, 2);
    assert.equal(stored['fake-1'].reviewer, '假人');
    assert.equal(await page.evaluate((key) => localStorage.getItem(key), REVIEWER), '假人');
    assert.deepEqual(errors, []);
  } finally {
    await context.close();
  }
});
