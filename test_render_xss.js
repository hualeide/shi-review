/**
 * 真实 Chromium DOM。加载本目录 index.html / app.js。
 * items.json 与 config.js 只回虚构内容，不读原文件。其余外网请求 abort。
 * 运行：NODE_PATH 指向已有 playwright，不要 npm install。
 */
const assert = require('node:assert/strict');
const path = require('node:path');
const { test } = require('node:test');
const fs = require('node:fs');
const { chromium } = require('playwright');

const CASES = [
  { id: 'cn', text: '你好', url: 'https://example.test/图片.png' },
  { id: 'punct', text: '甲&乙<丙>丁\'戊"己', url: 'https://example.test/a&b<c>d\'e"f.png' },
  { id: 'urlq', text: '链接', url: 'https://example.test/x" onerror="alert(1)' },
  { id: 'localq', text: '本地', local: 'media/a" onerror="alert(1)' },
  {
    id: 'both',
    text: '回退',
    local: 'media/b" onerror="alert(1)',
    url: 'https://example.test/fb" onerror="alert(2)',
  },
];

function mediaOf(c) {
  const m = { type: 'image' };
  if (c.local) m.local = c.local;
  if (c.url) m.url = c.url;
  return m;
}

function expectOf(c) {
  const src = c.local || c.url;
  return { src, full: src, fallback: c.local && c.url ? c.url : null };
}

function item(kind, c) {
  return {
    id: `${kind}-${c.id}`,
    kind,
    title: '虚构条目',
    time: 1700000000,
    sender: '甲',
    thread: [{ sender: '甲', time: 1700000000, text: c.text, media: [mediaOf(c)] }],
  };
}

const ITEMS = [
  ...CASES.map((c) => item('chat_record', c)),
  ...CASES.map((c) => item('single', c)),
];

const PIXEL = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
);

const STATIC = {
  '/index.html': ['text/html; charset=utf-8', 'index.html'],
  '/app.js': ['text/javascript; charset=utf-8', 'app.js'],
  '/styles.css': ['text/css; charset=utf-8', 'styles.css'],
};

let browser;
let context;
let page;

async function assertStage(expected) {
  const offenders = await page.locator('#stage *').evaluateAll((els) =>
    els.flatMap((el) =>
      [...el.attributes]
        .filter((a) => a.name.toLowerCase().startsWith('on'))
        .map((a) => `${el.tagName.toLowerCase()} ${a.name}`),
    ),
  );
  assert.deepEqual(offenders, []);
  assert.equal(await page.locator('#stage script').count(), 0);
  const imgs = page.locator('#stage img');
  assert.equal(await imgs.count(), expected.length);
  for (let i = 0; i < expected.length; i++) {
    const img = imgs.nth(i);
    const exp = expected[i];
    assert.equal(await img.getAttribute('src'), exp.src, `src ${i}`);
    if (exp.full !== undefined) assert.equal(await img.getAttribute('data-full'), exp.full, `full ${i}`);
    assert.equal(await img.getAttribute('data-fallback'), exp.fallback, `fb ${i}`);
  }
}

test.before(async () => {
  browser = await chromium.launch({ headless: true });
  context = await browser.newContext();
  page = await context.newPage();
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
    if (route.request().resourceType() === 'image') {
      await route.fulfill({ status: 200, contentType: 'image/png', body: PIXEL });
      return;
    }
    await route.abort();
  });
  await page.goto('http://127.0.0.1:9/index.html');
  await page.waitForSelector('#answerSheet .cell');
});

test.after(async () => {
  await context?.close();
  await browser?.close();
});

test('答题卡缩略图与记录详情', async () => {
  const sheetExpect = CASES.map((c) => ({ src: expectOf(c).src, fallback: expectOf(c).fallback }));
  assert.equal(await page.locator('#stage img').count(), CASES.length);
  await assertStage(sheetExpect.map((e) => ({ ...e, full: undefined })));
  const sheetImgs = page.locator('#answerSheet img');
  for (let i = 0; i < CASES.length; i++) {
    assert.equal(await sheetImgs.nth(i).getAttribute('data-full'), null);
  }

  for (const c of CASES) {
    await page.locator(`.cell[data-id="chat_record-${c.id}"]`).click();
    await page.waitForSelector('.cl-img');
    assert.equal(await page.locator('h2').innerText(), '虚构条目');
    assert.match(await page.locator('.cl-bubble p').innerText(), new RegExp(c.text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
    await assertStage([expectOf(c)]);
    await page.locator('#btnBackSheet').click();
    await page.waitForSelector('#answerSheet');
  }
});

test('单条详情', async () => {
  await page.locator('.tab[data-filter="single"]').click();
  await page.waitForSelector('.cell[data-id="single-cn"]');
  await assertStage(CASES.map((c) => ({ src: expectOf(c).src, fallback: expectOf(c).fallback, full: undefined })));

  for (const c of CASES) {
    await page.locator(`.cell[data-id="single-${c.id}"]`).click();
    await page.waitForSelector('.simple-media');
    assert.match(await page.locator('.simple-text').innerText(), new RegExp(c.text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
    await assertStage([expectOf(c)]);
    await page.locator('#btnBackSheet').click();
    await page.waitForSelector('#answerSheet');
  }
});

test('正常图片详情与 lightbox', async () => {
  await page.locator('.tab[data-filter="record"]').click();
  await page.waitForSelector('.cell[data-id="chat_record-cn"]');
  await page.locator('.cell[data-id="chat_record-cn"]').click();
  await page.waitForSelector('.cl-img');
  await page.locator('.cl-img').click();
  await page.waitForSelector('#lightbox:not([hidden])');
  assert.equal(await page.locator('#lbImg').getAttribute('src'), 'https://example.test/图片.png');
  assert.equal(await page.locator('#lbCounter').innerText(), '1 / 1');
  await page.keyboard.press('Escape');
  await page.waitForSelector('#lightbox', { state: 'hidden' });
});
