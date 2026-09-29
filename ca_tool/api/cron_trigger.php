<?php
header('Content-Type: application/json');
require_once __DIR__ . '/db.php';

if (!function_exists('getPythonCmd')) {
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
}

try {
    $db = getDbConnection();
    
    // Fetch cron settings from DB
    $stmt = $db->query("SELECT setting_key, setting_value FROM cron_settings");
    $settingsRows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    $settings = [];
    foreach ($settingsRows as $row) {
        $settings[$row['setting_key']] = $row['setting_value'];
    }

    $secretToken = $settings['cron_secret_token'] ?? 'ca_cron_secret_key_123';
    $cronEnabled = ($settings['cron_enabled'] ?? '1') === '1';

    // Verify token from GET query or HTTP header
    $providedToken = $_GET['token'] ?? $_SERVER['HTTP_X_CRON_TOKEN'] ?? '';
    $force = isset($_GET['force']) && ($_GET['force'] === '1' || $_GET['force'] === 'true');

    if ($providedToken !== $secretToken && !$force) {
        http_response_code(403);
        echo json_encode([
            'success' => false,
            'error' => 'Unauthorized cron request. Invalid or missing secret token.'
        ]);
        exit();
    }

    if (!$cronEnabled && !$force) {
        echo json_encode([
            'success' => false,
            'message' => 'Cron updater is currently disabled in settings.'
        ]);
        exit();
    }

    $runnerScript = realpath(__DIR__ . '/../scraper/runner.py');
    if (!$runnerScript || !file_exists($runnerScript)) {
        echo json_encode(['success' => false, 'error' => 'Scraper runner script not found at ' . $runnerScript]);
        exit();
    }

    $pythonBin = getPythonCmd();
    $flag = $force ? '--cron --force' : '--cron';

    if (strtoupper(substr(PHP_OS, 0, 3)) === 'WIN') {
        $cmd = 'start /B "" ' . $pythonBin . ' ' . escapeshellarg($runnerScript) . ' ' . $flag;
        pclose(popen($cmd, "r"));
    } else {
        $cmd = $pythonBin . ' ' . escapeshellarg($runnerScript) . ' ' . $flag . ' > /dev/null 2>&1 &';
        exec($cmd);
    }

    echo json_encode([
        'success' => true,
        'message' => 'Cron daily updater job triggered in background successfully!',
        'cron_interval_hours' => $settings['cron_interval_hours'] ?? '24',
        'last_cron_run' => $settings['last_cron_run'] ?? 'Never'
    ]);

} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
