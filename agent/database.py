import sqlite3
import os
from datetime import datetime, timedelta

# Path to our SQLite database file
DB_PATH = 'data/agent_memory.db'


def get_connection():
    """
    Creates and returns a connection to the SQLite database.
    Creates the data directory if it doesn't exist.
    """
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    # This makes rows behave like dictionaries
    # so you can access columns by name instead of index
    conn.row_factory = sqlite3.Row
    return conn


def initialise_runs_table():
    """
    Creates the agent_runs table if it doesn't exist.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agent_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_timestamp TEXT NOT NULL,
            emails_processed INTEGER DEFAULT 0,
            emails_deleted INTEGER DEFAULT 0
        )
    ''')

    conn.commit()
    conn.close()


def get_last_run_timestamp():
    """
    Returns the timestamp of the last successful run.
    If no previous run exists - defaults to 7 days ago.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT MAX(run_timestamp) FROM agent_runs')
    result = cursor.fetchone()
    conn.close()

    if result and result[0]:
        return result[0]
    else:
        # First run - default to 7 days ago
        seven_days_ago = datetime.now() - timedelta(days=7)
        return seven_days_ago.strftime('%Y/%m/%d')


def save_run(emails_processed, emails_deleted):
    """
    Saves a record of this agent run with current timestamp.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO agent_runs (run_timestamp, emails_processed, emails_deleted)
        VALUES (?, ?, ?)
    ''', (
        datetime.now().strftime('%Y/%m/%d'),
        emails_processed,
        emails_deleted
    ))

    conn.commit()
    conn.close()


def initialise_db():
    """
    Creates the gmail_agent table if it doesn't exist.
    Safe to run multiple times.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gmail_agent (
            serial_no INTEGER PRIMARY KEY AUTOINCREMENT,
            gmail_id TEXT UNIQUE NOT NULL,
            sender TEXT,
            subject TEXT,
            received_date TEXT,
            flag TEXT,
            decision TEXT,
            reason TEXT,
            user_approval TEXT DEFAULT 'pending'
        )
    ''')

    conn.commit()
    conn.close()


def is_already_processed(gmail_id):
    """
    Checks if an email has already been processed.
    Returns True if gmail_id exists in DB — this is our deduplication check.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        'SELECT 1 FROM gmail_agent WHERE gmail_id = ?',
        (gmail_id,)
    )

    result = cursor.fetchone()
    conn.close()

    return result is not None


def save_classification(email, classification):
    """
    Saves an email and its classification to the database.
    Skips if already processed — idempotency enforced at code level too.
    For spam emails, user_approval stays 'pending' until confirmed via WhatsApp.
    For keep emails, user_approval is set to 'na' (not applicable).
    """
    if is_already_processed(email['id']):
        return False

    conn = get_connection()
    cursor = conn.cursor()

    # Only spam emails need user approval — others are auto-approved
    approval_status = 'pending' if classification['decision'] == 'delete' else 'na'

    cursor.execute('''
        INSERT INTO gmail_agent 
        (gmail_id, sender, subject, received_date, flag, decision, reason, user_approval)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        email['id'],
        email['sender'],
        email['subject'],
        email['date'],
        classification['flag'],
        classification['decision'],
        classification['reason'],
        approval_status
    ))

    conn.commit()
    conn.close()
    return True


def get_pending_deletions():
    """
    Returns all emails marked for deletion but not yet approved by user.
    These are the emails awaiting WhatsApp confirmation.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT gmail_id, sender, subject, received_date, flag, reason
        FROM gmail_agent
        WHERE decision = 'delete' AND user_approval = 'pending'
        ORDER BY serial_no ASC
    ''')

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def update_approval_status(gmail_ids, status):
    """
    Updates user_approval for a list of gmail_ids.
    status: 'approved' | 'skipped'
    - approved: user confirmed deletion
    - skipped: user said no for this batch
    """
    if not gmail_ids:
        return

    conn = get_connection()
    cursor = conn.cursor()

    placeholders = ','.join('?' for _ in gmail_ids)
    cursor.execute(f'''
        UPDATE gmail_agent
        SET user_approval = ?
        WHERE gmail_id IN ({placeholders})
    ''', [status] + gmail_ids)

    conn.commit()
    conn.close()


def get_summary():
    """
    Returns a count of emails by flag for the daily summary notification.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT flag, decision, COUNT(*) as count 
        FROM gmail_agent 
        GROUP BY flag, decision
    ''')

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def clean_invalid_flags():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        DELETE FROM gmail_agent 
        WHERE flag NOT IN ('spam', 'job', 'news', 'alert')
    ''')
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    print(f"Cleaned {deleted} rows with invalid flags.")
