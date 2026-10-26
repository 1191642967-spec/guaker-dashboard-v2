#!/usr/bin/env node
/**
 * 从飞书公开分享链接抓取看板所需的 4 张表（访客身份，无需登录）
 * 原理：无头 Edge 打开页面 → 名称框选区（或 Ctrl+A）→ Ctrl+C → 读剪贴板 TSV
 * 输出：_cache/*.tsv
 * 依赖：puppeteer-core（NODE_PATH 指向 WorkBuddy node workspace）
 */
const path = require('path');
const fs = require('fs');
let puppeteer;
try { puppeteer = require('puppeteer-core'); }
catch (e) { puppeteer = require('C:/Users/20187/.workbuddy/binaries/node/workspace/node_modules/puppeteer-core'); }

const BASE = path.dirname(path.dirname(path.abspath ? '' : '')) || __dirname;
const PROJ = path.resolve(__dirname, '..');
const OUT = path.join(PROJ, '_cache');

const SHEETS = [
  { url: 'https://my.feishu.cn/wiki/XWwpwl073ifmjWkBO0FcU40Fn7b?sheet=nJjlbb', out: 'youxuan_sessions', range: null },
  { url: 'https://my.feishu.cn/wiki/XWwpwl073ifmjWkBO0FcU40Fn7b?sheet=e80Dru', out: 'youxuan_anchors',  range: 'A1:AZ50' },
  { url: 'https://my.feishu.cn/wiki/Be7lwLLzJimaA0kYrXhcSsWWnoD?sheet=dtjWao', out: 'guanfang_sessions', range: null },
  { url: 'https://my.feishu.cn/wiki/Be7lwLLzJimaA0kYrXhcSsWWnoD?sheet=q1dp44', out: 'guanfang_anchors',  range: 'A1:AZ50' },
];

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function grab(browser, { url, out, range }) {
  const page = await browser.newPage();
  const cdp = await page.createCDPSession();
  await cdp.send('Browser.grantPermissions', { permissions: ['clipboardReadWrite', 'clipboardSanitizedWrite'] });
  await page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
  await sleep(6000);
  if (/accounts\.feishu\.cn\/login/.test(page.url())) {
    console.error(`[${out}] 登录墙，抓取失败（分享权限可能被关闭）`);
    await page.close();
    return false;
  }
  if (range) {
    const handle = await page.evaluateHandle(() => {
      const inputs = [...document.querySelectorAll('input')];
      return inputs.find(i => /^[A-Z]{1,2}\d+$/.test((i.value || '').trim())) || null;
    });
    const el = handle.asElement();
    if (el) {
      await el.click(); await sleep(500);
      await page.keyboard.down('Control'); await page.keyboard.press('a'); await page.keyboard.up('Control');
      await page.keyboard.type(range, { delay: 30 });
      await page.keyboard.press('Enter'); await sleep(1200);
    } else {
      await page.mouse.click(840, 500);
      await page.keyboard.down('Control'); await page.keyboard.press('a'); await page.keyboard.up('Control');
    }
  } else {
    await page.mouse.click(840, 500); await sleep(1500);
    await page.keyboard.down('Control'); await page.keyboard.press('a'); await page.keyboard.up('Control');
  }
  await sleep(1000);
  await page.keyboard.down('Control'); await page.keyboard.press('c'); await page.keyboard.up('Control');
  await sleep(2500);
  const text = await page.evaluate(async () => {
    try { return await navigator.clipboard.readText(); } catch (e) { return 'ERR:' + e.message; }
  });
  if (text.startsWith('ERR:') || text.length < 50) {
    console.error(`[${out}] 剪贴板读取失败:`, text.slice(0, 80));
    await page.close();
    return false;
  }
  fs.writeFileSync(path.join(OUT, out + '.tsv'), '\ufeff' + text, 'utf8');
  const lines = text.split('\n');
  console.log(`[${out}] OK ${lines.length} rows, ${Math.max(...lines.map(l => l.split('\t').length))} cols`);
  await page.close();
  return true;
}

(async () => {
  if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--window-size=1700,1000', '--lang=zh-CN'],
    defaultViewport: { width: 1680, height: 950 },
  });
  let allOk = true;
  for (const s of SHEETS) allOk = (await grab(browser, s)) && allOk;
  await browser.close();
  console.log(allOk ? 'FETCH ALL OK' : 'FETCH PARTIAL FAIL');
  process.exit(allOk ? 0 : 1);
})();
