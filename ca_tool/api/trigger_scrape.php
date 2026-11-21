<?php
/**
 * Triggers the Scraper Job
 * Dispatches GitHub Actions workflow remotely via GitHub REST API if configured,
 * otherwise falls back to local Python background runner.
 */

require_once __DIR__ . '/db.php';

header('Content-Type: application/json; charset=utf-8');

$configFile = __DIR__ . '/../db_config.json';
$cfg = [];
if (file_exists($configFile)) {
    $cfg = json_decode(file_get_contents($configFile), true) ?: [];
}

$githubRepo = getenv('GITHUB_REPO') ?: ($cfg['github_repo'] ?? '');
$githubPat  = getenv('GITHUB_PAT') ?: ($cfg['github_pat'] ?? '');
$workflowFile = 'scraper.yml';

// -------------------------------------------------------------
// Mode 1: Dispatch to GitHub Actions (Recommended for Remote Hosting)
// -------------------------------------------------------------
if (!empty($githubRepo) && !empty($githubPat)) {
    $apiUrl = "https://api.github.com/repos/{$githubRepo}/actions/workflows/{$workflowFile}/dispatches";

    $ch = curl_init($apiUrl);
    $payload = json_encode(['ref' => 'main']);

    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_POSTFIELDS, $payload);
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        'Authorization: Bearer ' . trim($githubPat),
        'Accept: application/vnd.github+json',
        'User-Agent: CATool-Dashboard/1.0',
        'Content-Type: application/json'
    ]);

    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $curlErr  = curl_error($ch);
    curl_close($ch);

    if ($httpCode === 204) {
        // GitHub returns 204 No Content on successful dispatch
        $lockFile = __DIR__ . '/../storage/scraper.lock';
        @file_put_contents($lockFile, "RUNNING_GHA:" . time());

        try {
            $pdo = getDBConnection();
            $pdo->prepare("INSERT INTO execution_logs (status, items_scraped, log_details) VALUES ('STARTED', 0, :msg)")
                ->execute(['msg' => "Dispatched GitHub Actions scraper workflow for repo: {$githubRepo}."]);
        } catch (Exception $e) {}

        echo json_encode([
            'success' => true,
            'mode'    => 'github_actions',
            'message' => "GitHub Actions scraper job triggered successfully on repository: {$githubRepo}!"
        ]);
        exit();
    } else {
        echo json_encode([
            'success' => false,
            'mode'    => 'github_actions',
            'error'   => "Failed to trigger GitHub Actions (HTTP {$httpCode}): " . ($curlErr ?: $response)
        ]);
        exit();
    }
}

// -------------------------------------------------------------
// Mode 2: Local Python Background Runner Fallback
// -------------------------------------------------------------
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
    $runnerScript = realpath(__DIR__ . '/../scraper/runner.py');

    if (!$runnerScript || !file_exists($runnerScript)) {
        echo json_encode([
            'success' => false,
            'error'   => 'Scraper runner script not found locally, and GitHub Actions (github_repo & github_pat) is not configured in db_config.json.'
        ]);
        exit();
    }

    $pythonBin = getPythonCmd();

    if (strtoupper(substr(PHP_OS, 0, 3)) === 'WIN') {
        $cmd = 'start /B "" ' . $pythonBin . ' ' . escapeshellarg($runnerScript) . ' --once';
        pclose(popen($cmd, "r"));
    } else {
        $cmd = $pythonBin . ' ' . escapeshellarg($runnerScript) . ' --once > /dev/null 2>&1 &';
        exec($cmd);
    }

    echo json_encode([
        'success' => true,
        'mode'    => 'local',
        'message' => 'Scraper job triggered successfully locally in background!'
    ]);
} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
