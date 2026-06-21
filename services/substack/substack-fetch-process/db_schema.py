# db_schema.py
import sqlite3

def init_db(db_path='newsletters.db'):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS emails (
            id TEXT PRIMARY KEY,
            subject TEXT,
            sender TEXT,
            date TEXT,
            html TEXT,
            content_hash TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_content_hash ON emails(content_hash);
        
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT REFERENCES emails(id),
            url TEXT,
            local_path TEXT,
            image_hash TEXT,
            duplicate_of INTEGER REFERENCES images(id),
            vision_output TEXT,
            processed_at TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_image_hash ON images(image_hash);
        
        CREATE TABLE IF NOT EXISTS extracted_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT REFERENCES emails(id),
            data_type TEXT,
            content TEXT,
            extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS ticker_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT REFERENCES emails(id),
            ticker TEXT,
            action TEXT,
            sentiment TEXT,
            target_price REAL,
            stop_loss REAL,
            thesis TEXT,
            confidence TEXT,
            extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_ticker ON ticker_updates(ticker);
        CREATE INDEX IF NOT EXISTS idx_ticker_date ON ticker_updates(ticker, extracted_at);
        
        CREATE TABLE IF NOT EXISTS api_costs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cost_usd REAL,
            purpose TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS sync_state (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    ''')
    conn.commit()
    return conn
