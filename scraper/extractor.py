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
        self.known_acronyms = {
            'rbi': 'RBI', 'sebi': 'SEBI', 'rbisebi': 'RBI SEBI', 'gst': 'GST',
            'vat': 'VAT', 'llp': 'LLP', 'fema': 'FEMA', 'tds': 'TDS',
            'indas': 'Ind AS', 'roc': 'ROC', 'nsc': 'NSC', 'hra': 'HRA',
            'nbfc': 'NBFC', 'nbfcs': 'NBFCs', 'cgst': 'CGST', 'sgst': 'SGST',
            'igst': 'IGST', 'utgst': 'UTGST', 'ifrs': 'IFRS', 'ifsc': 'IFSC',
            'micr': 'MICR', 'hsn': 'HSN', 'mrp': 'MRP', 'cst': 'CST',
            'cenvat': 'CENVAT', 'rera': 'RERA', 'mca': 'MCA', 'so': 'SO',
            'cbdt': 'CBDT', 'ita': 'ITA', 'ibc': 'IBC', 'f_e_m_a': 'FEMA'
        }
        self.generic_titles = {
            "notification/circular search", "notification search", "circular search",
            "search", "bulletins", "bulletin", "home", "welcome", "dashboard",
            "default page", "default", "login", "query", "knowledge bank entry",
            "suresh chandra & associates", "sca", "suresh chandra and associates",
            "pankaj lunker & associates", "nexus advisors", "shah sol", "sujata bharti",
            "step ladder", "sunil kapoor & associates", "virendra associates",
            "skymap alliance", "ppd & company", "srg finserv", "summary", "about us",
            "contact us", "our team", "careers", "page 1", "view details", "details",
            "about", "services", "sca's services", "the sca vision", "fully amortized",
            "important notes:", "important notes", "notes:", "notes", "note:", "note", "disclaimer", "instructions"
        }

    def is_generic_or_widget(self, text):
        """Checks if a string is a generic heading, navigation artifact, or date picker calendar widget."""
        if not text:
            return True
        t = text.strip()
        if len(t) < 2 or len(t) > 150:
            return True
        t_lower = t.lower()
        if t_lower in self.generic_titles:
            return True
        if "notification/circular search" in t_lower:
            return True
        # Check branding phrases
        if any(b in t_lower for b in ["suresh chandra", "pankaj lunker", "nexus advisors"]):
            return True
        # Calendar date picker artifacts like <<<November 2026>>> or November 2026
        if re.search(r'(<|&lt;){2,}.*?(>|&gt;){2,}', t, re.I) or re.search(r'<{2,}.*?>{2,}', t):
            return True
        if re.search(r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}\b', t_lower):
            return True
        # Calculator outputs like "Instalment Amount: RS.0", "Total Effective Capital: Rs.0", "No. Of Installment:0"
        if re.search(r':\s*(rs\.?\s*)?\d+', t_lower):
            return True
        return False

    def extract_title(self, soup, default_url="", menu_title=""):
        """
        Intelligent 4-tier title extraction system:
        Priority 1: Page-specific heading (with widget/calendar decomposition)
        Priority 2: Breadcrumb and navigation information
        Priority 3: HTML metadata (<title>, og:title, twitter:title)
        Priority 4: Intelligent URL hierarchy and slug parsing
        """
        # If a valid menu title was passed from navigation, use it if page heading is missing/generic
        if menu_title and not self.is_generic_or_widget(menu_title):
            candidate_menu = menu_title.strip()
        else:
            candidate_menu = None

        if soup:
            # Clone or clean soup to strip calendar popups, widgets, and navigation bars
            soup_clean = BeautifulSoup(str(soup), "html.parser")
            for tag in soup_clean.find_all(["nav", "header", "footer", "aside"]):
                tag.decompose()
            for tag in soup_clean.find_all(class_=lambda c: c and any(k in str(c).lower() for k in ["navbar", "nav-", "footer", "topbar", "raddock", "radpicker", "calendar", "rctitle", "datepicker"])):
                tag.decompose()
            for tag in soup_clean.find_all(id=lambda i: i and any(k in str(i).lower() for k in ["calendar", "datepicker", "datefrom", "dateto"])):
                tag.decompose()

            # Priority 1: Page-specific H1
            h1 = soup_clean.find("h1")
            if h1 and h1.get_text(strip=True):
                val = h1.get_text(strip=True)
                if not self.is_generic_or_widget(val):
                    return val

            # Priority 1b: Content H2 or H3
            for tag_name in ["h2", "h3"]:
                for elem in soup_clean.find_all(tag_name):
                    val = elem.get_text(strip=True)
                    if not self.is_generic_or_widget(val) and len(val) > 3:
                        return val

            # Priority 1c: Content heading classes
            content_header = soup_clean.find(class_=re.compile(r'page-title|entry-title|content-heading', re.I))
            if content_header and content_header.get_text(strip=True):
                val = content_header.get_text(strip=True)
                if not self.is_generic_or_widget(val):
                    return val

            # Priority 2: Breadcrumbs / Navigation items
            breadcrumb = soup.find(class_=lambda c: c and 'breadcrumb' in str(c).lower())
            if breadcrumb:
                items = [li.get_text(strip=True) for li in breadcrumb.find_all(['li', 'a', 'span'])]
                meaningful = [i for i in items if not self.is_generic_or_widget(i)]
                if meaningful:
                    return meaningful[-1]

            if candidate_menu:
                return candidate_menu

            # Priority 3: HTML Metadata (<title>, og:title, twitter:title)
            if soup.title and soup.title.get_text(strip=True):
                raw_title = soup.title.get_text(strip=True)
                parts = [p.strip() for p in re.split(r'\||-|–|—', raw_title)]
                for p in parts:
                    if not self.is_generic_or_widget(p):
                        return p

            for meta_prop in ['og:title', 'twitter:title']:
                m = soup.find('meta', property=meta_prop) or soup.find('meta', attrs={'name': meta_prop})
                if m and m.get('content'):
                    val = m.get('content').strip()
                    if not self.is_generic_or_widget(val):
                        return val

        if candidate_menu:
            return candidate_menu

        # Priority 4: Intelligent URL Hierarchy Extraction
        if default_url:
            clean_url = self.extract_title_from_url(default_url)
            if clean_url:
                return clean_url

        return "Knowledge Bank Entry"

    def clean_slug_to_title(self, slug):
        """Converts raw URL slugs into human-readable titles preserving acronyms."""
        if not slug:
            return ""
        slug = re.sub(r'\.(aspx|html|htm|php)$', '', slug, flags=re.I)
        slug = re.sub(r'^-?\d+[-_]', '', slug)
        if slug.lower() == 'f_e_m_a':
            return 'FEMA'
        
        # Split camelCase (e.g. HomeBuyerRefund -> Home Buyer Refund)
        slug = re.sub(r'([a-z])([A-Z])', r'\1 \2', slug)
        slug = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', slug)

        words = re.split(r'[-_\s]+', slug)
        clean_words = []
        for w in words:
            if not w:
                continue
            w_lower = w.lower()
            if w_lower in self.known_acronyms:
                clean_words.append(self.known_acronyms[w_lower])
            elif w.isupper() and len(w) <= 5:
                clean_words.append(w)
            else:
                clean_words.append(w.capitalize())
        res = " ".join(clean_words).strip()
        if res.lower().startswith('cal ') and 'calculator' not in res.lower():
            res = res[4:].strip() + ' Calculator'
        return res

    def extract_title_from_url(self, url):
        """Extracts a clean, human-readable title from URL hierarchy when HTML title is generic or missing."""
        if not url:
            return ""
        parsed = urllib.parse.urlparse(url)
        segments = [s for s in parsed.path.split('/') if s and s != '.aspx']
        if not segments:
            return ""

        ignored_segments = {
            'resources', 'laws', 'notificationsearch', 'advancesearch', 
            'notification', 'bullnotification', 'resource', 'ca_tool'
        }
        meaningful = [s for s in segments if s.lower() not in ignored_segments]
        if not meaningful:
            meaningful = segments

        candidate = meaningful[-1]
        title = self.clean_slug_to_title(candidate)
        if title.lower() in ['bulletins', 'calculators', 'forms', 'utilities', 'links', 'laws']:
            if len(meaningful) > 1:
                title = self.clean_slug_to_title(meaningful[-2])

        return title

    def classify_category(self, title, html_text, page_url=""):
        """
        Classifies the content into one of the 7 Primary Categories:
        Utilities, Acts, Forms, Rules, Bulletins, Calculators, Links.
        Prioritizes exact URL path patterns and title keywords.
        """
        url_lower = (page_url or "").lower()
        title_lower = (title or "").lower()

        # 1. Exact URL Path Matching (Highest Reliability)
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
        if "/notificationsearch/" in url_lower or "/advancesearch/" in url_lower or "/bulletins/" in url_lower or "/bulletin/" in url_lower:
            return "Bulletins"
        if "/laws/" in url_lower:
            if "rule" in url_lower or "rule" in title_lower:
                return "Rules"
            return "Acts"

        # 2. Title Keyword Matching (Strict on title to avoid matching navbar tokens in page body)
        if any(w in title_lower for w in ["calculator", "calculate", "mrp", "hra", "eml", "loan", "rera", "net profit", "net worth"]):
            return "Calculators"
        if any(w in title_lower for w in ["bulletin", "circular", "notification", "sebi", "rbi"]):
            return "Bulletins"
        if any(w in title_lower for w in ["rates of tds", "rates of income tax", "depreciation", "ifsc", "tds rate", "utility", "utilities"]):
            return "Utilities"
        if any(w in title_lower for w in ["form", "forms", "roc form", "cgst form", "declaration form"]):
            return "Forms"
        if any(w in title_lower for w in ["rule", "rules"]):
            return "Rules"
        if any(w in title_lower for w in ["act", "acts", "statute", "code", "amendment act"]):
            return "Acts"
        if any(w in title_lower for w in ["important link", "useful link", "links", "portal"]):
            return "Links"

        # 3. URL Token Path Matching
        if "calc" in url_lower:
            return "Calculators"
        if "bulletin" in url_lower or "notif" in url_lower or "circ" in url_lower:
            return "Bulletins"
        if "utilit" in url_lower:
            return "Utilities"
        if "form" in url_lower:
            return "Forms"
        if "rule" in url_lower:
            return "Rules"
        if "act" in url_lower or "law" in url_lower:
            return "Acts"
        if "link" in url_lower:
            return "Links"

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

    def extract_subpages(self, soup, base_url, max_subpages=5, session=None):
        """Discovers linked sub-pages strictly within the main content of this knowledge entry."""
        sub_pages = []
        base_domain = urllib.parse.urlparse(base_url).netloc
        visited = {base_url}
        http = session or requests

        # Clone and decompose navigation, headers, footers, and menu containers
        clean_soup = BeautifulSoup(str(soup), "html.parser")
        for tag in clean_soup.find_all(["nav", "header", "footer", "aside"]):
            tag.decompose()
        for tag in clean_soup.find_all(["div", "ul"], class_=lambda c: c and any(k in c.lower() for k in ["navbar", "nav-", "footer", "menu-container", "topbar"])):
            tag.decompose()

        for a in clean_soup.find_all("a", href=True):
            if max_subpages is not None and max_subpages > 0 and len(sub_pages) >= max_subpages:
                break

            href = a['href'].strip()
            if not href or href == '#' or any(href.lower().startswith(p) for p in ['javascript:', 'mailto:', 'tel:']):
                continue

            full_url = urllib.parse.urljoin(base_url, href.split('#')[0].strip())
            parsed = urllib.parse.urlparse(full_url)
            path = parsed.path.lower()

            # Only follow links on the same domain that belong strictly to Knowledge Bank
            if parsed.netloc == base_domain and full_url not in visited:
                # Exclude company/services pages
                if "/resource/" in path and "/resources/" not in path:
                    continue
                if any(bad in path for bad in ['/services/', '/team', '/about', '/contact', '/career', '/login', '/query', 'home.aspx', 'partner', 'vision', 'ifrs']):
                    continue
                # Must be a legitimate Knowledge Bank path
                if any(p in path for p in ['/laws/', '/resources/', '/notificationsearch/', '/advancesearch/']):
                    if any(ext in path for ext in ['.aspx', '.html', '.htm', '']) and not path.endswith('.pdf'):
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

