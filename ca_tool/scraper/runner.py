import os
import sys
import argparse
import subprocess
import time
import logging
from datetime import datetime

# Adjust Python path to include ca_tool root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.config import LOCK_FILE, LOG_FILE
from scraper.db_manager import DatabaseManager
from scraper.rotator import SourceRotator
from scraper.crawler import WebsiteCrawler

# Configure File & Console Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("ScraperRunner")

class ScraperLock:
    """Manages PID lock file to prevent overlapping background runs."""
    def __init__(self, lock_file=LOCK_FILE):
        self.lock_file = lock_file

    def acquire(self):
        if os.path.exists(self.lock_file):
            try:
                with open(self.lock_file, "r") as f:
                    pid = int(f.read().strip())
                
                # Check if process is still running
                try:
                    import psutil
                    if psutil.pid_exists(pid):
                        logger.warning(f"Scraper process PID {pid} is already running. Skipping execution.")
                        return False
                except ImportError:
                    if sys.platform != "win32" and os.path.exists(f"/proc/{pid}"):
                        logger.warning(f"Scraper process PID {pid} is already running. Skipping execution.")
                        return False
            except Exception:
                # Stale lock file
                pass

        # Write current PID
        with open(self.lock_file, "w") as f:
            f.write(str(os.getpid()))
        return True

    def release(self):
        if os.path.exists(self.lock_file):
            try:
                os.remove(self.lock_file)
            except Exception as e:
                logger.warning(f"Error removing lock file: {str(e)}")

def run_scraper_job(is_cron=False, force=False, target_source_id=None):
    """Main execution job for the scraper with failover rotation, delta change logging, and cron support."""
    db = DatabaseManager()

    # Step 0: Check Cron Schedule if triggered via --cron
    if is_cron and not force:
        cron_settings = db.get_cron_settings()
        enabled = cron_settings.get("cron_enabled", "1") == "1"
        if not enabled:
            logger.info("Cron updater is disabled in settings. Aborting cron run.")
            return False

        interval_hours = int(cron_settings.get("cron_interval_hours", "24"))
        last_run_str = cron_settings.get("last_cron_run", "")

        if last_run_str:
            try:
                last_run_dt = datetime.strptime(last_run_str, "%Y-%m-%d %H:%M:%S")
                hours_since = (datetime.now() - last_run_dt).total_seconds() / 3600.0
                if hours_since < interval_hours:
                    logger.info(f"Cron interval check: Last run was {hours_since:.2f} hrs ago (interval: {interval_hours} hrs). Skipping execution.")
                    return True
            except Exception as dt_err:
                logger.warning(f"Error parsing last_cron_run timestamp: {dt_err}")

    rotator = SourceRotator(db)
    crawler = WebsiteCrawler(db)

    logger.info("==================================================")
    logger.info(f"Starting CA Knowledge Bank Scraper Job (Cron Mode: {is_cron}, Target Source ID: {target_source_id})")
    logger.info("==================================================")

    # Step 1: Health check & site rotator or single target source
    if target_source_id:
        active_source = db.get_source_by_id(target_source_id) if hasattr(db, 'get_source_by_id') else None
        if not active_source:
            sources = db.get_all_sources()
            for s in sources:
                if str(s.get("id")) == str(target_source_id):
                    active_source = s
                    break
        failover_logs = [f"Direct targeted manual sync requested for Source ID {target_source_id} ({active_source['name'] if active_source else 'Unknown'})."]
    else:
        active_source, failover_logs = rotator.get_active_scraping_source()

    log_summary = "\n".join(failover_logs)

    if not active_source:
        db.add_execution_log(
            source_id=None,
            status="FAILED",
            items_scraped=0,
            log_details=log_summary,
            error_message="All 11 CA target websites are unreachable."
        )
        logger.error("Job aborted: No active source available.")
        return False

    source_id = active_source["id"]
    status_flag = "SUCCESS" if active_source["is_primary"] else "FAILOVER"

    # Step 2: Execute Crawl on active source
    try:
        scraped_count, crawl_summary, metrics = crawler.scrape_source(active_source)
        full_log_details = f"{log_summary}\n{crawl_summary}"

        # Step 3: Automatic WordPress Sync batch for any remaining unsynced items
        wp_posts_updated = 0
        try:
            logger.info("Running automatic WordPress sync batch for remaining unsynced items...")
            from scraper.wp_sync import WordPressSyncEngine
            wp_engine = WordPressSyncEngine(db_manager=db)
            if wp_engine.is_configured():
                sync_res = wp_engine.sync_batch(limit=500)
                wp_posts_updated = sync_res.get("synced_count", 0)
                logger.info(f"Auto WP Sync summary: {wp_posts_updated} items synced, {sync_res.get('failed_count', 0)} failed, {sync_res.get('total_pending', 0)} pending.")
        except Exception as wp_err:
            logger.warning(f"Post-scraper job WP Sync error: {wp_err}")

        # Step 4: Record execution log with detailed delta metrics
        db.add_execution_log(
            source_id=source_id,
            status=status_flag,
            items_scraped=scraped_count,
            items_added=metrics.get("added", 0),
            items_updated=metrics.get("updated", 0),
            items_unchanged=metrics.get("unchanged", 0),
            wp_posts_updated=wp_posts_updated,
            log_details=full_log_details,
            error_message=None
        )

        # Step 5: Update last_cron_run timestamp in database settings
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.update_cron_setting("last_cron_run", now_str)

        logger.info(f"Scraper Job Finished Successfully! Total Scraped: {scraped_count} (Added: {metrics.get('added')}, Updated: {metrics.get('updated')}, Unchanged: {metrics.get('unchanged')})")
        return True
    except Exception as e:
        err_msg = f"Unhandled Scraper Exception: {str(e)}"
        logger.error(err_msg, exc_info=True)
        db.add_execution_log(
            source_id=source_id,
            status="FAILED",
            items_scraped=0,
            log_details=log_summary,
            error_message=err_msg
        )
        return False

def main():
    parser = argparse.ArgumentParser(description="CA Knowledge Bank Scraper & Background Job Runner")
    parser.add_argument("--background", action="store_true", help="Launch scraper job as an asynchronous background process")
    parser.add_argument("--once", action="store_true", help="Run scraper job once synchronously")
    parser.add_argument("--cron", action="store_true", help="Run in daily cron updater mode with interval check")
    parser.add_argument("--force", action="store_true", help="Force cron execution regardless of interval")
    parser.add_argument("--source-id", type=int, default=None, help="Target specific source ID for scraping")
    args = parser.parse_args()

    if args.background:
        # Launch non-blocking background process
        cmd = [sys.executable, __file__, "--cron" if args.cron else "--once"]
        if args.force:
            cmd.append("--force")
        if args.source_id:
            cmd.extend(["--source-id", str(args.source_id)])
        logger.info("Spawning background scraper worker process...")
        if sys.platform == "win32":
            CREATE_NO_WINDOW = 0x08000000
            subprocess.Popen(cmd, creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Scraper background worker process spawned successfully.")
        sys.exit(0)

    # Acquire PID Lock
    lock = ScraperLock()
    if not lock.acquire():
        sys.exit(1)

    try:
        run_scraper_job(is_cron=args.cron, force=args.force, target_source_id=args.source_id)
    finally:
        lock.release()

if __name__ == "__main__":
    main()

