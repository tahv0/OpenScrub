const { chromium } = require('/tmp/openscrub-save-as-20261116/node_modules/playwright');
const assert = require('node:assert/strict'), fs = require('node:fs');
const root = '/tmp/openscrub-task620', url = 'http://127.0.0.1:18488';
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1365, height: 1000 } });
    const errors = [], warnings = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => { if (['error','warning'].includes(m.type())) warnings.push(m.text()); });
    page.on('dialog', d => d.dismiss());
    await page.goto(url);
    await page.getByRole('link', { name: 'synthetic-task620.avi', exact: true }).click();
    const save = page.getByRole('button', { name: 'Save edits & render', exact: true });
    await save.waitFor();
    await page.locator('#bb0').click();
    await page.locator('#bb0').click();
    assert.equal(await page.evaluate(() => EDITS.enabled[0]), false);
    let submitted, savedReport;
    const job = JSON.parse(fs.readFileSync(root + '/job.json'));
    await page.route('**/api/jobs/' + job.id + '/detections', async route => {
      if (route.request().method() !== 'POST') return route.continue();
      submitted = route.request().postDataJSON();
      const response = await route.fetch();
      savedReport = await (await page.request.get(url + '/api/jobs/' + job.id + '/report')).json();
      await route.fulfill({ response });
    });
    await save.click();
    await page.getByRole('status').filter({ hasText: 'Rendering with saved edits' }).waitFor();
    assert.deepEqual(submitted.enabled, { '0': false });
    assert.equal('audio' in submitted, false);
    const before = JSON.parse(fs.readFileSync(root + '/render-before.json'));
    assert.deepEqual(savedReport, before);
    let actual;
    for (let attempt = 0; attempt < 900; attempt++) {
      actual = await (await page.request.get(url + '/api/jobs/' + job.id + '?qa=' + Date.now())).json();
      if (actual.phase === 'error') throw Error(actual.error);
      if (actual.phase === 'done' && actual.has_output) break;
      await page.waitForTimeout(100);
    }
    assert.equal(actual.phase, 'done');
    assert.equal(actual.has_output, true);
    const after = await (await page.request.get(url + '/api/jobs/' + job.id + '/report')).json();
    fs.writeFileSync(root + '/render-after.json', JSON.stringify(after, null, 2));
    const identity = { url: page.url(), title: await page.title(),
      nonblank: (await page.locator('body').innerText()).includes('OpenScrub'),
      overlay: await page.locator('vite-error-overlay,nextjs-portal').count() };
    await page.screenshot({ path: root + '/browser-done.png', fullPage: true });
    assert.deepEqual(errors, []);
    assert.equal(identity.title, 'OpenScrub');
    assert.equal(identity.nonblank, true);
    assert.equal(identity.overlay, 0);
    const result = { browser: 'Chromium headless Linux', plugin: 'Browser plugin not available',
      viewport: '1365x1000', identity, errors, warnings, submitted, phase: actual.phase,
      savedRows: savedReport.detections.length, renderedRows: after.detections.length };
    fs.writeFileSync(root + '/browser-results.json', JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result, null, 2));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
