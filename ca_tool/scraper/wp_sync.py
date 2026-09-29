import os
import sys
import re
import base64
import logging
import requests
from bs4 import BeautifulSoup
import urllib.parse
from datetime import datetime

# Ensure root directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.config import WP_CONFIG
from scraper.db_manager import DatabaseManager

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("WPSyncEngine")

class WordPressSyncEngine:
    def __init__(self, config=None, db_manager=None):
        self.config = config or WP_CONFIG
        self.db = db_manager or DatabaseManager()
        
        url_clean = self.config["base_url"].rstrip("/")
        if url_clean.endswith("/wp-json"):
            url_clean = url_clean[:-8].rstrip("/")
        self.base_url = url_clean

        self.username = self.config["username"]
        self.password = self.config["application_password"]
        self.post_type = self.config["post_type"]
        self.timeout = self.config.get("timeout", 15)
        self.session = requests.Session()
        self.session.verify = False  # Ignore self-signed or staging SSL issues
        
        # Set Basic Auth Header if credentials provided
        if self.username and self.password:
            user_pass = f"{self.username}:{self.password}"
            encoded = base64.b64encode(user_pass.encode("utf-8")).decode("utf-8")
            self.session.headers.update({
                "Authorization": f"Basic {encoded}"
            })

    def is_configured(self):
        """Checks if WordPress API authentication credentials are provided."""
        return bool(self.base_url and self.username and self.password)

    def test_connection(self):
        """Validates connection to remote WordPress REST API endpoint."""
        url = f"{self.base_url}/wp-json/wp/v2/users/me"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                user_data = resp.json()
                logger.info(f"Connected successfully to WP REST API as '{user_data.get('slug', self.username)}'")
                return {"success": True, "user": user_data.get("name", self.username)}
            else:
                err_msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.error(f"WP REST API auth failed: {err_msg}")
                return {"success": False, "error": err_msg}
        except Exception as e:
            logger.error(f"Connection to WP REST API failed: {e}")
            return {"success": False, "error": str(e)}

    def upload_pdf_attachment(self, local_path, file_name):
        """Uploads a local PDF to the Remote WordPress Media Library via REST API."""
        if not os.path.exists(local_path):
            logger.warning(f"Local PDF file not found for upload: {local_path}")
            return None

        url = f"{self.base_url}/wp-json/wp/v2/media"
        headers = {
            "Content-Type": "application/pdf",
            "Content-Disposition": f'attachment; filename="{file_name}"'
        }

        try:
            with open(local_path, "rb") as f:
                file_data = f.read()

            resp = self.session.post(url, headers=headers, data=file_data, timeout=self.timeout)
            if resp.status_code in [200, 201]:
                media_info = resp.json()
                remote_url = media_info.get("source_url")
                logger.info(f"Uploaded PDF to WP Media Library: {remote_url}")
                return remote_url
            else:
                logger.warning(f"Failed PDF upload to WP ({resp.status_code}): {resp.text[:150]}")
                return None
        except Exception as e:
                logger.error(f"Error uploading PDF to WP REST API: {e}")
                return None

    def clean_and_extract_html_content(self, raw_html, base_url):
        """
        Strips scraped site chrome (headers, logos, side nav, footers),
        rewrites all relative URLs to absolute URLs, and wraps the main document
        content in a responsive, styled wrapper matching the tool preview.
        """
        if not raw_html or not raw_html.strip():
            return ""

        soup = BeautifulSoup(raw_html, "html.parser")

        # 1. Remove script tags, noscript, iframes, and framebuster scripts
        for tag in soup.find_all(["script", "noscript", "iframe"]):
            tag.decompose()

        # 2. Identify and isolate main content container
        main_container = None

        selectors = [
            {"id": re.compile(r'^HomepagecontentControl', re.I)},
            {"id": re.compile(r'content_?control', re.I)},
            {"id": re.compile(r'main_?content', re.I)},
            {"class_": re.compile(r'main_?content|article_?body|document_?content', re.I)},
            {"id": re.compile(r'form1|aspnetform', re.I)}
        ]

        for sel in selectors:
            cand = soup.find(**sel)
            if cand and len(cand.get_text(strip=True)) > 50:
                main_container = cand
                break

        if not main_container:
            tables = soup.find_all("table")
            if tables:
                main_container = max(tables, key=lambda t: len(t.get_text(strip=True)))

        if not main_container:
            main_container = soup.body or soup

        container_soup = BeautifulSoup(str(main_container), "html.parser")

        # Decompose any site header, footer, top navbar, or sidebar navigation inside container
        chrome_patterns = re.compile(r'header|footer|top_?nav|side_?bar|menu_?list|footerrcontrol', re.I)
        for tag in container_soup.find_all(True):
            if not getattr(tag, 'attrs', None):
                continue
            t_id = str(tag.get('id', ''))
            t_class_val = tag.get('class', '')
            t_class = " ".join(t_class_val) if isinstance(t_class_val, list) else str(t_class_val)
            if (chrome_patterns.search(t_id) or chrome_patterns.search(t_class)) and len(tag.get_text(strip=True)) < 500:
                if tag.name != (container_soup.contents[0].name if container_soup.contents else ""):
                    tag.decompose()

        # Clean non-printable / replacement characters
        html_str = str(container_soup).replace('', '')
        container_soup = BeautifulSoup(html_str, "html.parser")

        # 3. Rewrite relative URLs to absolute URLs
        if base_url:
            parsed = urllib.parse.urlparse(base_url)
            domain_root = f"{parsed.scheme}://{parsed.netloc}"
            path = parsed.path or "/"
            dir_path = path[:path.rfind('/') + 1] if '/' in path else "/"
            base_dir = domain_root + dir_path

            def to_abs(url):
                url = (url or "").strip()
                if not url or url.startswith(('http://', 'https://', '//', 'data:', 'javascript:', 'mailto:', '#')):
                    return url
                if url.startswith('/'):
                    return domain_root + url
                return base_dir + url

            for tag in container_soup.find_all(True):
                for attr in ['href', 'src', 'action', 'poster', 'data-src']:
                    if tag.has_attr(attr):
                        tag[attr] = to_abs(tag[attr])

        inner_html = str(container_soup)

        styled_wrapper = f"""<div class="ca-kb-article-container" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #1e293b; background: #ffffff; padding: 20px; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); margin: 0 auto; max-width: 100%;">
  <style>
    .ca-kb-article-container table {{ width: 100% !important; border-collapse: collapse !important; margin: 16px 0 !important; font-size: 14px !important; }}
    .ca-kb-article-container table, .ca-kb-article-container th, .ca-kb-article-container td {{ border: 1px solid #cbd5e1 !important; padding: 10px 14px !important; text-align: left !important; }}
    .ca-kb-article-container th {{ background-color: #f1f5f9 !important; font-weight: 600 !important; color: #0f172a !important; }}
    .ca-kb-article-container tr:nth-child(even) {{ background-color: #f8fafc !important; }}
    .ca-kb-article-container tr:hover {{ background-color: #f1f5f9 !important; }}
    .ca-kb-article-container a {{ color: #2563eb !important; text-decoration: underline !important; font-weight: 500 !important; }}
    .ca-kb-article-container a:hover {{ color: #1d4ed8 !important; }}
    .ca-kb-article-container img {{ max-width: 100% !important; height: auto !important; border-radius: 4px !important; }}
    .ca-kb-article-container input[type="text"], .ca-kb-article-container select {{ padding: 6px 12px !important; border: 1px solid #cbd5e1 !important; border-radius: 4px !important; font-size: 14px !important; margin: 4px !important; }}
    .ca-kb-article-container input[type="submit"], .ca-kb-article-container button, .ca-kb-article-container .btn {{ background-color: #2563eb !important; color: #ffffff !important; border: none !important; padding: 8px 16px !important; border-radius: 4px !important; cursor: pointer !important; font-weight: 600 !important; font-size: 14px !important; margin: 4px !important; display: inline-block !important; text-decoration: none !important; }}
    .ca-kb-article-container input[type="submit"]:hover, .ca-kb-article-container button:hover {{ background-color: #1d4ed8 !important; }}
    .ca-kb-article-container .rdTable, .ca-kb-article-container .rgMasterTable {{ width: 100% !important; border-style: solid !important; border-color: #cbd5e1 !important; }}
  </style>
  {inner_html}
</div>"""
        return styled_wrapper.strip()

    def _extract_summary(self, html_content, max_len=300):
        """Extracts clean text summary from HTML content."""
        if not html_content:
            return ""
        soup = BeautifulSoup(html_content, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        if len(text) > max_len:
            return text[:max_len].rsplit(' ', 1)[0] + "..."
        return text

    def _extract_notification_number(self, title, html_content):
        """Attempts to extract circular/notification number using regex pattern matching."""
        combined = f"{title} {html_content[:500]}"
        patterns = [
            r'(?:notification|circular|bulletin|act|rule)\s*(?:no\.?|number|#)?\s*([a-zA-Z0-9/\-_]{3,25})',
            r'\b(\d{1,4}/\d{2,4})\b',
            r'\b([A-Z]{2,5}-\d{2,6})\b'
        ]
        for pattern in patterns:
            match = re.search(pattern, combined, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return "N/A"

    def sync_item(self, item):
        """Syncs or updates a single knowledge entry to the remote WordPress ACF Post Type."""
        wp_post_id = item.get("wp_post_id")
        if wp_post_id:
            post_url = f"{self.base_url}/wp-json/wp/v2/{self.post_type}/{wp_post_id}"
        else:
            post_url = f"{self.base_url}/wp-json/wp/v2/{self.post_type}"

        # Determine remote PDF attachment URL
        attachment_url = ""
        attachments = item.get("attachments", [])
        if attachments:
            att = attachments[0]
            local_path = att.get("local_storage_path", "")
            file_name = att.get("file_name", "attachment.pdf")
            
            # 1. Try uploading local PDF to WP Media Library
            remote_media_url = self.upload_pdf_attachment(local_path, file_name)
            if remote_media_url:
                attachment_url = remote_media_url
            else:
                # 2. Fallback to original scraped file URL
                attachment_url = att.get("file_url", "")

        title = item.get("title", "Knowledge Bank Record")
        raw_html = item.get("full_html_content", "")
        source_url = item.get("source_url", "")
        collected_date = str(item.get("collected_date", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        category = item.get("authority_category", "Acts")
        
        # Clean and extract main document HTML (removing site chrome & rewriting relative URLs)
        cleaned_html = self.clean_and_extract_html_content(raw_html, source_url)

        summary = self._extract_summary(cleaned_html or raw_html)
        notif_num = self._extract_notification_number(title, raw_html)

        # Build ACF Fields Payload according to 8 created ACF fields
        acf_payload = {
            "authority": item.get("source_name", "SCA & Associates"),
            "category": category,
            "notification_number": notif_num,
            "published_date": collected_date.split(" ")[0] if " " in collected_date else collected_date,
            "attachment_url": attachment_url,
            "source_url": source_url,
            "summary": summary,
            "collected_date": collected_date
        }

        wp_payload = {
            "title": title,
            "content": cleaned_html,
            "status": "publish",  # Publish post directly
            "acf": acf_payload
        }

        try:
            resp = self.session.post(post_url, json=wp_payload, timeout=self.timeout)
            if resp.status_code in [200, 201]:
                res_data = resp.json()
                res_wp_post_id = res_data.get("id", wp_post_id)
                
                # Update local DB record with WP Post ID and timestamp
                self.db.update_wp_sync_status(item["id"], res_wp_post_id)
                logger.info(f"Successfully {'updated' if wp_post_id else 'published'} WP Post ID {res_wp_post_id} for KB Item #{item['id']} ('{title[:40]}')")
                return {"success": True, "kb_id": item["id"], "wp_post_id": res_wp_post_id}
            else:
                err_msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.error(f"Failed WP REST sync for KB Item #{item['id']}: {err_msg}")
                return {"success": False, "kb_id": item["id"], "error": err_msg}
        except Exception as e:
            logger.error(f"Exception during WP sync for KB Item #{item['id']}: {e}")
            return {"success": False, "kb_id": item["id"], "error": str(e)}

    def sync_batch(self, limit=25, force=False, item_id=None):
        """Fetches and syncs a batch of items from local database to WordPress."""
        items = self.db.get_knowledge_items_for_sync(limit=limit, force=force, item_id=item_id)
        if not items:
            logger.info("No items found to sync in local database.")
            return {"synced_count": 0, "failed_count": 0, "total_pending": 0, "details": []}

        synced_count = 0
        failed_count = 0
        results = []

        logger.info(f"Starting WP REST sync batch for {len(items)} items...")
        for item in items:
            res = self.sync_item(item)
            results.append(res)
            if res.get("success"):
                synced_count += 1
            else:
                failed_count += 1

        # Count remaining unsynced items
        remaining = len(self.db.get_knowledge_items_for_sync(limit=1, force=False))
        return {
            "synced_count": synced_count,
            "failed_count": failed_count,
            "total_pending": remaining,
            "details": results
        }

if __name__ == "__main__":
    import sys
    import json
    logging.basicConfig(level=logging.INFO)
    engine = WordPressSyncEngine()
    if "--test" in sys.argv:
        print(json.dumps(engine.test_connection()))
    else:
        limit = 25
        force = False
        item_id = None
        for arg in sys.argv:
            if arg.startswith("--limit="):
                try:
                    limit = int(arg.split("=")[1])
                except ValueError:
                    pass
            elif arg in ["--force", "--all"]:
                force = True
            elif arg.startswith("--id="):
                try:
                    item_id = int(arg.split("=")[1])
                except ValueError:
                    pass

        res = engine.sync_batch(limit=limit, force=force, item_id=item_id)
        print(json.dumps(res))
