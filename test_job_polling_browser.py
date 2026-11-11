"""Job polling recovery against the real page and Flask routes.

Run with pytest -q test_job_polling_browser.py (Playwright + Chromium).
Only the stalled transport/body and browser lifecycle are simulated; the job
state, endpoints, rendering, cursor handling, and retry loop are production code.
"""
import json
from pathlib import Path
import threading

import pytest
from flask import jsonify
from werkzeug.serving import make_server

import openscrub_web as web
from test_review_browser import browser_instance, load_browser_page


@pytest.fixture
def polling_server(tmp_path, monkeypatch):
    jobs = {}
    for key, label in [('poll-alpha', 'Polling fixture A'),
                       ('poll-beta', 'Polling fixture B')]:
        directory = tmp_path / key
        directory.mkdir()
        jobs[key] = dict(id=key, dir=str(directory), video='', name=label,
                         phase='rendering', progress=.1, eta=None, error=None,
                         stats={}, log=[label + ' started'], output=None,
                         created=0, options={}, cancel=threading.Event(),
                         stop=threading.Event())
    monkeypatch.setattr(web, 'JOBS', jobs)
    monkeypatch.setattr(web, 'JOBS_DIR', str(tmp_path))
    monkeypatch.setattr(web, 'TOKEN', None)
    monkeypatch.setattr(web, 'openscrub_update', None)
    server = make_server('127.0.0.1', 0, web.app, threaded=True)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield 'http://127.0.0.1:%s' % server.server_port, jobs
    finally:
        server.shutdown()
        worker.join(timeout=5)


@pytest.fixture
def polling_page(polling_server):
    sync = pytest.importorskip('playwright.sync_api')
    url, _ = polling_server
    with sync.sync_playwright() as pw:
        browser = browser_instance(pw)
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        page.set_default_timeout(5000)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        load_browser_page(page, url, [], [])
        page.get_by_role('link', name='Polling fixture A', exact=True).wait_for()
        try:
            yield page
            assert not errors, errors
        finally:
            browser.close()


def stall_body_once(page, endpoint):
    """Model a response reader that never settles on transport cancellation.

    A normal browser Fetch body honours AbortSignal. An adapter, suspended
    transport, or separately pending body consumer may not. Returning headers
    alone must not let it hold the application's polling slot forever.
    """
    page.evaluate("""endpoint => {
      const original = window.fetch;
      let used = false;
      window.__bodyStalled = false;
      window.fetch = async (url, options) => {
        const response = await original(url, options);
        if (!used && String(url).split('?')[0].endsWith(endpoint)) {
          used = true;
          const data = await response.json();
          response.json = () => new Promise(resolve => {
            window.__releaseBody = () => resolve(data);
            window.__bodyStalled = true;
          });
        }
        return response;
      };
    }""", endpoint)


def open_alpha(page):
    page.get_by_role('link', name='Polling fixture A', exact=True).click()
    page.wait_for_function("document.querySelector('#log')?.textContent.includes('fixture A started')")


def test_request_deadline_covers_a_body_that_ignores_abort(polling_page):
    page = polling_page
    stall_body_once(page, 'api/jobs/poll-alpha')
    result = page.evaluate("""async () => Promise.race([
      reviewRequest('api/jobs/poll-alpha', {timeoutMs: 250})
        .then(() => 'unexpected success', error => error.name),
      new Promise(resolve => setTimeout(() => resolve('still pending'), 1000))
    ])""")
    assert page.evaluate('window.__bodyStalled')
    assert result == 'TimeoutError'


