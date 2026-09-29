<?php
require_once __DIR__ . '/db.php';

$action = $_GET['action'] ?? 'status';

try {
    $pdo = getDBConnection();

    // Check if columns exist
    try {
        $pdo->query("SELECT wp_post_id, wp_synced_at FROM knowledge_bank LIMIT 1");
    } catch (Exception $e) {
        $pdo->exec("ALTER TABLE knowledge_bank ADD COLUMN wp_post_id INT NULL AFTER collected_date");
        $pdo->exec("ALTER TABLE knowledge_bank ADD COLUMN wp_synced_at DATETIME NULL AFTER wp_post_id");
    }

    if ($action === 'status') {
        $totalStmt = $pdo->query("SELECT COUNT(*) FROM knowledge_bank");
        $totalItems = (int)$totalStmt->fetchColumn();

        $syncedStmt = $pdo->query("SELECT COUNT(*) FROM knowledge_bank WHERE wp_synced_at IS NOT NULL");
        $syncedItems = (int)$syncedStmt->fetchColumn();

        $unsyncedItems = $totalItems - $syncedItems;

        $lastSyncStmt = $pdo->query("SELECT MAX(wp_synced_at) FROM knowledge_bank");
        $lastSyncedAt = $lastSyncStmt->fetchColumn() ?: null;

        echo json_encode([
            'success' => true,
            'data' => [
                'total_items' => $totalItems,
                'synced_items' => $syncedItems,
                'unsynced_items' => $unsyncedItems,
                'last_synced_at' => $lastSyncedAt
            ]
        ]);
        exit();
    }

    if ($action === 'sync') {
        $limit = isset($_GET['limit']) ? max(1, min(500, (int)$_GET['limit'])) : 500;
        $syncScript = realpath(__DIR__ . '/../scraper/wp_sync.py');
        if (!$syncScript || !file_exists($syncScript)) {
            echo json_encode(['success' => false, 'error' => 'WordPress sync script not found at scraper/wp_sync.py']);
            exit();
        }

        $forceFlag = (isset($_GET['force']) && ($_GET['force'] === 'true' || $_GET['force'] === '1')) ? ' --force' : '';
        $idFlag = isset($_GET['id']) ? ' --id=' . (int)$_GET['id'] : '';

        $pythonBin = getPythonCmd();
        // Execute python script with limit
        $cmd = $pythonBin . ' ' . escapeshellarg($syncScript) . ' --limit=' . $limit . $forceFlag . $idFlag;
        $rawOutput = shell_exec($cmd . ' 2>&1');
        
        $parsedOutput = null;
        // Try parsing JSON output from last line of script
        $lines = explode("\n", trim($rawOutput));
        for ($i = count($lines) - 1; $i >= 0; $i--) {
            $decoded = json_decode(trim($lines[$i]), true);
            if (is_array($decoded)) {
                $parsedOutput = $decoded;
                break;
            }
        }

        // Fetch refreshed stats
        $syncedStmt = $pdo->query("SELECT COUNT(*) FROM knowledge_bank WHERE wp_synced_at IS NOT NULL");
        $syncedItems = (int)$syncedStmt->fetchColumn();

        $totalStmt = $pdo->query("SELECT COUNT(*) FROM knowledge_bank");
        $totalItems = (int)$totalStmt->fetchColumn();

        if ($parsedOutput && isset($parsedOutput['synced_count'])) {
            $syncedCount = $parsedOutput['synced_count'];
            $failedCount = $parsedOutput['failed_count'];
            
            $firstErr = '';
            if ($failedCount > 0 && !empty($parsedOutput['details'])) {
                foreach ($parsedOutput['details'] as $det) {
                    if (!empty($det['error'])) {
                        $firstErr = $det['error'];
                        break;
                    }
                }
            }

            echo json_encode([
                'success' => $syncedCount > 0 || $failedCount === 0,
                'message' => $syncedCount > 0 
                    ? "Successfully pushed {$syncedCount} item(s) to WordPress!" 
                    : "Sync attempt completed. 0 items pushed, {$failedCount} failed.",
                'synced_count' => $syncedCount,
                'failed_count' => $failedCount,
                'first_error' => $firstErr,
                'raw_output' => $rawOutput,
                'stats' => [
                    'synced_items' => $syncedItems,
                    'unsynced_items' => $totalItems - $syncedItems
                ]
            ]);
        } else {
            echo json_encode([
                'success' => false,
                'error' => 'Sync script output error: ' . $rawOutput
            ]);
        }
        exit();
    }

    if ($action === 'test_connection') {
        $syncScript = realpath(__DIR__ . '/../scraper/wp_sync.py');
        $pythonBin = getPythonCmd();
        $cmd = $pythonBin . ' -c "import logging; logging.basicConfig(level=logging.INFO); from scraper.wp_sync import WordPressSyncEngine; print(WordPressSyncEngine().test_connection())"';
        $output = shell_exec($cmd . ' 2>&1');

        echo json_encode([
            'success' => true,
            'output' => $output
        ]);
        exit();
    }

    echo json_encode(['success' => false, 'error' => 'Invalid action parameter']);

} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
