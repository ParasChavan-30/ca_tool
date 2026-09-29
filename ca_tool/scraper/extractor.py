import os
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import logging
from scraper.config import PDF_DIR, HTTP_HEADERS, REQUEST_TIMEOUT, CATEGORY_KEYWORDS

logger = logging.getLogger("Extractor")

class DataExtractor:
    def __init__(self, pdf_dir=PDF_DIR):
        self.pdf_dir = pdf_dir
        os.makedirs(self.pdf_dir, exist_ok=True)

    def extract_title(self, soup, default_url=""):
        """
        Extracts title prioritizing HTML <H1> header as requested.
        Handles generic site headers gracefully by cleaning URL basenames.
        """
        GENERIC_TITLES = [
            "suresh chandra & associates", "sca", "suresh chandra and associates",
            "pankaj lunker & associates", "nexus advisors", "shah sol", "sujata bharti",
            "step ladder", "sunil kapoor & associates", "virendra associates",
            "skymap alliance", "ppd & company", "srg finserv", "home"
        ]

        # 1. Try H1
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            val = h1.get_text(strip=True)
            if val.lower() not in GENERIC_TITLES:
                return val

        # 2. Try H2 or H3
        for tag_name in ["h2", "h3"]:
            for elem in soup.find_all(tag_name):
                val = elem.get_text(strip=True)
                if val and val.lower() not in GENERIC_TITLES and len(val) > 3:
                    return val

        # 3. Check for specific title elements
        content_header = soup.find(class_=re.compile(r'title|heading|caption', re.I))
        if content_header and content_header.get_text(strip=True):
            val = content_header.get_text(strip=True)
            if val.lower() not in GENERIC_TITLES:
                return val

        # 4. Fallback to clean URL path formatting
        if default_url:
            path = urllib.parse.urlparse(default_url).path
            basename = os.path.basename(path)
            # Remove extension (.aspx, .html)
            clean_name = re.sub(r'\.(aspx|html|htm)$', '', basename, flags=re.I)
            # Remove leading numeric ID prefix like -37- or -37_
            clean_name = re.sub(r'^-?\d+[-_]', '', clean_name)
            # Replace underscores and dashes with spaces
            clean_name = clean_name.replace('_', ' ').replace('-', ' ').strip()
            if clean_name:
                return clean_name

        # 5. Last resort: <title>
        if soup.title and soup.title.get_text(strip=True):
            raw_title = soup.title.get_text(strip=True)
            parts = [p.strip() for p in raw_title.split("|")]
            for p in parts:
                if p.lower() not in GENERIC_TITLES:
                    return p

        return "Knowledge Bank Entry"

    def classify_category(self, title, html_text, page_url=""):
        """
        Classifies the content into one of the 7 Primary Categories:
        Utilities, Acts, Forms, Rules, Bulletins, Calculators, Links.
        Prioritizes exact URL path patterns and title/content keywords.
        """
        url_lower = (page_url or "").lower()
        title_lower = (title or "").lower()

        # 1. Exact URL Path Matching
        if "/resources/utilities/" in url_lower:
            return "Utilities"
        if "/resources/forms/" in url_lower:
            return "Forms"
        if "/resources/bulletins/" in url_lower:
            return "Bulletins"
        if "/resources/calculators/" in url_lower:
            return "Calculators"
        if "/resources/links/" in url_lower:
            return "Links"
        if "/laws/" in url_lower:
            if "rule" in url_lower or "rule" in title_lower:
                return "Rules"
            return "Acts"

        # 2. Fallback to Title and Combined Text Keyword Matching
        combined = f"{title} {html_text} {page_url}".lower()
        if "utility" in combined or "utilities" in combined:
            return "Utilities"
        if "form" in combined or "forms" in combined:
            return "Forms"
        if "bulletin" in combined or "bulletins" in combined:
            return "Bulletins"
        if "calculator" in combined or "calculators" in combined:
            return "Calculators"
        if "link" in combined or "links" in combined:
            return "Links"
        if "rule" in combined:
            return "Rules"
        if "act" in combined or "laws" in combined:
            return "Acts"

        for category, keywords in CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in combined:
                    return category

        return "Acts"

    def _download_single_pdf(self, pdf_url, link_text, http):
        """Helper to download a single PDF attachment safely."""
        try:
            filename = os.path.basename(urllib.parse.urlparse(pdf_url).path)
            if not filename or not filename.lower().endswith(".pdf"):
                safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', link_text[:30])
                filename = f"document_{safe_name}_{int(datetime.now().timestamp())}.pdf"

            local_path = os.path.join(self.pdf_dir, filename)

            # Skip download if file already exists locally
            if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                file_size = os.path.getsize(local_path)
                logger.info(f"Skipped PDF download (already exists locally): {filename}")
                return {
                    "file_name": filename,
                    "file_url": pdf_url,
                    "local_storage_path": local_path,
                    "file_size_bytes": file_size
                }

            # Download PDF via HTTP session
            resp = http.get(pdf_url, headers=HTTP_HEADERS, timeout=REQUEST_TIMEOUT, stream=True)
            if resp.status_code == 200:
                with open(local_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)

                file_size = os.path.getsize(local_path)
                logger.info(f"Downloaded PDF attachment: {filename} ({file_size} bytes)")
                return {
                    "file_name": filename,
                    "file_url": pdf_url,
                    "local_storage_path": local_path,
                    "file_size_bytes": file_size
                }
        except Exception as e:
            logger.warning(f"Failed to download PDF {pdf_url}: {str(e)}")
        return None

    def extract_and_download_pdfs(self, soup, base_url, session=None):
        """
        Finds all PDF attachment links on the page, downloads them concurrently to local storage,
        and returns attachment metadata dict list.
        """
        attachments = []
        pdf_links = set()
        http = session or requests

        for a in soup.find_all("a", href=True):
            href = a['href'].strip()
            if href.lower().endswith(".pdf") or "pdf" in href.lower() or "download" in href.lower():
                full_url = urllib.parse.urljoin(base_url, href)
                if full_url.lower().endswith(".pdf") or ".pdf?" in full_url.lower():
                    pdf_links.add((full_url, a.get_text(strip=True) or "Download PDF"))

        if not pdf_links:
            return []

        # Download PDFs concurrently using ThreadPoolExecutor
        from concurrent.futures import ThreadPoolExecutor, as_completed
        workers = min(5, len(pdf_links))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(self._download_single_pdf, pdf_url, link_text, http)
                for pdf_url, link_text in pdf_links
            ]
            for future in as_completed(futures):
                res = future.result()
                if res:
                    attachments.append(res)

        return attachments

    def extract_subpages(self, soup, base_url, max_subpages=None, session=None):
        """Discovers linked sub-pages on the same website for this knowledge entry."""
        sub_pages = []
        base_domain = urllib.parse.urlparse(base_url).netloc
        visited = {base_url}
        http = session or requests

        for a in soup.find_all("a", href=True):
            if max_subpages is not None and max_subpages > 0 and len(sub_pages) >= max_subpages:
                break

            href = a['href'].strip()
            full_url = urllib.parse.urljoin(base_url, href)
            parsed = urllib.parse.urlparse(full_url)

            # Only follow sub-links on the same domain that are html/aspx pages
            if parsed.netloc == base_domain and full_url not in visited:
                if any(ext in parsed.path.lower() for ext in ['.aspx', '.html', '.htm', '']) and not parsed.path.lower().endswith('.pdf'):
                    visited.add(full_url)
                    try:
                        resp = http.get(full_url, headers=HTTP_HEADERS, timeout=REQUEST_TIMEOUT)
                        if resp.status_code == 200:
                            sub_soup = BeautifulSoup(resp.text, "html.parser")
                            sub_title = self.extract_title(sub_soup, full_url)
                            sub_pages.append({
                                "sub_page_url": full_url,
                                "sub_page_title": sub_title,
                                "sub_page_html": resp.text
                            })
                            logger.info(f"Extracted sub-page: {sub_title} ({full_url})")
                    except Exception as e:
                        logger.warning(f"Could not fetch sub-page {full_url}: {str(e)}")

        return sub_pages

    def extract_notification_number(self, title, html_content):
        """Extracts circular/notification number using regex pattern matching."""
        combined = f"{title} {html_content[:1000]}"
        patterns = [
            r'(?:notification|circular|bulletin|act|rule)\s*(?:no\.?|number|#)?\s*([a-zA-Z0-9/\-_]{3,30})',
            r'\b(\d{1,4}/\d{2,4})\b',
            r'\b([A-Z]{2,5}-\d{2,6})\b'
        ]
        for pattern in patterns:
            match = re.search(pattern, combined, re.IGNORECASE)
            if match:
                val = match.group(1).strip()
                if len(val) >= 3 and not val.lower().startswith(('http', 'www', 'aspx', 'html')):
                    return val
        return "N/A"

    def extract_summary(self, html_content, max_len=300):
        """Extracts clean text summary from HTML content."""
        if not html_content:
            return ""
        soup = BeautifulSoup(html_content, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        if len(text) > max_len:
            return text[:max_len].rsplit(' ', 1)[0] + "..."
        return text

    def extract_published_date(self, soup, html_text=""):
        """Extracts publication date from text using regex or fallback to today."""
        combined = f"{soup.get_text()} {html_text[:500]}"
        date_patterns = [
            r'\b(\d{1,2}[-/\.](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[-/\.]\d{2,4})\b',
            r'\b(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{4})\b',
            r'\b(\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2})\b'
        ]
        for pat in date_patterns:
            match = re.search(pat, combined, re.IGNORECASE)
            if match:
                raw_d = match.group(1)
                for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y", "%d-%b-%Y", "%d/%b/%Y"):
                    try:
                        dt = datetime.strptime(raw_d, fmt)
                        return dt.strftime("%Y-%m-%d")
                    except ValueError:
                        pass
        return datetime.now().strftime("%Y-%m-%d")

