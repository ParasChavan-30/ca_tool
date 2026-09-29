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

# Database Configuration (MySQL XAMPP, Railway & SQLite fallback)
USE_MYSQL = True
MYSQL_CONFIG = {
    "host": os.getenv("MYSQLHOST", os.getenv("DB_HOST", "127.0.0.1")),
    "port": int(os.getenv("MYSQLPORT", os.getenv("DB_PORT", 3307))),
    "user": os.getenv("MYSQLUSER", os.getenv("DB_USER", "root")),
    "password": os.getenv("MYSQLPASSWORD", os.getenv("DB_PASS", os.getenv("DB_PASSWORD", ""))),
    "database": os.getenv("MYSQLDATABASE", os.getenv("DB_NAME", "railway")),
    "charset": "utf8mb4"
}

CONFIG_FILE = os.path.join(BASE_DIR, "db_config.json")
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            if "host" in cfg and cfg["host"]: MYSQL_CONFIG["host"] = cfg["host"]
            if "port" in cfg and cfg["port"]: MYSQL_CONFIG["port"] = int(cfg["port"])
            if "user" in cfg and cfg["user"]: MYSQL_CONFIG["user"] = cfg["user"]
            if "password" in cfg: MYSQL_CONFIG["password"] = cfg["password"]
            if "database" in cfg and cfg["database"]: MYSQL_CONFIG["database"] = cfg["database"]
    except Exception:
        pass

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

