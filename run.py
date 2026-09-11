"""Production entry point — Waitress WSGI server.

A fresh deploy needs nothing but a filled-in .env. The two marts the page reads
are dbt tables built from four Airflow-maintained tables in `swiggydbo` plus one
seed, so on a database that has never had dbt run against it there is nothing to
read. Startup checks for them and runs a full `dbt build` if they are missing,
which also loads the seed — so there is no separate "run dbt first" step to
remember.
"""
import logging
import os
import sys

from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, '.env'))

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s | %(levelname)-7s | %(message)s')

REQUIRED_ENV = ['PG_SSH_HOST', 'PG_SSH_USER', 'PG_SSH_PASSWORD',
                'PG_REMOTE_HOST', 'PG_REMOTE_PORT',
                'PG_DATABASE', 'PG_USER', 'PG_PASSWORD']


def _check_env():
    if not os.path.exists(os.path.join(HERE, '.env')):
        print('\nERROR: .env not found.\n'
              '       Copy .env.example to .env and fill in the credentials:\n'
              '           copy .env.example .env\n')
        sys.exit(1)
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        print('\nERROR: .env is missing values for:\n'
              + ''.join(f'           {k}\n' for k in missing)
              + '       Fill them in and try again.\n')
        sys.exit(1)


def main():
    _check_env()
    port = int(os.environ.get('PORT', 5016))

    try:
        import data
        if not data.marts_exist():
            logging.info('Marts missing — running dbt build (first run)…')
            from run_dbt import main as dbt_main
            code = dbt_main()
            if code != 0:
                logging.error('Mart build failed. The app will start, but the '
                              'page will error until "python run_dbt.py" succeeds.')
    except Exception as exc:
        logging.error('Could not check/build marts: %s', exc)

    logging.info('Preloading marts…')
    try:
        import data
        data.preload()
        logging.info('Loaded %s response rows, %s manager-cycle rows, cycles: %s',
                     f'{len(data.responses()):,}', f'{len(data.managers()):,}',
                     ', '.join(data.cycles()))
    except Exception as exc:
        logging.error('Preload failed: %s', exc)
        logging.error('Starting anyway — the app will retry on first request.')

    from waitress import serve

    from app import server

    logging.info('Serving on http://127.0.0.1:%s', port)
    serve(server, host='0.0.0.0', port=port, threads=4)


if __name__ == '__main__':
    main()
