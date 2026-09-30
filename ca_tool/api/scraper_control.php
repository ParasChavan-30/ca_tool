<?php
require_once __DIR__ . '/db.php';

$lockFile = realpath(__DIR__ . '/../storage/scraper.lock');
if (!$lockFile) {
    $lockFile = __DIR__ . '/../storage/scraper.lock';
}

$action = $_GET['action'] ?? 'status';

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

function isPidRunning($pid) {
    if (!$pid || !is_numeric($pid)) return false;
    if (strtoupper(substr(PHP_OS, 0, 3)) === 'WIN') {
        $output = shell_exec("tasklist /FI \"PID eq {$pid}\" 2>NUL");
        return strpos($output, (string)$pid) !== false;
    } else {
        return file_exists("/proc/{$pid}");
    }
}

function getScraperStatus($lockFile) {
    if (!file_exists($lockFile)) {
        return ['is_running' => false, 'pid' => null];
    }
    $pid = trim(@file_get_contents($lockFile));
    if (isPidRunning($pid)) {
        return ['is_running' => true, 'pid' => (int)$pid];
    }
    // Stale lock file
    @unlink($lockFile);
    return ['is_running' => false, 'pid' => null];
}

if ($action === 'status') {
    $status = getScraperStatus($lockFile);
    echo json_encode(['success' => true, 'data' => $status]);
    exit();
}

if ($action === 'start') {
    $sourceId = isset($_REQUEST['source_id']) ? (int)$_REQUEST['source_id'] : 0;
    $status = getScraperStatus($lockFile);
    if ($status['is_running']) {
        echo json_encode(['success' => false, 'error' => 'Scraper is already running in background (PID: ' . $status['pid'] . ')']);
        exit();
    }

    $runnerScript = realpath(__DIR__ . '/../scraper/runner.py');
    if (!$runnerScript || !file_exists($runnerScript)) {
        echo json_encode(['success' => false, 'error' => 'Scraper runner script not found.']);
        exit();
    }

    $targetText = $sourceId > 0 ? "for single Source ID #{$sourceId}" : "for all sources";
    try {
        $pdo = getDBConnection();
        $pdo->prepare("INSERT INTO execution_logs (source_id, status, items_scraped, log_details) VALUES (:sid, 'STARTED', 0, :msg)")
            ->execute([
                'sid' => $sourceId > 0 ? $sourceId : null,
                'msg' => "Scraper process manually STARTED by user via Dashboard {$targetText}."
            ]);
    } catch (Exception $e) {}

    $pythonBin = getPythonCmd();
    $modeFlag = $sourceId > 0 ? " --once --source-id {$sourceId}" : " --continuous";
    if (strtoupper(substr(PHP_OS, 0, 3)) === 'WIN') {
        $cmd = 'start /B "" ' . $pythonBin . ' ' . escapeshellarg($runnerScript) . $modeFlag;
        pclose(popen($cmd, "r"));
    } else {
        $cmd = $pythonBin . ' ' . escapeshellarg($runnerScript) . $modeFlag . ' > /dev/null 2>&1 &';
        exec($cmd);
    }

    echo json_encode(['success' => true, 'message' => "Scraper process started successfully {$targetText}!"]);
    exit();
}

if ($action === 'resume') {
    $status = getScraperStatus($lockFile);
    if ($status['is_running']) {
        echo json_encode(['success' => false, 'error' => 'Scraper is already running in background (PID: ' . $status['pid'] . ')']);
        exit();
    }

    $runnerScript = realpath(__DIR__ . '/../scraper/runner.py');
    if (!$runnerScript || !file_exists($runnerScript)) {
        echo json_encode(['success' => false, 'error' => 'Scraper runner script not found.']);
        exit();
    }

    try {
        $pdo = getDBConnection();
        $pdo->exec("INSERT INTO execution_logs (status, items_scraped, log_details) VALUES ('RESUMED', 0, 'Scraper process manually RESUMED by user via Dashboard.')");
    } catch (Exception $e) {}

    $pythonBin = getPythonCmd();
    if (strtoupper(substr(PHP_OS, 0, 3)) === 'WIN') {
        $cmd = 'start /B "" ' . $pythonBin . ' ' . escapeshellarg($runnerScript) . ' --continuous';
        pclose(popen($cmd, "r"));
    } else {
        $cmd = $pythonBin . ' ' . escapeshellarg($runnerScript) . ' --continuous > /dev/null 2>&1 &';
        exec($cmd);
    }

    echo json_encode(['success' => true, 'message' => 'Scraper process resumed successfully!']);
    exit();
}

if ($action === 'stop') {
    $status = getScraperStatus($lockFile);
    if (!$status['is_running']) {
        if (file_exists($lockFile)) @unlink($lockFile);
        echo json_encode(['success' => true, 'message' => 'Scraper is already stopped.']);
        exit();
    }

    $pid = $status['pid'];
    if (strtoupper(substr(PHP_OS, 0, 3)) === 'WIN') {
        exec("taskkill /F /PID {$pid} 2>&1");
    } else {
        exec("kill -9 {$pid} 2>&1");
    }

    if (file_exists($lockFile)) {
        @unlink($lockFile);
    }

    // Log stop action in DB
    try {
        $pdo = getDBConnection();
        $pdo->exec("INSERT INTO execution_logs (status, items_scraped, log_details) VALUES ('STOPPED', 0, 'Scraper manually STOPPED by user via Dashboard.')");
    } catch (Exception $e) {}

    echo json_encode(['success' => true, 'message' => "Scraper process (PID: {$pid}) stopped successfully."]);
    exit();
}

if ($action === 'clear') {
    try {
        $pdo = getDBConnection();
        $pdo->exec("SET FOREIGN_KEY_CHECKS = 0;");
        $pdo->exec("TRUNCATE TABLE attachments;");
        $pdo->exec("TRUNCATE TABLE sub_pages;");
        $pdo->exec("TRUNCATE TABLE knowledge_bank;");
        $pdo->exec("TRUNCATE TABLE execution_logs;");
        $pdo->exec("UPDATE sources SET total_scraped_items = 0;");
        $pdo->exec("SET FOREIGN_KEY_CHECKS = 1;");

        $pdfDir = realpath(__DIR__ . '/../storage/pdfs');
        if ($pdfDir && is_dir($pdfDir)) {
            $files = glob($pdfDir . '/*');
            foreach ($files as $file) {
                if (is_file($file)) @unlink($file);
            }
        }

        echo json_encode(['success' => true, 'message' => 'All scraped data cleared successfully from database and storage!']);
    } catch (Exception $e) {
        echo json_encode(['success' => false, 'error' => $e->getMessage()]);
    }
    exit();
}

echo json_encode(['success' => false, 'error' => 'Invalid action parameter']);
