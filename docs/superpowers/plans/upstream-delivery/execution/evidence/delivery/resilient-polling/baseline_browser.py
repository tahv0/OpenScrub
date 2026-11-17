import ast
import subprocess


def pytest_runtest_call(item):
    if item.module.__name__ != 'test_job_polling_browser':
        return
    import openscrub_web as web
    source = subprocess.check_output(['git', 'show', '92124753736e287ac800af91f0ac96f3e96c01be:openscrub_web.py'], text=True)
    base = next(ast.literal_eval(n.value) for n in ast.parse(source).body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'APP_JS' for t in n.targets))
    web.PAGE = web.PAGE.replace(web.APP_JS, base)
