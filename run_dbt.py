"""Run the dbt models for the Recognition MVP dashboard.

Opens a dedicated SSH tunnel, exports PG_TUNNEL_PORT for profiles.yml to read,
then delegates to dbt. The tunnel is closed afterwards.

Usage:
    python run_dbt.py                                  # build (run + test)
    python run_dbt.py run --select mart_recog_awards
    python run_dbt.py test
"""
import os
import shutil
import subprocess
import sys

from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, '.env'))

DBT_DIR = os.path.join(HERE, 'dbt')


def find_dbt():
    """Locate the dbt executable.

    Also looks beside the running interpreter: pip installs dbt into Python's
    Scripts/ directory, which on a corporate Windows box is frequently absent
    from PATH, so shutil.which alone finds nothing even though dbt is installed.
    """
    explicit = os.environ.get('DBT_EXE', '').strip()
    if explicit:
        return explicit if os.path.exists(explicit) else None

    found = shutil.which('dbt')
    if found:
        return found

    scripts = os.path.join(os.path.dirname(sys.executable), 'Scripts')
    for name in ('dbt.exe', 'dbt'):
        cand = os.path.join(scripts, name)
        if os.path.exists(cand):
            return cand
    return None


def main():
    dbt_exe = find_dbt()
    if not dbt_exe:
        print('ERROR: dbt not found. Run "pip install -r requirements.txt", or '
              'set DBT_EXE in .env to the full path of dbt.exe.', file=sys.stderr)
        return 1

    # 'build' rather than 'run', so the uniqueness guards in the _*.yml files
    # actually execute. Those tests are the early-warning system for the two
    # failure modes that would otherwise show up as silently wrong numbers:
    # an employee-email join fanning out, and a non-numeric value turning a
    # guarded cast into a NULL.
    args = sys.argv[1:] or ['build']

    from pg_connection import open_dedicated_tunnel

    print('Opening SSH tunnel...')
    tunnel = open_dedicated_tunnel()
    os.environ['PG_TUNNEL_PORT'] = str(tunnel.local_bind_port)
    print(f'  Tunnel on port {tunnel.local_bind_port}')

    try:
        result = subprocess.run(
            [dbt_exe] + args + ['--profiles-dir', DBT_DIR, '--project-dir', DBT_DIR],
            capture_output=False, text=True,
        )
        return result.returncode
    finally:
        tunnel.stop()


if __name__ == '__main__':
    sys.exit(main())
