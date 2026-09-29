import re
import urllib.parse
import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from scraper.config import HTTP_HEADERS, REQUEST_TIMEOUT, MAX_SUBPAGES_PER_ITEM, MAX_WORKERS, DISCOVERY_KEYWORDS, MAX_CRAWL_DEPTH
from scraper.extractor import DataExtractor
from scraper.db_manager import DatabaseManager
from scraper.wp_sync import WordPressSyncEngine

logger = logging.getLogger("Crawler")

class WebsiteCrawler:
    def __init__(self, db_manager=None, auto_sync_wp=False):
        self.db = db_manager or DatabaseManager()
        self.extractor = DataExtractor()
        self.auto_sync_wp = auto_sync_wp
        self.wp_engine = None

        if self.auto_sync_wp:
            try:
                engine = WordPressSyncEngine(db_manager=self.db)
                if engine.is_configured():
                    self.wp_engine = engine
                    logger.info("WordPress Auto-Sync is ENABLED and configured.")
            except Exception as e:
                logger.warning(f"Could not initialize WordPressSyncEngine for auto-sync: {e}")

    def discover_knowledge_links(self, base_url, html_content):
        """
        Finds all Knowledge Bank & section links on a page using expanded discovery keywords.
        Extracts all item links embedded inside tables, lists, and ASP.NET section view grids
        on submenu pages down to every individual article and act section page.
        """
        if not html_content:
            return []

        soup = BeautifulSoup(html_content, "html.parser")
        kb_links = set()
        base_domain = urllib.parse.urlparse(base_url).netloc

        for a in soup.find_all("a", href=True):
            href = a['href'].strip()
            if not href or any(href.lower().startswith(prefix) for prefix in ['javascript:', 'mailto:', 'tel:']):
                continue

            # Strip fragments
            clean_href = href.split('#')[0].strip()
            if not clean_href:
                continue

            full_url = urllib.parse.urljoin(base_url, clean_href)
            parsed = urllib.parse.urlparse(full_url)
            url_lower = full_url.lower()
            text_lower = a.get_text(strip=True).lower()

            # Ensure link belongs to target domain
            if parsed.netloc == base_domain:
                # Exclude static assets and binary files
                if not any(url_lower.endswith(ext) or f"{ext}?" in url_lower for ext in ['.pdf', '.jpg', '.png', '.jpeg', '.gif', '.zip', '.css', '.js', '.docx', '.xlsx', '.ico']):
                    # Exclude self-referential root URL
                    if full_url.rstrip('/') == base_url.rstrip('/'):
                        continue

                    # 1. Match discovery keywords in URL or link text
                    matches_keyword = any(k in url_lower for k in DISCOVERY_KEYWORDS) or any(k in text_lower for k in DISCOVERY_KEYWORDS)

                    # 2. Check if link is embedded inside data tables, lists, or ASP.NET section view grids
                    is_inside_data_container = False
                    parent = a.find_parent(['table', 'ul', 'ol', 'tbody', 'gridview', 'datalist'])
                    if parent is not None:
                        is_inside_data_container = True
                    else:
                        parent_div = a.find_parent('div')
                        if parent_div:
                            classes = " ".join(parent_div.get('class', [])).lower() if parent_div.get('class') else ""
                            div_id = str(parent_div.get('id', '')).lower()
                            if any(token in classes or token in div_id for token in ['grid', 'list', 'content', 'section', 'table', 'item', 'row', 'view', 'asp']):
                                is_inside_data_container = True

                    # 3. Check for primary category knowledge structure paths
                    is_knowledge_path = any(p in url_lower for p in ['/laws/', '/resources/', '/utilities/', '/forms/', '/bulletins/', '/calculators/', '/links/'])

                    # 4. Check for Pagination & Historical Archive links
                    is_pagination_or_archive = (
                        any(param in url_lower for param in ['page=', 'pg=', 'pageno=', 'p=', 'index=', 'year=']) or
                        any(arch in url_lower for arch in ['archive', 'past', 'history', 'old', 'circulars-', 'bulletins-']) or
                        bool(re.search(r'/(19|20)\d\d(/|\.|$)', url_lower)) or
                        any(token in text_lower for token in ['next', 'previous', 'prev', 'page', 'archive', '2025', '2024', '2023', '2022', '2021', '2020'])
                    )

                    if matches_keyword or is_inside_data_container or is_knowledge_path or is_pagination_or_archive:
                        kb_links.add(full_url)

        return list(kb_links)

    def _scrape_single_page(self, url, source_id, session):
        """Scrapes a single Knowledge Bank page, its attachments, subpages, and discovers child links using delta hashing."""
        try:
            logger.info(f"Scraping Knowledge Bank page: {url}")
            page_resp = session.get(url, headers=HTTP_HEADERS, timeout=REQUEST_TIMEOUT)
            if page_resp.status_code != 200:
                logger.warning(f"Skipping {url} - HTTP {page_resp.status_code}")
                return False, [], "FAILED"

            html_content = page_resp.text
            soup = BeautifulSoup(html_content, "html.parser")

            # Extract H1 Title (prioritizing H1 tag)
            title = self.extractor.extract_title(soup, url)

            # Classify Authority / Category
            category = self.extractor.classify_category(title, soup.get_text(), url)

            # Extract Extended Fields: Notification Number, Summary, Published Date
            notification_number = self.extractor.extract_notification_number(title, html_content)
            summary = self.extractor.extract_summary(html_content)
            published_date = self.extractor.extract_published_date(soup, html_content)

            collected_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Compute SHA-256 fingerprint hash of page HTML
            content_hash = hashlib.sha256(html_content.encode("utf-8")).hexdigest()

            # Save / Delta update Knowledge Bank entry in Database with extended fields & multi-attribute matching
            kb_id, status_str = self.db.save_knowledge_item(
                source_id=source_id,
                source_url=url,
                title=title,
                authority_category=category,
                full_html_content=html_content,
                collected_date=collected_date,
                content_hash=content_hash,
                notification_number=notification_number,
                summary=summary,
                published_date=published_date
            )

            if kb_id:
                # If page is newly ADDED or UPDATED, extract subpages and attachments
                if status_str in ["ADDED", "UPDATED"]:
                    attachments = self.extractor.extract_and_download_pdfs(soup, url, session=session)
                    for att in attachments:
                        self.db.save_attachment(
                            knowledge_bank_id=kb_id,
                            file_name=att["file_name"],
                            file_url=att["file_url"],
                            local_storage_path=att["local_storage_path"],
                            file_size_bytes=att["file_size_bytes"]
                        )

                    sub_pages = self.extractor.extract_subpages(soup, url, max_subpages=MAX_SUBPAGES_PER_ITEM, session=session)
                    for sub in sub_pages:
                        self.db.save_sub_page(
                            knowledge_bank_id=kb_id,
                            sub_page_url=sub["sub_page_url"],
                            sub_page_title=sub["sub_page_title"],
                            sub_page_html=sub["sub_page_html"]
                        )

                    # Auto-sync newly added or modified item to WordPress
                    if self.auto_sync_wp and self.wp_engine:
                        try:
                            sync_items = self.db.get_knowledge_items_for_sync(item_id=kb_id)
                            if sync_items:
                                sync_res = self.wp_engine.sync_item(sync_items[0])
                                if sync_res.get("success"):
                                    logger.info(f"Auto-synced ({status_str}) KB Item #{kb_id} ('{title[:30]}...') to WP Post #{sync_res.get('wp_post_id')}")
                                else:
                                    logger.warning(f"Auto-sync to WP failed for KB Item #{kb_id}: {sync_res.get('error')}")
                        except Exception as wp_err:
                            logger.warning(f"Auto-sync exception for KB Item #{kb_id}: {wp_err}")

                # Discover child article links for deep/recursive crawling
                child_links = self.discover_knowledge_links(url, html_content)

                return True, child_links, status_str
            return False, [], "FAILED"
        except Exception as e:
            logger.error(f"Error scraping page {url}: {str(e)}")
            return False, [], "FAILED"


    def scrape_source(self, source_dict, max_depth=MAX_CRAWL_DEPTH):
        """
        Crawls all Knowledge Bank pages from the active source dict recursively up to max_depth.
        Follows article links inside section pages concurrently & safely.
        Returns total_scraped count and execution log summary.
        """
        source_id = source_dict["id"]
        base_url = source_dict["url"]
        domain = source_dict["domain"]
        name = source_dict["name"]

        logger.info(f"Starting Knowledge Bank scrape for source: {name} ({base_url}) [Max Depth: {max_depth}]")

        # Step 1: Create reusable HTTP session with high-capacity connection pooling
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=2)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update(HTTP_HEADERS)

        # Step 2: Fetch Home / Portal Page
        try:
            resp = session.get(base_url, headers=HTTP_HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code} when fetching root page {base_url}")
            root_html = resp.text
        except Exception as e:
            err_msg = f"Failed to connect to source root {base_url}: {str(e)}"
            logger.error(err_msg)
            return 0, err_msg

        # Step 3: Discover initial Knowledge Bank section URLs (Level 1)
        initial_urls = set(self.discover_knowledge_links(base_url, root_html))
        logger.info(f"Discovered {len(initial_urls)} section index links on {domain}")

        if not initial_urls:
            # Fallback: scrape root page as a single entry if no sub-links found
            initial_urls = {base_url}

        visited_urls = set()
        to_visit = initial_urls.copy()
        scraped_count = 0
        added_count = 0
        updated_count = 0
        unchanged_count = 0
        error_count = 0
        current_depth = 1

        # Deep / Recursive multi-level crawling loop
        while to_visit and current_depth <= max_depth:
            logger.info(f"--- Crawling Level {current_depth}/{max_depth} ({len(to_visit)} URLs queued) ---")
            next_level_urls = set()
            workers = min(MAX_WORKERS, max(1, len(to_visit)))

            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {}
                for url in to_visit:
                    visited_urls.add(url)
                    futures[executor.submit(self._scrape_single_page, url, source_id, session)] = url

                for future in as_completed(futures):
                    url = futures[future]
                    try:
                        success, child_links, status_str = future.result()
                        if success:
                            scraped_count += 1
                            if status_str == "ADDED":
                                added_count += 1
                            elif status_str == "UPDATED":
                                updated_count += 1
                            elif status_str == "UNCHANGED":
                                unchanged_count += 1

                            # Add newly discovered article links inside section pages to next depth level
                            for child_url in child_links:
                                if child_url not in visited_urls and child_url not in to_visit:
                                    next_level_urls.add(child_url)
                        else:
                            error_count += 1
                    except Exception as exc:
                        logger.error(f"Error processing page {url}: {exc}")
                        error_count += 1

            to_visit = next_level_urls
            current_depth += 1

        # Update source metrics in database
        self.db.update_source_status(source_id, "ACTIVE", total_scraped_delta=scraped_count)

        metrics = {
            "scraped": scraped_count,
            "added": added_count,
            "updated": updated_count,
            "unchanged": unchanged_count,
            "errors": error_count
        }

        summary = f"Deep scrape completed for {name}. Total Scraped: {scraped_count} (New: {added_count}, Updated: {updated_count}, Unchanged: {unchanged_count}, Errors: {error_count}). Final Crawl Depth: {current_depth - 1}."
        logger.info(summary)
        return scraped_count, summary, metrics

