# database/setup_db.py
import sqlite3
import os

# All three servers share one database file
DB_PATH = os.path.join(os.path.dirname(__file__), "it_ops.db")

def get_connection():
    """Returns a sqlite3 connection. Call this from any server."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # lets you access columns by name e.g. row["cpu"]
    return conn

def setup_database():
    """Creates all tables and seeds initial data if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    # ── Monitoring table ──────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS servers (
            name        TEXT PRIMARY KEY,
            cpu         INTEGER NOT NULL,
            memory      INTEGER NOT NULL,
            disk        INTEGER NOT NULL,
            status      TEXT NOT NULL CHECK(status IN ('healthy','warning','critical'))
        )
    """)

    # ── Ticketing table ───────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id          TEXT PRIMARY KEY,
            server_name TEXT NOT NULL,
            title       TEXT NOT NULL,
            priority    TEXT NOT NULL CHECK(priority IN ('low','medium','high','critical')),
            status      TEXT NOT NULL CHECK(status IN ('open','in_progress','resolved')),
            created     TEXT NOT NULL
        )
    """)

    # ── Inventory table ───────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            name        TEXT PRIMARY KEY,
            type        TEXT NOT NULL,
            os          TEXT NOT NULL,
            ram         TEXT NOT NULL,
            cpu_cores   INTEGER NOT NULL,
            location    TEXT NOT NULL,
            owner       TEXT NOT NULL,
            ip          TEXT NOT NULL,
            age_years   INTEGER NOT NULL
        )
    """)

    # ── Seed data (only if tables are empty) ─────────────────────
    # Monitoring seed
    cursor.execute("SELECT COUNT(*) FROM servers")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO servers VALUES (?,?,?,?,?)",
            [
                ("DB-01",  78, 85, 60, "warning"),
                ("WEB-01", 32, 45, 40, "healthy"),
                ("WEB-02", 91, 88, 75, "critical"),
                ("APP-01", 55, 62, 55, "healthy"),
            ]
        )

    # Ticketing seed
    cursor.execute("SELECT COUNT(*) FROM tickets")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO tickets VALUES (?,?,?,?,?,?)",
            [
                ("INC-001", "DB-01",  "High memory usage",       "high",     "open",        "2024-01-15"),
                ("INC-002", "WEB-02", "CPU spike intermittent",  "critical", "in_progress", "2024-01-16"),
                ("INC-003", "DB-01",  "Slow query performance",  "medium",   "open",        "2024-01-14"),
                ("INC-004", "APP-01", "Deployment failed",       "high",     "resolved",    "2024-01-13"),
                ("INC-005", "WEB-01", "SSL cert expiring soon",  "medium",   "open",        "2024-01-12"),
            ]
        )

    # Inventory seed
    cursor.execute("SELECT COUNT(*) FROM inventory")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO inventory VALUES (?,?,?,?,?,?,?,?,?)",
            [
                ("DB-01",  "Database Server",    "Ubuntu 22.04", "64GB", 16, "DC-East", "Database Team", "10.0.1.10", 3),
                ("WEB-01", "Web Server",         "Ubuntu 20.04", "16GB", 4,  "DC-East", "Web Team",      "10.0.1.11", 2),
                ("WEB-02", "Web Server",         "CentOS 7",     "16GB", 4,  "DC-West", "Web Team",      "10.0.2.11", 5),
                ("APP-01", "Application Server", "Ubuntu 22.04", "32GB", 8,  "DC-East", "App Team",      "10.0.1.12", 1),
            ]
        )

    conn.commit()
    conn.close()
    print(f"[DB] Database ready at: {DB_PATH}")

if __name__ == "__main__":
    setup_database()