def test_switching_jobs_does_not_wait_for_a_stale_body(polling_page):
    page = polling_page
    stall_body_once(page, 'api/jobs/poll-alpha')
    page.get_by_role('link', name='Polling fixture A', exact=True).click()
    page.wait_for_function('window.__bodyStalled')
    page.get_by_role('link', name='Polling fixture B', exact=True).click()
    page.wait_for_function("document.querySelector('#log')?.textContent.includes('fixture B started')",
                           timeout=1200)
    page.evaluate('window.__releaseBody()')
    # A late A response must neither repaint B nor hold up B's next update.
    web.JOBS['poll-beta']['progress'] = .7
    web.JOBS['poll-beta']['log'].append('B remains current')
    page.wait_for_function("document.querySelector('#prog')?.value === .7")
    assert page.locator('#log').inner_text() == 'Polling fixture B started\nB remains current'


def test_slow_jobs_list_does_not_stop_selected_job_progress(polling_page):
    page = polling_page
    open_alpha(page)
    # Let the first complete refresh release both single-flight slots.
    page.evaluate('refresh()')
    page.evaluate('loadJobs()')
    stall_body_once(page, 'api/jobs')
    page.evaluate('void loadJobs()')
    page.wait_for_function('window.__bodyStalled')
    web.JOBS['poll-alpha']['progress'] = .3
    page.wait_for_function("document.querySelector('#prog').value === .3")
    web.JOBS['poll-alpha']['progress'] = .6
    web.JOBS['poll-alpha']['log'].append('Progress continues while list is slow')
    page.wait_for_function("document.querySelector('#prog').value === .6", timeout=2500)
    assert 'Progress continues while list is slow' in page.locator('#log').inner_text()


def test_hidden_poll_does_not_permanently_block_visible_updates(polling_page):
    page = polling_page
    open_alpha(page)
    page.evaluate('refresh()')
    page.evaluate("""async () => {
      Object.defineProperty(document, 'hidden', {configurable: true, value: true});
      await refresh();
      Object.defineProperty(document, 'hidden', {configurable: true, value: false});
    }""")
    web.JOBS['poll-alpha']['progress'] = .55
    web.JOBS['poll-alpha']['log'].append('Visible again')
    page.evaluate('refresh()')
    page.wait_for_function("document.querySelector('#prog').value === .55", timeout=1200)
    assert 'Visible again' in page.locator('#log').inner_text()


def test_wake_during_review_loading_cannot_rebuild_a_newer_view(polling_page):
    page = polling_page
    job = web.JOBS['poll-alpha']
    Path(job['dir'], 'report.json').write_text(json.dumps({
        'detections': [], 'render_state': {'fps': 30, 'cum': [[0, 0]] * 30}}))
    job['phase'] = 'review'
    stall_body_once(page, 'api/jobs/poll-alpha/detections')
    page.get_by_role('link', name='Polling fixture A', exact=True).click()
    page.wait_for_function('window.__bodyStalled')
    job['phase'], job['progress'] = 'rendering', .6
    page.evaluate("window.dispatchEvent(new Event('online'))")
    page.wait_for_function("document.querySelector('#prog').value === .6", timeout=1200)
    page.evaluate("async () => {window.__releaseBody();await new Promise(requestAnimationFrame);}")
    assert page.locator('#review').count() == 0
    page.get_by_role('button', name='Cancel render', exact=True).wait_for()


@pytest.mark.parametrize('event', ['visibilitychange', 'focus', 'pageshow', 'online'])
def test_lifecycle_resume_refreshes_immediately_during_backoff(polling_page, monkeypatch, event):
    page = polling_page
    open_alpha(page)
    page.evaluate('refresh()')
    page.evaluate('loadJobs()')
    original = web.app.view_functions['job_status']
    monkeypatch.setitem(web.app.view_functions, 'job_status',
                        lambda jid: (jsonify(error='Temporary fixture outage'), 503))
    page.evaluate('refresh()')
    assert 'interrupted' in page.locator('#jobsLoadStatus').inner_text()
    monkeypatch.setitem(web.app.view_functions, 'job_status', original)
    web.JOBS['poll-alpha']['progress'] = .65
    web.JOBS['poll-alpha']['log'].append('Recovered after ' + event)
    if event == 'visibilitychange':
        page.evaluate("""() => {
          Object.defineProperty(document, 'hidden', {configurable: true, value: true});
          document.dispatchEvent(new Event('visibilitychange'));
          Object.defineProperty(document, 'hidden', {configurable: true, value: false});
          document.dispatchEvent(new Event('visibilitychange'));
        }""")
    else:
        page.evaluate('event => window.dispatchEvent(new Event(event))', event)
    page.wait_for_function("document.querySelector('#prog').value === .65", timeout=1200)
    page.wait_for_function("document.querySelector('#log').textContent.includes('Recovered after')")


