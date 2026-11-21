import requests
from urllib.parse import urlparse
import logging
from scraper.config import REQUEST_TIMEOUT, HTTP_HEADERS, get_proxy_dict
from scraper.db_manager import DatabaseManager

logger = logging.getLogger("Rotator")

class SourceRotator:
    def __init__(self, db_manager=None):
        self.db = db_manager or DatabaseManager()

    def check_site_health(self, url):
        """Sends a HEAD/GET request to test if a target site is reachable and responding."""
        proxies = get_proxy_dict()
        try:
            # First try HEAD for speed
            resp = requests.head(url, headers=HTTP_HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True, proxies=proxies)
            if resp.status_code == 200:
                return True, resp.status_code, "Site is online"
            
            # Fallback to GET if HEAD returned 405 or non-200
            resp = requests.get(url, headers=HTTP_HEADERS, timeout=REQUEST_TIMEOUT, stream=True, proxies=proxies)
            if resp.status_code == 200:
                return True, resp.status_code, "Site is online"
            return False, resp.status_code, f"HTTP Error {resp.status_code}"
        except requests.exceptions.Timeout:
            return False, 408, "Request timed out"
        except requests.exceptions.ConnectionError:
            # Try direct connection fallback if proxy connection failed
            try:
                resp = requests.head(url, headers=HTTP_HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
                if resp.status_code in [200, 301, 302]:
                    return True, resp.status_code, "Site is online (direct fallback)"
            except Exception:
                pass
            return False, 503, "Connection error / DNS failure"
        except Exception as e:
            return False, 500, f"Exception: {str(e)}"

    def get_active_scraping_source(self):
        """
        Probes sources in priority order.
        Returns (selected_source_dict, failover_logs_list).
        If primary is healthy, returns primary.
        Otherwise, iterates backup queue and returns first healthy backup.
        """
        sources = self.db.get_all_sources()
        failover_logs = []

        if not sources:
            raise Exception("No sources registered in database.")

        selected_source = None

        for source in sources:
            source_dict = dict(source)
            url = source_dict["url"]
            name = source_dict["name"]
            domain = source_dict["domain"]
            is_primary = source_dict["is_primary"]

            logger.info(f"Health checking target site: {name} ({url})...")
            is_healthy, status_code, message = self.check_site_health(url)

            if is_healthy:
                status_str = "ACTIVE" if is_primary else "ROTATED"
                self.db.reset_source_failure(source_dict["id"])
                self.db.update_source_status(source_dict["id"], status_str)
                selected_source = source_dict
                log_msg = f"Selected active site: {name} ({domain}) - Status: {status_str} [{message}]"
                failover_logs.append(log_msg)
                logger.info(log_msg)
                break
            else:
                self.db.record_source_failure(source_dict["id"])
                log_msg = f"Site DOWN: {name} ({domain}) - {message}. Triggering failover to next source..."
                failover_logs.append(log_msg)
                logger.warning(log_msg)

        if not selected_source:
            err_msg = "CRITICAL FAILOVER ERROR: All primary and backup CA websites are currently DOWN or unreachable!"
            failover_logs.append(err_msg)
            logger.error(err_msg)
            return None, failover_logs

        return selected_source, failover_logs
