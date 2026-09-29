<?php
require_once __DIR__ . '/db.php';

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

try {
    $runnerScript = realpath(__DIR__ . '/../scraper/runner.py');

    if (!$runnerScript || !file_exists($runnerScript)) {
        echo json_encode(['success' => false, 'error' => 'Scraper runner script not found at ' . $runnerScript]);
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
        'message' => 'Scraper job triggered successfully in the background!'
    ]);
} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
