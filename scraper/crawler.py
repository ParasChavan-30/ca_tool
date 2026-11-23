import os
import re
import urllib.parse
import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from scraper.config import HTTP_HEADERS, REQUEST_TIMEOUT, MAX_SUBPAGES_PER_ITEM, MAX_WORKERS, DISCOVERY_KEYWORDS, EXCLUDED_KEYWORDS, MAX_CRAWL_DEPTH, get_proxy_dict
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

    def is_valid_knowledge_url(self, url, base_domain=None):
        """
        Validates that a URL belongs strictly to Knowledge Bank and excludes
        all non-knowledge pages like Home, Services, Team, Careers, Contact Us, About, etc.
        """
        if not url:
            return False

        parsed = urllib.parse.urlparse(url)
        if base_domain and parsed.netloc and parsed.netloc.lower() != base_domain.lower():
            return False

        path = parsed.path.lower()
        full_url_lower = url.lower()

        # 1. Reject static binary assets & media
        ignored_exts = ('.jpg', '.png', '.jpeg', '.gif', '.zip', '.css', '.js', '.docx', '.xlsx', '.ico', '.svg', '.mp4', '.mp3')
        if any(path.endswith(ext) or f"{ext}?" in full_url_lower for ext in ignored_exts):
            return False

        # 2. Strict Exclusions: corporate pages, services, about, career, etc.
        # Exclude /resource/ (singular) which holds company/services pages, but allow /resources/ (plural)
        if "/resource/" in path and "/resources/" not in path:
            return False

        # Blocked exact file basenames (case-insensitive)
        blocked_exact_basenames = [
            'home.aspx', 'about.aspx', 'about_us.aspx', 'about-us.aspx',
            'team.aspx', 'our_team.aspx', 'our-team.aspx', 'partners.aspx', 'partner.aspx',
            'the_sca_vision.aspx', 'vision.aspx', 'ifrs.aspx',
            'contact.aspx', 'contact_us.aspx', 'contact-us.aspx',
            'career.aspx', 'careers.aspx', 'query.aspx', 'newthemequerysheet.aspx',
            'login.aspx', 'admin.aspx', 'timesheet.aspx', 'disclaimer.aspx',
            'client.aspx', 'clients.aspx', 'feedback.aspx', 'services.aspx', 'service.aspx'
        ]
        basename = os.path.basename(path).lower()
        if basename in blocked_exact_basenames:
            return False

        # Blocked directory segments
        blocked_dirs = [
            '/services/', '/service/', '/team/', '/about/', '/contact/',
            '/career/', '/careers/', '/admin/', '/client/', '/clients/'
        ]
        if any(b_dir in path for b_dir in blocked_dirs):
            return False

        if any(token in full_url_lower for token in EXCLUDED_KEYWORDS):
            return False

        # 3. Must match Knowledge Bank areas (laws, resources, forms, utilities, bulletins, calculators, links, etc.)
        valid_prefixes = (
            '/laws/', '/resources/', '/utilities/', '/forms/',
            '/bulletins/', '/calculators/', '/links/',
            '/notificationsearch/', '/advancesearch/', '/notification/', '/circular/'
        )
        if any(p in path for p in valid_prefixes):
            return True

        # 4. Check for knowledge tokens in URL path segments
        kb_tokens = ['/act', '/rule', '/circular', '/bulletin', '/notification', '/utility', '/calculator', '/form']
        if any(t in path for t in kb_tokens):
            return True

        return False

    def discover_knowledge_bank_menu(self, base_url, html_content):
        """
        Dynamically discovers and extracts the complete Knowledge Bank menu hierarchy:
        Top-level categories (Calculators, Bulletins, Utilities, Links, Acts, Rules, Forms),
        all nested subcategories, sub-dropdowns, and destination URLs.
        Returns a dictionary mapping:
        url -> {
            'url': full_url,
            'menu_title': clean_title,
            'category': standardized_category,
            'subcategory': subcategory,
            'hierarchy': ' > '.join(path)
        }
        """
        if not html_content:
            return {}

        soup = BeautifulSoup(html_content, "html.parser")
        base_domain = urllib.parse.urlparse(base_url).netloc
        discovered_items = {}
        seen_urls = set()

        # Step 1: Locate Knowledge Bank navigation element and its dropdown container
        kb_menu = None
        for a in soup.find_all(['a', 'button']):
            text = a.get_text().strip().lower()
            if "knowledge bank" in text or "knowledge hub" in text:
                parent_li = a.find_parent("li")
                if parent_li:
                    kb_menu = parent_li.find("ul", class_=lambda c: c and "dropdown-menu" in c) or parent_li.find("ul")
                    if kb_menu:
                        break

        # Fallback: Check for id='submenu3', 'submenu5', or any id containing 'submenu'
        if not kb_menu:
            kb_menu = soup.find(id="submenu3") or soup.find(id="submenu5") or soup.find(id=lambda i: i and "submenu" in i.lower())

        if not kb_menu:
            logger.warning(f"Could not locate Knowledge Bank dropdown container on {base_url}. Falling back to page link discovery.")
            fallback_links = self.discover_knowledge_links(base_url, html_content)
            for link in fallback_links:
                cat = self.extractor.classify_category("", "", link)
                discovered_items[link] = {
                    "url": link,
                    "menu_title": "",
                    "category": cat,
                    "subcategory": "",
                    "hierarchy": f"Knowledge Bank > {cat}"
                }
            return discovered_items

        def standardize_category(raw_name):
            n = (raw_name or "").strip().lower()
            if "calc" in n:
                return "Calculators"
            if "bulletin" in n:
                return "Bulletins"
            if "utilit" in n:
                return "Utilities"
            if "link" in n:
                return "Links"
            if "act" in n:
                return "Acts"
            if "rule" in n:
                return "Rules"
            if "form" in n:
                return "Forms"
            return raw_name.strip()

        # Recursive traversal through nested <li> and <ul> tags
        def traverse(ul_element, path_stack):
            for li in ul_element.find_all("li", recursive=False):
                a_tag = li.find("a", recursive=False)
                if not a_tag:
                    continue

                raw_text = a_tag.get_text(strip=True).replace("\xa0", " ").strip()
                # Clean trailing arrow glyphs & indicators
                clean_title = raw_text
                for suffix in ["\u25b6", ">", "\u00bb", "▼", "caret"]:
                    clean_title = clean_title.rstrip(suffix).strip()

                current_path = path_stack + [clean_title] if clean_title else path_stack
                href = a_tag.get("href", "").strip()
                child_ul = li.find("ul", recursive=False)

                # Process destination URL if present and not a dummy toggle (#)
                if href and href != "#" and not any(href.lower().startswith(p) for p in ["javascript:", "mailto:", "tel:"]):
                    clean_href = href.split("#")[0].strip()
                    if clean_href:
                        full_url = urllib.parse.urljoin(base_url, clean_href)
                        if self.is_valid_knowledge_url(full_url, base_domain):
                            if full_url not in seen_urls and full_url.rstrip("/") != base_url.rstrip("/"):
                                seen_urls.add(full_url)
                                top_cat_raw = path_stack[0] if path_stack else clean_title
                                top_cat = standardize_category(top_cat_raw)
                                sub_cat = path_stack[1] if len(path_stack) > 1 else (clean_title if path_stack else "")
                                hierarchy_str = " > ".join(current_path)

                                discovered_items[full_url] = {
                                    "url": full_url,
                                    "menu_title": clean_title,
                                    "category": top_cat,
                                    "subcategory": sub_cat,
                                    "hierarchy": hierarchy_str
                                }

                # Recursively explore nested sub-menus
                if child_ul:
                    traverse(child_ul, current_path)

        traverse(kb_menu, [])

        # Log detailed discovery breakdown
        cat_counts = {}
        for item in discovered_items.values():
            c = item["category"]
            cat_counts[c] = cat_counts.get(c, 0) + 1
        breakdown = ", ".join([f"{k}: {v}" for k, v in sorted(cat_counts.items())])
        logger.info(f"Discovered {len(discovered_items)} Knowledge Bank items on {base_domain} ({breakdown})")

        return discovered_items

    def discover_knowledge_bank_menu_links(self, base_url, html_content):
        """Extracts ALL links from inside the 'Knowledge Bank' navigation dropdown menu."""
        items = self.discover_knowledge_bank_menu(base_url, html_content)
        return list(items.keys())

    def discover_knowledge_links(self, base_url, html_content):
        """
        Discovers child links, sub-pages, pagination, and articles strictly within the main content
        of a Knowledge Bank page (ignoring headers, footers, and general navigation bars).
        Strictly excludes any links outside the Knowledge Bank.
        """
        if not html_content:
            return []

        soup = BeautifulSoup(html_content, "html.parser")
        base_domain = urllib.parse.urlparse(base_url).netloc
        kb_links = set()

        # Remove navbars, headers, footers, and side menus to prevent re-crawling site-wide navigation
        for tag in soup.find_all(["nav", "header", "footer", "aside"]):
            tag.decompose()
        for tag in soup.find_all(["div", "ul"], class_=lambda c: c and any(k in c.lower() for k in ["navbar", "nav-", "footer", "menu-container", "topbar"])):
            tag.decompose()

        for a in soup.find_all("a", href=True):
            href = a['href'].strip()
            if not href or href == '#' or any(href.lower().startswith(prefix) for prefix in ['javascript:', 'mailto:', 'tel:']):
                continue

            clean_href = href.split('#')[0].strip()
            if not clean_href:
                continue

            full_url = urllib.parse.urljoin(base_url, clean_href)
            if self.is_valid_knowledge_url(full_url, base_domain):
                if full_url.rstrip('/') != base_url.rstrip('/'):
                    kb_links.add(full_url)

        return list(kb_links)

    def _scrape_single_page(self, url, source_id, session, menu_meta=None):
        """Scrapes a single Knowledge Bank page, its attachments, subpages, and discovers child links using delta hashing."""
        try:
            logger.info(f"Scraping Knowledge Bank page: {url}")
            proxy = get_proxy_dict()
            try:
                page_resp = session.get(url, headers=HTTP_HEADERS, timeout=REQUEST_TIMEOUT, proxies=proxy)
            except Exception as req_err:
                if proxy:
                    page_resp = session.get(url, headers=HTTP_HEADERS, timeout=REQUEST_TIMEOUT)
                else:
                    raise req_err

            if page_resp.status_code != 200:
                logger.warning(f"Skipping {url} - HTTP {page_resp.status_code}")
                return False, [], "FAILED"

            html_content = page_resp.text
            soup = BeautifulSoup(html_content, "html.parser")

            # Extract H1 Title (prioritizing H1 tag, fallback to exact menu title if generic)
            title = self.extractor.extract_title(soup, url)
            if menu_meta and menu_meta.get("menu_title"):
                generic_titles = ["knowledge bank entry", "home", "default", ""]
                if not title or title.lower() in generic_titles:
                    title = menu_meta["menu_title"]

            # Classify Authority / Category: prioritize menu hierarchy metadata
            if menu_meta and menu_meta.get("category"):
                category = menu_meta["category"]
            else:
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
            proxy = get_proxy_dict()
            resp = session.get(base_url, headers=HTTP_HEADERS, timeout=REQUEST_TIMEOUT, proxies=proxy)
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code} when fetching root page {base_url}")
            root_html = resp.text
        except Exception as e:
            err_msg = f"Failed to connect to source root {base_url}: {str(e)}"
            logger.error(err_msg)
            return 0, err_msg

        # Step 3: Discover initial Knowledge Bank section URLs (Level 1) strictly from Knowledge Bank menu hierarchy
        discovered_menu_items = self.discover_knowledge_bank_menu(base_url, root_html)
        initial_urls = set(discovered_menu_items.keys())
        logger.info(f"Discovered {len(initial_urls)} Knowledge Bank dropdown & submenu links on {domain}")

        if not initial_urls:
            logger.warning(f"No Knowledge Bank dropdown links discovered on {domain}.")
            return 0, "No Knowledge Bank links discovered.", {"scraped": 0, "added": 0, "updated": 0, "unchanged": 0}

        visited_urls = set()
        to_visit = initial_urls.copy()
        url_metadata = discovered_menu_items.copy()
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
                    meta = url_metadata.get(url)
                    futures[executor.submit(self._scrape_single_page, url, source_id, session, meta)] = (url, meta)

                for future in as_completed(futures):
                    url, parent_meta = futures[future]
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
                                    # Inherit category from parent if child doesn't have metadata yet
                                    if child_url not in url_metadata and parent_meta:
                                        url_metadata[child_url] = {
                                            "url": child_url,
                                            "menu_title": "",
                                            "category": parent_meta.get("category", "Acts"),
                                            "subcategory": parent_meta.get("subcategory", ""),
                                            "hierarchy": parent_meta.get("hierarchy", "") + " > Child Article"
                                        }
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

