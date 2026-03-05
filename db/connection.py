
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA cache_size = -10000;")
    conn.execute("PRAGMA cache_size = -10000;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    return conn
    return conn




def connect(path: Optional[str] = None) -> sqlite3.Connection:
def connect(path: Optional[str] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(
    conn = sqlite3.connect(
        path or get_db_path(),
        path or get_db_path(),
        timeout=30,
        timeout=30,
        isolation_level=None,
        isolation_level=None,
        detect_types=sqlite3.PARSE_DECLTYPES,
        detect_types=sqlite3.PARSE_DECLTYPES,
    )
    )
    return configure_connection(conn)
    return configure_connection(conn)




@contextmanager
@contextmanager
def db_session(path: Optional[str] = None) -> Iterator[sqlite3.Connection]:
def db_session(path: Optional[str] = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    conn = connect(path)
    try:
    try:
        yield conn
        yield conn
    finally:
    finally:
        conn.close()
        conn.close()
