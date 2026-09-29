import mysql.connector
from scraper.config import MYSQL_CONFIG

def reset_mysql_db():
    print("Connecting to MySQL on port 3307...")
    conn = mysql.connector.connect(
        host=MYSQL_CONFIG["host"],
        port=MYSQL_CONFIG["port"],
        user=MYSQL_CONFIG["user"],
        password=MYSQL_CONFIG["password"],
        database=MYSQL_CONFIG["database"],
        autocommit=True
    )
    cursor = conn.cursor()

    # Drop existing tables to align schema
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
    tables = ['attachments', 'sub_pages', 'knowledge_bank', 'execution_logs', 'sources', 'sync_logs', 'updates']
    for t in tables:
        cursor.execute(f"DROP TABLE IF EXISTS `{t}`;")
        print(f"Dropped table `{t}`")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
    conn.close()
    print("MySQL database cleaned for schema alignment.")

if __name__ == "__main__":
    reset_mysql_db()
