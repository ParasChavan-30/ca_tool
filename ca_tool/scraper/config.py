import os

# Base Directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
DB_DIR = os.path.join(STORAGE_DIR, "db")
PDF_DIR = os.path.join(STORAGE_DIR, "pdfs")
LOG_DIR = os.path.join(STORAGE_DIR, "logs")

import json

# Ensure directories exist
for folder in [STORAGE_DIR, DB_DIR, PDF_DIR, LOG_DIR]:
    os.makedirs(folder, exist_ok=True)

from urllib.parse import urlparse

# Database Configuration (MySQL XAMPP, Railway & SQLite fallback)
USE_MYSQL = True

def _get_db_config():
    # 1. Check DATABASE_URL or MYSQL_URL first
    db_url = os.getenv("DATABASE_URL") or os.getenv("MYSQL_URL") or os.getenv("MYSQL_PRIVATE_URL")
    if db_url and db_url.startswith("mysql://"):
        try:
            parsed = urlparse(db_url)
            return {
                "host": parsed.hostname or "127.0.0.1",
                "port": parsed.port or 3306,
                "user": parsed.username or "root",
                "password": parsed.password or "",
                "database": parsed.path.lstrip("/") or "railway",
                "charset": "utf8mb4"
            }
        except Exception:
            pass

    # 2. Check explicit environment variables
    env_host = os.getenv("MYSQLHOST") or os.getenv("MYSQL_HOST") or os.getenv("DB_HOST")
    env_port = os.getenv("MYSQLPORT") or os.getenv("MYSQL_PORT") or os.getenv("DB_PORT")
    env_user = os.getenv("MYSQLUSER") or os.getenv("MYSQL_USER") or os.getenv("DB_USER")
    env_pass = os.getenv("MYSQLPASSWORD") if os.getenv("MYSQLPASSWORD") is not None else (os.getenv("MYSQL_PASSWORD") if os.getenv("MYSQL_PASSWORD") is not None else os.getenv("DB_PASS", os.getenv("DB_PASSWORD")))
    env_db = os.getenv("MYSQLDATABASE") or os.getenv("MYSQL_DATABASE") or os.getenv("DB_NAME")

    if env_host:
        return {
            "host": env_host,
            "port": int(env_port) if env_port else 3306,
            "user": env_user or "root",
            "password": env_pass if env_pass is not None else "",
            "database": env_db or "railway",
            "charset": "utf8mb4"
        }

    # 3. Fallback to db_config.json for local development
    config_file = os.path.join(BASE_DIR, "db_config.json")
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return {
                    "host": cfg.get("host", "127.0.0.1"),
                    "port": int(cfg.get("port", 3306)),
                    "user": cfg.get("user", "root"),
                    "password": cfg.get("password", ""),
                    "database": cfg.get("database", "catool_db"),
                    "charset": "utf8mb4"
                }
        except Exception:
            pass

    return {
        "host": "127.0.0.1",
        "port": 3306,
        "user": "root",
        "password": "",
        "database": "catool_db",
        "charset": "utf8mb4"
    }

MYSQL_CONFIG = _get_db_config()

DB_PATH = os.path.join(DB_DIR, "ca_knowledge.db")
LOCK_FILE = os.path.join(STORAGE_DIR, "scraper.lock")
LOG_FILE = os.path.join(LOG_DIR, "scraper.log")

# Primary Target Website
PRIMARY_SOURCE = {
    "name": "SCA & Associates",
    "domain": "scaca.in",
    "url": "https://scaca.in/",
    "is_primary": True
}

# 10 Backup Target Websites (Rotational Priority Queue)
BACKUP_SOURCES = [
    {"name": "Pankaj Lunker & Associates", "domain": "pankajlunkerassociates.com", "url": "https://pankajlunkerassociates.com/"},
    {"name": "Nexus Advisors", "domain": "nexusadvisors.co.in", "url": "https://nexusadvisors.co.in/"},
    {"name": "Shah Sol", "domain": "shahsol.com", "url": "https://shahsol.com/"},
    {"name": "Sujata Bharti", "domain": "sujatabharti.com", "url": "https://sujatabharti.com/"},
    {"name": "Step Ladder", "domain": "stepladder.in", "url": "https://stepladder.in/"},
    {"name": "Sunil Kapoor & Associates", "domain": "sunilkapoorandassociates.com", "url": "https://sunilkapoorandassociates.com/"},
    {"name": "Virendra Associates", "domain": "virendraassociates.com", "url": "https://virendraassociates.com/"},
    {"name": "Skymap Alliance", "domain": "skymapalliance.in", "url": "https://skymapalliance.in/"},
    {"name": "PPD & Company", "domain": "ppdandcompany.com", "url": "https://ppdandcompany.com/"},
    {"name": "SRG Finserv", "domain": "srgfinserv.com", "url": "https://srgfinserv.com/"},
]

# Scraper Settings
REQUEST_TIMEOUT = 8  # Optimal connection timeout (seconds)
MAX_SUBPAGES_PER_ITEM = None  # None = Unlimited sub-pages for section index pages
MAX_CRAWL_DEPTH = 4  # Deep/Recursive crawling depth limit (1 = section index pages, 2-4 = article/sub-item pages)
MAX_WORKERS = 25  # High-throughput optimal worker threads for fast concurrent scraping
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Link Discovery Keywords (for section index & deep recursive URL discovery)
DISCOVERY_KEYWORDS = [
    'laws', 'bulletins', 'notification', 'circular', 'resource',
    'income_tax', 'gst', 'corporate', 'audit', 'fema', 'act', 'rule',
    'utility', 'utilities', 'form', 'calculator', 'link'
]

# Category Keywords for Automatic Authority Classification (7 Primary Categories)
CATEGORY_KEYWORDS = {
    "Utilities": ["/resources/utilities/", "utilities", "utility"],
    "Acts": ["/laws/", "act", "acts"],
    "Forms": ["/resources/forms/", "forms", "form"],
    "Rules": ["rules", "rule"],
    "Bulletins": ["/resources/bulletins/", "bulletins", "bulletin"],
    "Calculators": ["/resources/calculators/", "calculators", "calculator"],
    "Links": ["/resources/links/", "links", "link"]
}

# Remote WordPress REST API Configuration
WP_CONFIG = {
    "base_url": os.getenv("WP_BASE_URL", "https://site40243-dn3p3f.scloudsite101.com/wp89265/wp-json"),
    "username": os.getenv("WP_USERNAME", "paras"),
    "application_password": os.getenv("WP_APP_PASSWORD", "4nZr IdgR nNjA uUfw wky5 JxKi"),  # Fill Application Password created under WP Profile
    "post_type": "knowledge_bank",  # Custom post type slug in ACF
    "timeout": 15,
    "batch_size": 25
}

