"""Open one SQLite connection per request, and close it afterwards."""
import sqlite3
from pathlib import Path
from flask import current_app, g


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'], timeout=30)
        g.db.row_factory = sqlite3.Row  # Use row['name'] instead of row[2].
        g.db.execute('PRAGMA foreign_keys = ON')
        g.db.execute('PRAGMA journal_mode = WAL')
    return g.db


def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    schema = Path(__file__).with_name('schema.sql').read_text(encoding='utf-8')
    get_db().executescript(schema)
