"""SSH-tunnelled PostgreSQL connection for the Recognition MVP dashboard."""
import os, threading, socket
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

_tunnel      = None
_tunnel_lock = threading.Lock()


def _start_tunnel():
    global _tunnel
    from sshtunnel import SSHTunnelForwarder
    _tunnel = SSHTunnelForwarder(
        (os.environ['PG_SSH_HOST'], int(os.environ['PG_SSH_PORT'])),
        ssh_username=os.environ['PG_SSH_USER'],
        ssh_password=os.environ['PG_SSH_PASSWORD'],
        remote_bind_address=(os.environ['PG_REMOTE_HOST'], int(os.environ['PG_REMOTE_PORT'])),
        set_keepalive=15,
    )
    _tunnel.start()
    return _tunnel


def _port_reachable(port, timeout=2):
    try:
        s = socket.create_connection(('127.0.0.1', port), timeout=timeout)
        s.close()
        return True
    except OSError:
        return False


def get_tunnel():
    global _tunnel
    import time
    with _tunnel_lock:
        if _tunnel is not None and _tunnel.is_active:
            if not _port_reachable(_tunnel.local_bind_port):
                try:
                    _tunnel.stop()
                except Exception:
                    pass
                _tunnel = None

        if _tunnel is None or not _tunnel.is_active:
            last_exc = None
            for attempt in range(3):
                try:
                    if _tunnel is not None:
                        try:
                            _tunnel.stop()
                        except Exception:
                            pass
                        _tunnel = None
                    _start_tunnel()
                    last_exc = None
                    break
                except Exception as exc:
                    last_exc = exc
                    if attempt < 2:
                        time.sleep(3)
            if last_exc is not None:
                raise last_exc
    return _tunnel


def get_pg_conn():
    import psycopg2
    tunnel = get_tunnel()
    conn = psycopg2.connect(
        host='127.0.0.1',
        port=tunnel.local_bind_port,
        dbname=os.environ['PG_DATABASE'],
        user=os.environ['PG_USER'],
        password=os.environ['PG_PASSWORD'],
    )
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SET lock_timeout = '30s'")
        # The heaviest read here is ~1.6k rows, but it crosses the SSH tunnel
        # and statement_timeout covers the whole round trip — so this is sized
        # for a slow tunnel minute, not for the server's execution time.
        cur.execute("SET statement_timeout = '180s'")
    return conn


def open_dedicated_tunnel():
    """A private tunnel on its own local port, for a long-running subprocess.

    dbt must NOT share the app's tunnel. get_tunnel() self-heals by stopping
    and restarting the shared forwarder whenever its local port stops
    answering, and flush_db() tears it down outright — either one yanks the
    port out from under a dbt run that is minutes long, which surfaces as
    "server closed the connection unexpectedly" and a failed rebuild.
    A dedicated forwarder isolates the two.

    The caller owns it and must .stop() it.
    """
    from sshtunnel import SSHTunnelForwarder
    tunnel = SSHTunnelForwarder(
        (os.environ['PG_SSH_HOST'], int(os.environ['PG_SSH_PORT'])),
        ssh_username=os.environ['PG_SSH_USER'],
        ssh_password=os.environ['PG_SSH_PASSWORD'],
        remote_bind_address=(os.environ['PG_REMOTE_HOST'], int(os.environ['PG_REMOTE_PORT'])),
        set_keepalive=15,
    )
    tunnel.start()
    return tunnel


def stop_tunnel():
    global _tunnel
    with _tunnel_lock:
        if _tunnel and _tunnel.is_active:
            try:
                _tunnel.stop()
            except Exception:
                pass
            _tunnel = None
