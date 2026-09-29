<?php
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

if (isset($_SERVER['REQUEST_METHOD']) && $_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit();
}

function getPythonCmd() {
    if (getenv('PYTHON_PATH')) {
        return getenv('PYTHON_PATH');
    }
    if (strtoupper(substr(PHP_OS, 0, 3)) === 'WIN') {
        return 'python';
    }
    $output = @shell_exec('which python3 2>/dev/null');
    if ($output && trim($output) !== '') {
        return trim($output);
    }
    return 'python3';
}

function getDBConnection() {
    $configFile = __DIR__ . '/../db_config.json';
    
    // Default fallback values
    $host = '127.0.0.1';
    $port = 3306;
    $db   = 'catool_db';
    $user = 'root';
    $pass = '';

    // Check DATABASE_URL or MYSQL_URL first (Railway / Heroku style)
    $dbUrl = getenv('DATABASE_URL') ?: (getenv('MYSQL_URL') ?: getenv('MYSQL_PRIVATE_URL'));
    if ($dbUrl && strpos($dbUrl, 'mysql://') === 0) {
        $parsed = parse_url($dbUrl);
        if ($parsed) {
            $host = $parsed['host'] ?? $host;
            $port = $parsed['port'] ?? $port;
            $user = $parsed['user'] ?? $user;
            $pass = $parsed['pass'] ?? $pass;
            $db   = isset($parsed['path']) ? ltrim($parsed['path'], '/') : $db;
        }
    } else {
        // Check explicit environment variables
        $envHost = getenv('MYSQLHOST') ?: (getenv('MYSQL_HOST') ?: getenv('DB_HOST'));
        $envPort = getenv('MYSQLPORT') ?: (getenv('MYSQL_PORT') ?: getenv('DB_PORT'));
        $envDb   = getenv('MYSQLDATABASE') ?: (getenv('MYSQL_DATABASE') ?: getenv('DB_NAME'));
        $envUser = getenv('MYSQLUSER') ?: (getenv('MYSQL_USER') ?: getenv('DB_USER'));
        $envPass = getenv('MYSQLPASSWORD') !== false ? getenv('MYSQLPASSWORD') : (getenv('MYSQL_PASSWORD') !== false ? getenv('MYSQL_PASSWORD') : (getenv('DB_PASS') !== false ? getenv('DB_PASS') : null));

        if ($envHost) {
            $host = $envHost;
            if ($envPort) $port = $envPort;
            if ($envDb)   $db   = $envDb;
            if ($envUser) $user = $envUser;
            if ($envPass !== null) $pass = $envPass;
        } else if (file_exists($configFile)) {
            // Fallback to db_config.json only if environment variables are not set
            $cfg = json_decode(file_get_contents($configFile), true);
            if ($cfg && is_array($cfg)) {
                if (!empty($cfg['host'])) $host = $cfg['host'];
                if (!empty($cfg['port'])) $port = $cfg['port'];
                if (!empty($cfg['database'])) $db = $cfg['database'];
                if (!empty($cfg['user'])) $user = $cfg['user'];
                if (isset($cfg['password'])) $pass = $cfg['password'];
            }
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
            // 1. Auto-Initialize Database Schema if sources table missing
            try {
                $check = $pdo->query("SHOW TABLES LIKE 'sources'");
                if ($check->rowCount() === 0) {
                    $schemaFile = __DIR__ . '/../schema.sql';
                    if (file_exists($schemaFile)) {
                        $sql = file_get_contents($schemaFile);
                        $sqlClean = preg_replace('/--.*$/m', '', $sql);
                        $queries = explode(';', $sqlClean);
                        foreach ($queries as $query) {
                            $query = trim($query);
                            if (!empty($query)) {
                                try {
                                    $pdo->exec($query);
                                } catch (Exception $e) {}
                            }
                        }
                    }
                }
            } catch (Exception $e) {}

            // 2. Incremental Migrations
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

