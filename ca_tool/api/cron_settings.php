<?php
header('Content-Type: application/json');
require_once __DIR__ . '/db.php';

try {
    $db = getDbConnection();
    $method = $_SERVER['REQUEST_METHOD'] ?? 'GET';

    if ($method === 'POST') {
        $input = json_decode(file_get_contents('php://input'), true) ?? $_POST;
        
        $allowedKeys = ['cron_enabled', 'cron_interval_hours', 'cron_secret_token', 'retry_limits', 'request_timeout'];
        $updated = [];

        foreach ($allowedKeys as $key) {
            if (isset($input[$key])) {
                $val = trim((string)$input[$key]);
                $stmt = $db->prepare("
                    INSERT INTO cron_settings (setting_key, setting_value) 
                    VALUES (:key, :val) 
                    ON DUPLICATE KEY UPDATE setting_value = :val2
                ");
                $stmt->execute(['key' => $key, 'val' => $val, 'val2' => $val]);
                $updated[$key] = $val;
            }
        }

        echo json_encode([
            'success' => true,
            'message' => 'Settings updated successfully!',
            'updated' => $updated
        ]);
        exit();
    }

    // GET request: return all cron settings
    $stmt = $db->query("SELECT setting_key, setting_value, updated_at FROM cron_settings");
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);

    $settings = [
        'cron_enabled' => '1',
        'cron_interval_hours' => '24',
        'last_cron_run' => '',
        'cron_secret_token' => 'ca_cron_secret_key_123',
        'retry_limits' => '3',
        'request_timeout' => '30'
    ];

    foreach ($rows as $row) {
        $settings[$row['setting_key']] = $row['setting_value'];
    }

    echo json_encode([
        'success' => true,
        'settings' => $settings
    ]);

} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
