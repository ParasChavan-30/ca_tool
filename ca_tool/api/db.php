<?php
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

if (isset($_SERVER['REQUEST_METHOD']) && $_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit();
}

function getDBConnection() {
    $configFile = __DIR__ . '/../db_config.json';
    $host = '127.0.0.1';
    $port = 3307;
    $db = 'catool_db';
    $user = 'root';
    $pass = '';

    if (file_exists($configFile)) {
        $cfg = json_decode(file_get_contents($configFile), true);
        if ($cfg && is_array($cfg)) {
            $host = $cfg['host'] ?? $host;
            $port = $cfg['port'] ?? $port;
            $db = $cfg['database'] ?? $db;
            $user = $cfg['user'] ?? $user;
            $pass = $cfg['password'] ?? $pass;
        }
    }

    try {
        $pdo = new PDO("mysql:host={$host};port={$port};dbname={$db};charset=utf8mb4", $user, $pass, [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES => false,
        ]);
        
        static $migrated = false;
        if (!$migrated) {
            try {
                $pdo->exec("ALTER TABLE sources ADD COLUMN failure_count INT DEFAULT 0;");
            } catch (Exception $e) {}
            try {
                $pdo->exec("ALTER TABLE knowledge_bank ADD COLUMN notification_number VARCHAR(255) NULL AFTER authority_category;");
            } catch (Exception $e) {}
            try {
                $pdo->exec("ALTER TABLE knowledge_bank ADD COLUMN summary TEXT NULL AFTER notification_number;");
            } catch (Exception $e) {}
            try {
                $pdo->exec("ALTER TABLE knowledge_bank ADD COLUMN published_date DATE NULL AFTER summary;");
            } catch (Exception $e) {}
            try {
                $pdo->exec("CREATE TABLE IF NOT EXISTS knowledge_bank_sources (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    knowledge_bank_id INT NOT NULL,
                    source_id INT NOT NULL,
                    source_url VARCHAR(768) NOT NULL UNIQUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (knowledge_bank_id) REFERENCES knowledge_bank(id) ON DELETE CASCADE,
                    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;");
            } catch (Exception $e) {}
            try {
                $pdo->exec("INSERT IGNORE INTO cron_settings (setting_key, setting_value) VALUES ('retry_limits', '3'), ('request_timeout', '30');");
            } catch (Exception $e) {}
            $migrated = true;
        }
        
        return $pdo;
    } catch (PDOException $e) {
        echo json_encode([
            'success' => false,
            'error' => 'Database Connection Failed: ' . $e->getMessage()
        ]);
        exit();
    }
}
