import mysql.connector
import sqlite3
import os
from datetime import datetime
import logging
from scraper.config import MYSQL_CONFIG, USE_MYSQL, DB_PATH, PRIMARY_SOURCE, BACKUP_SOURCES

logger = logging.getLogger("DatabaseManager")

class DatabaseManager:
    def __init__(self, use_mysql=USE_MYSQL):
        self.use_mysql = use_mysql
        self.mysql_config = MYSQL_CONFIG.copy()
        self.db_path = DB_PATH
        self.init_db()

    def get_connection(self):
        if self.use_mysql:
            try:
                # Connect to MySQL server
                conn = mysql.connector.connect(
                    host=self.mysql_config["host"],
                    port=self.mysql_config["port"],
                    user=self.mysql_config["user"],
                    password=self.mysql_config["password"],
                    database=self.mysql_config["database"],
                    charset=self.mysql_config["charset"],
                    autocommit=True
                )
                return conn
            except mysql.connector.Error as err:
                if err.errno == 1049:  # Unknown database
                    self._create_mysql_database()
                    return self.get_connection()
                logger.warning(f"MySQL connection failed ({err}). Falling back to SQLite.")
                self.use_mysql = False

        # SQLite fallback
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_mysql_database(self):
        try:
            conn = mysql.connector.connect(
                host=self.mysql_config["host"],
                port=self.mysql_config["port"],
                user=self.mysql_config["user"],
                password=self.mysql_config["password"]
            )
            cursor = conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.mysql_config['database']} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            conn.close()
            logger.info(f"Created MySQL database '{self.mysql_config['database']}' successfully.")
        except Exception as e:
            logger.error(f"Failed to create MySQL database: {e}")

    def init_db(self):
        """Initializes tables in MySQL or SQLite."""
        conn = self.get_connection()
        cursor = conn.cursor()

        if self.use_mysql:
            # MySQL syntax
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sources (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    domain VARCHAR(255) NOT NULL UNIQUE,
                    url VARCHAR(500) NOT NULL,
                    is_primary TINYINT(1) DEFAULT 0,
                    status VARCHAR(50) DEFAULT 'PENDING',
                    last_checked DATETIME NULL,
                    total_scraped_items INT DEFAULT 0,
                    failover_priority INT DEFAULT 99,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_bank (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    source_id INT NOT NULL,
                    source_url VARCHAR(768) NOT NULL UNIQUE,
                    title VARCHAR(500) NOT NULL,
                    authority_category VARCHAR(255) NOT NULL,
                    full_html_content LONGTEXT,
                    collected_date DATETIME NOT NULL,
                    wp_post_id INT NULL,
                    wp_synced_at DATETIME NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sub_pages (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    knowledge_bank_id INT NOT NULL,
                    sub_page_url VARCHAR(768) NOT NULL,
                    sub_page_title VARCHAR(500),
                    sub_page_html LONGTEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (knowledge_bank_id) REFERENCES knowledge_bank(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS attachments (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    knowledge_bank_id INT NOT NULL,
                    file_name VARCHAR(255) NOT NULL,
                    file_url VARCHAR(768) NOT NULL,
                    local_storage_path VARCHAR(500) NOT NULL,
                    file_size_bytes BIGINT DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (knowledge_bank_id) REFERENCES knowledge_bank(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS execution_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    source_id INT NULL,
                    run_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(50) NOT NULL,
                    items_scraped INT DEFAULT 0,
                    log_details TEXT,
                    error_message TEXT,
                    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
        else:
            # SQLite syntax
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    domain TEXT NOT NULL UNIQUE,
                    url TEXT NOT NULL,
                    is_primary INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'PENDING',
                    last_checked DATETIME,
                    total_scraped_items INTEGER DEFAULT 0,
                    failover_priority INTEGER DEFAULT 99,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_bank (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER NOT NULL,
                    source_url TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    authority_category TEXT NOT NULL,
                    full_html_content TEXT,
                    collected_date DATETIME NOT NULL,
                    wp_post_id INTEGER,
                    wp_synced_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sub_pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    knowledge_bank_id INTEGER NOT NULL,
                    sub_page_url TEXT NOT NULL,
                    sub_page_title TEXT,
                    sub_page_html TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (knowledge_bank_id) REFERENCES knowledge_bank(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS attachments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    knowledge_bank_id INTEGER NOT NULL,
                    file_name TEXT NOT NULL,
                    file_url TEXT NOT NULL,
                    local_storage_path TEXT NOT NULL,
                    file_size_bytes INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (knowledge_bank_id) REFERENCES knowledge_bank(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS execution_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER,
                    run_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    status TEXT NOT NULL,
                    items_scraped INTEGER DEFAULT 0,
                    log_details TEXT,
                    error_message TEXT,
                    FOREIGN KEY (source_id) REFERENCES sources(id)
                )
            """)
            conn.commit()

        self._migrate_schema(cursor)
        self._seed_sources(cursor, conn)
        conn.close()

    def _migrate_schema(self, cursor):
        """Ensures wp_post_id, wp_synced_at, content_hash, last_updated_at, notification_number, summary, published_date exist, and creates cron_settings and knowledge_bank_sources tables."""
        try:
            if self.use_mysql:
                cursor.execute("SHOW COLUMNS FROM sources LIKE 'failure_count'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE sources ADD COLUMN failure_count INT DEFAULT 0 AFTER status")

                cursor.execute("SHOW COLUMNS FROM knowledge_bank LIKE 'content_hash'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE knowledge_bank ADD COLUMN content_hash VARCHAR(64) NULL AFTER full_html_content")
                cursor.execute("SHOW COLUMNS FROM knowledge_bank LIKE 'notification_number'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE knowledge_bank ADD COLUMN notification_number VARCHAR(255) NULL AFTER authority_category")
                cursor.execute("SHOW COLUMNS FROM knowledge_bank LIKE 'summary'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE knowledge_bank ADD COLUMN summary TEXT NULL AFTER notification_number")
                cursor.execute("SHOW COLUMNS FROM knowledge_bank LIKE 'published_date'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE knowledge_bank ADD COLUMN published_date DATE NULL AFTER summary")
                cursor.execute("SHOW COLUMNS FROM knowledge_bank LIKE 'last_updated_at'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE knowledge_bank ADD COLUMN last_updated_at DATETIME NULL AFTER collected_date")
                cursor.execute("SHOW COLUMNS FROM knowledge_bank LIKE 'wp_post_id'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE knowledge_bank ADD COLUMN wp_post_id INT NULL AFTER collected_date")
                    cursor.execute("ALTER TABLE knowledge_bank ADD COLUMN wp_synced_at DATETIME NULL AFTER wp_post_id")

                cursor.execute("SHOW COLUMNS FROM execution_logs LIKE 'items_added'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE execution_logs ADD COLUMN items_added INT DEFAULT 0 AFTER items_scraped")
                    cursor.execute("ALTER TABLE execution_logs ADD COLUMN items_updated INT DEFAULT 0 AFTER items_added")
                    cursor.execute("ALTER TABLE execution_logs ADD COLUMN items_unchanged INT DEFAULT 0 AFTER items_updated")
                    cursor.execute("ALTER TABLE execution_logs ADD COLUMN wp_posts_updated INT DEFAULT 0 AFTER items_unchanged")

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS knowledge_bank_sources (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        knowledge_bank_id INT NOT NULL,
                        source_id INT NOT NULL,
                        source_url VARCHAR(768) NOT NULL UNIQUE,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (knowledge_bank_id) REFERENCES knowledge_bank(id) ON DELETE CASCADE,
                        FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cron_settings (
                        setting_key VARCHAR(100) PRIMARY KEY,
                        setting_value TEXT NULL,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
            else:
                cursor.execute("PRAGMA table_info(sources)")
                src_cols = [row[1] for row in cursor.fetchall()]
                if 'failure_count' not in src_cols:
                    cursor.execute("ALTER TABLE sources ADD COLUMN failure_count INTEGER DEFAULT 0")

                cursor.execute("PRAGMA table_info(knowledge_bank)")
                columns = [row[1] for row in cursor.fetchall()]
                if 'content_hash' not in columns:
                    cursor.execute("ALTER TABLE knowledge_bank ADD COLUMN content_hash TEXT")
                if 'notification_number' not in columns:
                    cursor.execute("ALTER TABLE knowledge_bank ADD COLUMN notification_number TEXT")
                if 'summary' not in columns:
                    cursor.execute("ALTER TABLE knowledge_bank ADD COLUMN summary TEXT")
                if 'published_date' not in columns:
                    cursor.execute("ALTER TABLE knowledge_bank ADD COLUMN published_date DATE")
                if 'last_updated_at' not in columns:
                    cursor.execute("ALTER TABLE knowledge_bank ADD COLUMN last_updated_at DATETIME")
                if 'wp_post_id' not in columns:
                    cursor.execute("ALTER TABLE knowledge_bank ADD COLUMN wp_post_id INTEGER")
                if 'wp_synced_at' not in columns:
                    cursor.execute("ALTER TABLE knowledge_bank ADD COLUMN wp_synced_at DATETIME")

                cursor.execute("PRAGMA table_info(execution_logs)")
                log_cols = [row[1] for row in cursor.fetchall()]
                if 'items_added' not in log_cols:
                    cursor.execute("ALTER TABLE execution_logs ADD COLUMN items_added INTEGER DEFAULT 0")
                if 'items_updated' not in log_cols:
                    cursor.execute("ALTER TABLE execution_logs ADD COLUMN items_updated INTEGER DEFAULT 0")
                if 'items_unchanged' not in log_cols:
                    cursor.execute("ALTER TABLE execution_logs ADD COLUMN items_unchanged INTEGER DEFAULT 0")
                if 'wp_posts_updated' not in log_cols:
                    cursor.execute("ALTER TABLE execution_logs ADD COLUMN wp_posts_updated INTEGER DEFAULT 0")

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS knowledge_bank_sources (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        knowledge_bank_id INTEGER NOT NULL,
                        source_id INTEGER NOT NULL,
                        source_url TEXT NOT NULL UNIQUE,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (knowledge_bank_id) REFERENCES knowledge_bank(id) ON DELETE CASCADE,
                        FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cron_settings (
                        setting_key TEXT PRIMARY KEY,
                        setting_value TEXT,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

            # Seed default cron settings if missing
            defaults = {
                "cron_enabled": "1",
                "cron_interval_hours": "24",
                "last_cron_run": "",
                "cron_secret_token": "ca_cron_secret_key_123"
            }
            for key, val in defaults.items():
                if self.use_mysql:
                    cursor.execute("""
                        INSERT INTO cron_settings (setting_key, setting_value)
                        VALUES (%s, %s) ON DUPLICATE KEY UPDATE setting_key=setting_key
                    """, (key, val))
                else:
                    cursor.execute("""
                        INSERT INTO cron_settings (setting_key, setting_value)
                        VALUES (?, ?) ON CONFLICT(setting_key) DO NOTHING
                    """, (key, val))
        except Exception as e:
            logger.warning(f"Schema migration warning: {e}")


    def _seed_sources(self, cursor, conn):
        if self.use_mysql:
            cursor.execute("""
                INSERT INTO sources (name, domain, url, is_primary, failover_priority, status)
                VALUES (%s, %s, %s, 1, 0, 'ACTIVE')
                ON DUPLICATE KEY UPDATE is_primary=1, failover_priority=0
            """, (PRIMARY_SOURCE["name"], PRIMARY_SOURCE["domain"], PRIMARY_SOURCE["url"]))

            for idx, backup in enumerate(BACKUP_SOURCES, start=1):
                cursor.execute("""
                    INSERT INTO sources (name, domain, url, is_primary, failover_priority, status)
                    VALUES (%s, %s, %s, 0, %s, 'PENDING')
                    ON DUPLICATE KEY UPDATE failover_priority=%s
                """, (backup["name"], backup["domain"], backup["url"], idx, idx))
        else:
            cursor.execute("""
                INSERT INTO sources (name, domain, url, is_primary, failover_priority, status)
                VALUES (?, ?, ?, 1, 0, 'ACTIVE')
                ON CONFLICT(domain) DO UPDATE SET is_primary=1, failover_priority=0
            """, (PRIMARY_SOURCE["name"], PRIMARY_SOURCE["domain"], PRIMARY_SOURCE["url"]))

            for idx, backup in enumerate(BACKUP_SOURCES, start=1):
                cursor.execute("""
                    INSERT INTO sources (name, domain, url, is_primary, failover_priority, status)
                    VALUES (?, ?, ?, 0, ?, 'PENDING')
                    ON CONFLICT(domain) DO UPDATE SET failover_priority=?
                """, (backup["name"], backup["domain"], backup["url"], idx, idx))
            conn.commit()

    def get_cron_settings(self):
        """Retrieves key-value dict of all cron settings."""
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True) if self.use_mysql else conn.cursor()
        cursor.execute("SELECT setting_key, setting_value FROM cron_settings")
        rows = cursor.fetchall()
        conn.close()
        settings = {}
        for r in rows:
            if isinstance(r, dict):
                settings[r["setting_key"]] = r["setting_value"]
            else:
                settings[r[0]] = r[1]
        return settings

    def update_cron_setting(self, key, value):
        """Updates or inserts a cron setting key-value pair."""
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if self.use_mysql:
            cursor.execute("""
                INSERT INTO cron_settings (setting_key, setting_value, updated_at)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value), updated_at = VALUES(updated_at)
            """, (key, value, now))
        else:
            cursor.execute("""
                INSERT INTO cron_settings (setting_key, setting_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value, updated_at = excluded.updated_at
            """, (key, value, now))
            conn.commit()
        conn.close()

    def update_source_status(self, source_id, status, total_scraped_delta=0):
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ph = "%s" if self.use_mysql else "?"
        query = f"""
            UPDATE sources 
            SET status = {ph}, last_checked = {ph}, total_scraped_items = total_scraped_items + {ph}
            WHERE id = {ph}
        """
        cursor.execute(query, (status, now, total_scraped_delta, source_id))
        if not self.use_mysql:
            conn.commit()
        conn.close()

    def get_source_by_domain(self, domain):
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True) if self.use_mysql else conn.cursor()
        ph = "%s" if self.use_mysql else "?"
        cursor.execute(f"SELECT * FROM sources WHERE domain = {ph}", (domain,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_all_sources(self):
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True) if self.use_mysql else conn.cursor()
        cursor.execute("SELECT * FROM sources ORDER BY failover_priority ASC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def record_source_failure(self, source_id):
        """Increments failure count and automatically downgrades failover priority if consecutive failures >= 3."""
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True) if self.use_mysql else conn.cursor()
        ph = "%s" if self.use_mysql else "?"
        
        cursor.execute(f"SELECT failure_count, failover_priority, name FROM sources WHERE id = {ph}", (source_id,))
        row = cursor.fetchone()
        if row:
            curr_fc = (row["failure_count"] if isinstance(row, dict) else row[0]) or 0
            curr_prio = (row["failover_priority"] if isinstance(row, dict) else row[1]) or 99
            name = (row["name"] if isinstance(row, dict) else row[2]) or "Source"
            
            new_fc = curr_fc + 1
            new_status = "UNHEALTHY" if new_fc >= 3 else "FAILED"
            new_prio = curr_prio + 10 if new_fc == 3 else curr_prio
            
            query = f"""
                UPDATE sources 
                SET failure_count = {ph}, status = {ph}, failover_priority = {ph}, last_checked = {ph}
                WHERE id = {ph}
            """
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(query, (new_fc, new_status, new_prio, now, source_id))
            if not self.use_mysql:
                conn.commit()
                
            if new_fc >= 3:
                logger.warning(f"Source '{name}' (ID {source_id}) has failed {new_fc} consecutive times! Priority demoted to {new_prio} and marked {new_status}.")
        conn.close()

    def reset_source_failure(self, source_id):
        """Resets failure count to 0 and restores active status upon successful operation."""
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = "%s" if self.use_mysql else "?"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        query = f"""
            UPDATE sources 
            SET failure_count = 0, status = 'ACTIVE', last_checked = {ph}
            WHERE id = {ph}
        """
        cursor.execute(query, (now, source_id))
        if not self.use_mysql:
            conn.commit()
        conn.close()

    def save_knowledge_item(self, source_id, source_url, title, authority_category, full_html_content, collected_date, content_hash=None, notification_number=None, summary=None, published_date=None):
        """
        Saves or updates a knowledge item using multi-attribute fallback change & duplicate detection:
        1. Match by source_url (or secondary linked source_url)
        2. Match by Reference/Notification Number + Category
        3. Match by Title + Published Date
        4. Match by Content Hash

        If duplicate update originates from a different backup source, links source to master post instead of creating duplicates.
        Returns tuple: (kb_id, status_str) where status_str is 'ADDED', 'UPDATED', 'LINKED', or 'UNCHANGED'.
        """
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True) if self.use_mysql else conn.cursor()
        ph = "%s" if self.use_mysql else "?"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        existing = None

        # 1. Primary Match: Exact source_url in knowledge_bank
        cursor.execute(f"SELECT id, source_url, content_hash, notification_number, summary, published_date, wp_post_id FROM knowledge_bank WHERE source_url = {ph}", (source_url,))
        existing = cursor.fetchone()

        # 1b. Secondary Match: Check if source_url exists in secondary linked sources table
        if not existing:
            cursor.execute(f"SELECT kb.id, kb.source_url, kb.content_hash, kb.notification_number, kb.summary, kb.published_date, kb.wp_post_id FROM knowledge_bank_sources kbs JOIN knowledge_bank kb ON kbs.knowledge_bank_id = kb.id WHERE kbs.source_url = {ph}", (source_url,))
            existing = cursor.fetchone()

        # 2. Multi-Attribute Fallback Match: Reference/Notification Number (if valid & not N/A)
        if not existing and notification_number and notification_number.strip().upper() not in ["N/A", "NONE", ""]:
            notif_clean = notification_number.strip()
            if len(notif_clean) >= 3:
                cursor.execute(f"SELECT id, source_url, content_hash, notification_number, summary, published_date, wp_post_id FROM knowledge_bank WHERE notification_number = {ph} AND authority_category = {ph}", (notif_clean, authority_category))
                existing = cursor.fetchone()

        # 3. Multi-Attribute Fallback Match: Title + Published Date (or exact Title match)
        if not existing and title and len(title.strip()) > 10:
            clean_title = title.strip()
            if published_date:
                cursor.execute(f"SELECT id, source_url, content_hash, notification_number, summary, published_date, wp_post_id FROM knowledge_bank WHERE title = {ph} AND (published_date = {ph} OR DATE(collected_date) = {ph})", (clean_title, published_date, published_date))
                existing = cursor.fetchone()
            if not existing:
                cursor.execute(f"SELECT id, source_url, content_hash, notification_number, summary, published_date, wp_post_id FROM knowledge_bank WHERE title = {ph} AND authority_category = {ph}", (clean_title, authority_category))
                existing = cursor.fetchone()

        # 4. Fallback Match: Content Hash Fingerprint
        if not existing and content_hash:
            cursor.execute(f"SELECT id, source_url, content_hash, notification_number, summary, published_date, wp_post_id FROM knowledge_bank WHERE content_hash = {ph}", (content_hash,))
            existing = cursor.fetchone()

        if existing:
            kb_id = existing["id"] if isinstance(existing, dict) else existing[0]
            existing_url = existing["source_url"] if isinstance(existing, dict) else existing[1]
            existing_hash = existing["content_hash"] if isinstance(existing, dict) else existing[2]

            # Check if this update comes from a DIFFERENT backup source URL -> Link to Master Post!
            if existing_url != source_url:
                try:
                    if self.use_mysql:
                        cursor.execute("INSERT IGNORE INTO knowledge_bank_sources (knowledge_bank_id, source_id, source_url) VALUES (%s, %s, %s)", (kb_id, source_id, source_url))
                    else:
                        cursor.execute("INSERT OR IGNORE INTO knowledge_bank_sources (knowledge_bank_id, source_id, source_url) VALUES (?, ?, ?)", (kb_id, source_id, source_url))
                        conn.commit()
                    logger.info(f"Cross-Source Duplicate Detected: Linked backup source URL ({source_url}) to Canonical Master Post ID #{kb_id}")
                except Exception as link_err:
                    logger.warning(f"Source linking notice: {link_err}")

                conn.close()
                return kb_id, "LINKED"

            # Same source URL: compare content hashes
            if content_hash and existing_hash and content_hash == existing_hash:
                conn.close()
                return kb_id, "UNCHANGED"
            else:
                # Content updated: update record
                if self.use_mysql:
                    query = """
                        UPDATE knowledge_bank
                        SET title = %s, authority_category = %s, notification_number = %s, summary = %s,
                            published_date = %s, full_html_content = %s, content_hash = %s,
                            last_updated_at = %s, wp_synced_at = NULL
                        WHERE id = %s
                    """
                    cursor.execute(query, (title, authority_category, notification_number, summary, published_date, full_html_content, content_hash, now, kb_id))
                else:
                    query = """
                        UPDATE knowledge_bank
                        SET title = ?, authority_category = ?, notification_number = ?, summary = ?,
                            published_date = ?, full_html_content = ?, content_hash = ?,
                            last_updated_at = ?, wp_synced_at = NULL
                        WHERE id = ?
                    """
                    cursor.execute(query, (title, authority_category, notification_number, summary, published_date, full_html_content, content_hash, now, kb_id))
                    conn.commit()

                cursor.execute(f"DELETE FROM sub_pages WHERE knowledge_bank_id = {ph}", (kb_id,))
                cursor.execute(f"DELETE FROM attachments WHERE knowledge_bank_id = {ph}", (kb_id,))
                if not self.use_mysql:
                    conn.commit()

                conn.close()
                return kb_id, "UPDATED"
        else:
            # New Item: ADDED
            if self.use_mysql:
                query = """
                    INSERT INTO knowledge_bank (source_id, source_url, title, authority_category, notification_number, summary, published_date, full_html_content, content_hash, collected_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (source_id, source_url, title, authority_category, notification_number, summary, published_date, full_html_content, content_hash, collected_date))
                kb_id = cursor.lastrowid
            else:
                query = """
                    INSERT INTO knowledge_bank (source_id, source_url, title, authority_category, notification_number, summary, published_date, full_html_content, content_hash, collected_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                cursor.execute(query, (source_id, source_url, title, authority_category, notification_number, summary, published_date, full_html_content, content_hash, collected_date))
                conn.commit()
                kb_id = cursor.lastrowid

            conn.close()
            return kb_id, "ADDED"

    def save_sub_page(self, knowledge_bank_id, sub_page_url, sub_page_title, sub_page_html):
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = "%s" if self.use_mysql else "?"
        query = f"""
            INSERT INTO sub_pages (knowledge_bank_id, sub_page_url, sub_page_title, sub_page_html)
            VALUES ({ph}, {ph}, {ph}, {ph})
        """
        cursor.execute(query, (knowledge_bank_id, sub_page_url, sub_page_title, sub_page_html))
        if not self.use_mysql:
            conn.commit()
        conn.close()

    def save_attachment(self, knowledge_bank_id, file_name, file_url, local_storage_path, file_size_bytes):
        conn = self.get_connection()
        cursor = conn.cursor()
        ph = "%s" if self.use_mysql else "?"
        query = f"""
            INSERT INTO attachments (knowledge_bank_id, file_name, file_url, local_storage_path, file_size_bytes)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
        """
        cursor.execute(query, (knowledge_bank_id, file_name, file_url, local_storage_path, file_size_bytes))
        if not self.use_mysql:
            conn.commit()
        conn.close()

    def add_execution_log(self, source_id, status, items_scraped, log_details, error_message=None, items_added=0, items_updated=0, items_unchanged=0, wp_posts_updated=0):
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ph = "%s" if self.use_mysql else "?"
        query = f"""
            INSERT INTO execution_logs (source_id, run_timestamp, status, items_scraped, items_added, items_updated, items_unchanged, wp_posts_updated, log_details, error_message)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """
        cursor.execute(query, (source_id, now, status, items_scraped, items_added, items_updated, items_unchanged, wp_posts_updated, log_details, error_message))
        last_id = cursor.lastrowid
        if not self.use_mysql:
            conn.commit()
        conn.close()
        return last_id


    def get_knowledge_items_for_sync(self, limit=50, force=False, item_id=None):
        """Fetches items from knowledge_bank to sync or re-sync to WordPress."""
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True) if self.use_mysql else conn.cursor()
        ph = "%s" if self.use_mysql else "?"
        
        where_clauses = []
        params = []
        
        if item_id is not None:
            where_clauses.append(f"kb.id = {ph}")
            params.append(item_id)
        elif not force:
            where_clauses.append("kb.wp_synced_at IS NULL")
            
        where_str = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        query = f"""
            SELECT kb.*, s.name as source_name, s.domain as source_domain
            FROM knowledge_bank kb
            LEFT JOIN sources s ON kb.source_id = s.id
            {where_str}
            ORDER BY kb.id ASC
            LIMIT {ph}
        """
        params.append(limit)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        items = [dict(r) for r in rows]

        # Fetch attachments for these items
        if items:
            item_ids = [it['id'] for it in items]
            in_clause = ",".join([ph] * len(item_ids))
            att_query = f"SELECT * FROM attachments WHERE knowledge_bank_id IN ({in_clause})"
            cursor.execute(att_query, item_ids)
            att_rows = cursor.fetchall()
            att_map = {}
            for att in att_rows:
                att_dict = dict(att)
                att_map.setdefault(att_dict['knowledge_bank_id'], []).append(att_dict)

            for it in items:
                it['attachments'] = att_map.get(it['id'], [])

        conn.close()
        return items

    def get_unsynced_knowledge_items(self, limit=50):
        """Fetches items from knowledge_bank that have not yet been synced to WordPress."""
        return self.get_knowledge_items_for_sync(limit=limit, force=False)

    def update_wp_sync_status(self, kb_id, wp_post_id):
        """Updates wp_post_id and wp_synced_at timestamp for a knowledge item."""
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ph = "%s" if self.use_mysql else "?"
        query = f"""
            UPDATE knowledge_bank
            SET wp_post_id = {ph}, wp_synced_at = {ph}
            WHERE id = {ph}
        """
        cursor.execute(query, (wp_post_id, now, kb_id))
        if not self.use_mysql:
            conn.commit()
        conn.close()