def test_transient_log_failure_recovers_without_reopening(polling_page, monkeypatch):
    page = polling_page
    original = web.app.view_functions['job_log']
    failed = []
    def flaky(jid):
        if not failed:
            failed.append(True)
            return jsonify(error='Temporary fixture outage'), 503
        return original(jid)
    monkeypatch.setitem(web.app.view_functions, 'job_log', flaky)
    page.get_by_role('link', name='Polling fixture A', exact=True).click()
    page.wait_for_function("document.querySelector('#jobsLoadStatus').textContent.includes('interrupted')")
    web.JOBS['poll-alpha']['progress'] = .8
    web.JOBS['poll-alpha']['log'].append('Recovered automatically')
    page.wait_for_function("document.querySelector('#log').textContent.includes('Recovered automatically')")
    assert page.locator('#prog').evaluate('(p) => p.value') == .8


def test_log_catchup_is_bounded_and_recovers_after_cursor_reset(polling_page):
    page = polling_page
    open_alpha(page)
    job = web.JOBS['poll-alpha']
    job['log'].extend('Synthetic log line %d' % i for i in range(2500))
    page.evaluate('refresh()')
    visible = page.locator('#log').inner_text().splitlines()
    assert visible[-1] == 'Synthetic log line 2499'
    assert len(visible) <= 400
    # A restarted/rehydrated server can have a shorter log for the same job.
    job['log'] = ['Restarted log', 'Fresh progress']
    page.evaluate('refresh()')
    assert page.locator('#log').inner_text() == 'Restarted log\nFresh progress'
    job['log'].append('Continued once')
    page.evaluate('refresh()')
    page.evaluate('refresh()')
    assert page.locator('#log').inner_text() == 'Restarted log\nFresh progress\nContinued once'


def test_log_endpoint_bounds_catchup_and_reports_reset(polling_server):
    _, jobs = polling_server
    job = jobs['poll-alpha']
    job['log'] = ['Synthetic log line %d' % i for i in range(2000)]
    with web.app.test_client() as client:
        data = client.get('/api/jobs/poll-alpha/log?from=1&limit=400').get_json()
        assert data['from'] == 1600
        assert data['len'] == 2000
        assert data['lines'] == job['log'][-400:]
        job['log'] = ['Restarted log']
        data = client.get('/api/jobs/poll-alpha/log?from=2000&limit=400').get_json()
        assert data['from'] == 0
        assert data['len'] == 1
        assert data['lines'] == ['Restarted log']


def test_log_cursor_never_acknowledges_a_line_appended_after_its_snapshot(polling_server):
    _, jobs = polling_server
    class AppendingLog(list):
        appended = False
        def __getitem__(self, key):
            result = super().__getitem__(key)
            if isinstance(key, slice) and not self.appended:
                self.appended = True
                self.append('Written during response')
            return result
    jobs['poll-alpha']['log'] = AppendingLog(['Original line'])
    with web.app.test_client() as client:
        first = client.get('/api/jobs/poll-alpha/log?from=0').get_json()
        assert first['lines'] == ['Original line']
        assert first['len'] == 1
        second = client.get('/api/jobs/poll-alpha/log?from=1').get_json()
        assert second['lines'] == ['Written during response']
        assert second['len'] == 2
