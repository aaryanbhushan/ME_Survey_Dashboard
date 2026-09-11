"""Rebuild the dbt layer and reload the marts, without blocking the browser.

A full `dbt build` runs the staging models, the intermediate models, the marts,
the seed and the tests. That is minutes, not seconds, so it cannot happen
inside a Dash callback: the request would sit open until the browser gave up,
and the user would have no idea whether anything was happening.

So the work runs on a background thread and the page polls this module for
status. Three properties matter:

  ONE AT A TIME     a second click while a build is running is ignored rather
                    than starting a competing dbt process against the same
                    tables.
  CACHE LAST        the in-memory frames are only flushed AFTER dbt exits 0.
                    The old numbers keep serving throughout the build, which
                    is right: half-rebuilt marts are worse than stale ones.
  NEVER HALF-LOADED flush and preload happen together under the same guard, so
                    no request can observe an emptied cache.
"""
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# How much of dbt's output to keep for the UI. Enough to show what failed
# without holding the whole log in memory.
TAIL_LINES = 40

_lock = threading.Lock()
_state = {
    'state': 'idle',        # idle | running | done | error
    'message': '',
    'started': None,
    'finished': None,
    'tail': [],
    'returncode': None,
}


def status():
    with _lock:
        return dict(_state, tail=list(_state['tail']))


def is_running():
    with _lock:
        return _state['state'] == 'running'


def _set(**fields):
    with _lock:
        _state.update(fields)


def _run():
    import data

    started = time.time()
    _set(state='running', message='Building dbt models…', started=started,
         finished=None, tail=[], returncode=None)

    try:
        # A subprocess, not run_dbt.main() in-process: that function reads
        # sys.argv, which inside the server is the server's own command line,
        # and it opens its own SSH tunnel that must not outlive the build.
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, 'run_dbt.py')],
            cwd=HERE, capture_output=True, text=True,
            encoding='utf-8', errors='replace',
        )
        output = (proc.stdout or '') + (proc.stderr or '')
        tail = [ln for ln in output.splitlines() if ln.strip()][-TAIL_LINES:]

        if proc.returncode != 0:
            _set(state='error', returncode=proc.returncode, tail=tail,
                 finished=time.time(),
                 message=f'dbt failed (exit {proc.returncode}) — '
                         'the dashboard is still showing the previous data.')
            return

        _set(message='Reloading marts…', tail=tail)
        data.flush()
        data.preload()

        cycles = ', '.join(data.cycles())
        rows = len(data.responses())
        _set(state='done', returncode=0, finished=time.time(),
             message=f'Refreshed in {time.time() - started:.0f}s · '
                     f'{rows:,} response rows · cycles: {cycles}')
    except Exception as exc:                     # noqa: BLE001 - surfaced in UI
        _set(state='error', finished=time.time(),
             message=f'Refresh failed: {exc}',
             tail=list(_state.get('tail') or []))


def start():
    """Kick off a refresh. Returns False if one is already running."""
    with _lock:
        if _state['state'] == 'running':
            return False
        _state.update(state='running', message='Starting…',
                      started=time.time(), finished=None, tail=[],
                      returncode=None)
    threading.Thread(target=_run, name='ps-refresh', daemon=True).start()
    return True
