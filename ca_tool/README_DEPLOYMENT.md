# CA Knowledge Bank Tool - cPanel Deployment & Configuration Guide

## 1. Directory Structure on Host
The tool is uploaded to:
`public_html/ca_tool/`

Access the Web Dashboard at:
`http://yourdomain.com/ca_tool/`

---

## 2. Database Setup (cPanel MySQL)
1. Go to **cPanel -> MySQL Databases**.
2. Create a new database (e.g. `paras_catool`).
3. Create a new database user (e.g. `paras_catool`), set a strong password, and assign **ALL PRIVILEGES** to the database.
4. Open **cPanel -> phpMyAdmin**.
5. Select your database (`paras_catool`).
6. Click **Import**, select `schema.sql` from your `ca_tool` folder, and click **Go**.
7. Open `db_config.json` in `public_html/ca_tool/` and update your database credentials:
```json
{
  "host": "localhost",
  "port": 3306,
  "database": "paras_catool",
  "user": "paras_catool",
  "password": "YOUR_CPANEL_DB_PASSWORD"
}
```

---

## 3. Python Scraper Setup on cPanel
Your Python scraper runs automatically in background when triggered from the PHP Dashboard, or via cPanel Cron Jobs.

### Installing Python Dependencies:
In cPanel Terminal or SSH:
```bash
cd ~/public_html/ca_tool
pip3 install -r requirements.txt
```
*(Or `python3 -m pip install -r requirements.txt`)*

### Setting up Cron Job (Recommended for Automated Background Scraping):
1. Go to **cPanel -> Cron Jobs**.
2. Add a common interval (e.g. Once per hour or Twice per day):
```bash
python3 /home/paras/public_html/ca_tool/scraper/runner.py --once > /dev/null 2>&1
```
*(Adjust `/home/paras/` to match your home path if different)*.

---

## 4. WordPress Integration
The scraper automatically posts scraped knowledge items to WordPress.
Configuration is in `scraper/config.py` under `WP_CONFIG`:
- **Base URL**: `https://yourdomain.com/wp89265/wp-json`
- **Username**: `paras`
- **Application Password**: WP Profile -> Application Passwords
- **Custom Post Type**: `knowledge_bank`

---

## 5. Storage Permissions
Ensure the `storage/` directory in `public_html/ca_tool/` has write permissions (`0755` or `0777`):
- `storage/pdfs/`
- `storage/logs/`
- `storage/db/`
