import threading

_conn      = None
_conn_lock = threading.RLock()


def _ping(conn):
    """Return True if conn can execute a trivial query."""
    try:
        cur = conn.cursor()
        cur.execute('SELECT 1')
        cur.close()
        return True
    except Exception:
        return False


def get_db():
    global _conn
    with _conn_lock:
        # Detect connections whose underlying tunnel died (psycopg2 won't
        # report .closed == 1 until we actually try to use the socket).
        if _conn is not None and not _conn.closed:
            if not _ping(_conn):
                # Connection is broken — flush conn + tunnel so get_pg_conn()
                # will rebuild both from scratch.
                flush_db()

        if _conn is None or _conn.closed:
            from pg_connection import get_pg_conn
            _conn = get_pg_conn()
            _raise_statement_timeout(_conn)
    return _conn


def _raise_statement_timeout(conn, ms=900000):
    """Lift the server's 3-minute statement_timeout for this session.

    marts.mart_ps_avp_respondents is 145k rows and mart_ps_responses 78k; a
    plain SELECT * over the SSH tunnel sits close to the server's 3-minute
    limit and intermittently trips it — which surfaces as a page that loads
    fine one minute and throws QueryCanceled the next. The reads are
    legitimately that big; the timeout is the wrong guard for them, so raise it
    per-session rather than shrink the frames the pages depend on.

    Best-effort: a role without permission to SET it still gets a working
    connection, just the server default.
    """
    try:
        with conn.cursor() as cur:
            cur.execute('SET statement_timeout = %s', (ms,))
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass


def flush_db():
    global _conn
    with _conn_lock:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None
    from pg_connection import stop_tunnel
    stop_tunnel()
