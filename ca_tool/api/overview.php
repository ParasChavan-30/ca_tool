<?php
require_once __DIR__ . '/db.php';

try {
    $pdo = getDBConnection();

    // 1. Total Articles
    $totalArticles = (int)$pdo->query("SELECT COUNT(*) FROM knowledge_bank")->fetchColumn();

    // 2. Articles Added Today
    $addedToday = (int)$pdo->query("SELECT COUNT(*) FROM knowledge_bank WHERE DATE(created_at) = CURDATE() OR DATE(collected_date) = CURDATE()")->fetchColumn();

    // 3. Total PDFs
    $totalPDFs = (int)$pdo->query("SELECT COUNT(*) FROM attachments")->fetchColumn();

    // 4. Total Sources, Active Sources, Failed Sources
    $totalSources = (int)$pdo->query("SELECT COUNT(*) FROM sources")->fetchColumn();
    $activeSourcesCount = (int)$pdo->query("SELECT COUNT(*) FROM sources WHERE status IN ('ACTIVE', 'ROTATED')")->fetchColumn();
    $failedSourcesCount = (int)$pdo->query("SELECT COUNT(*) FROM sources WHERE status IN ('FAILED', 'DOWN', 'ERROR') OR failure_count > 0")->fetchColumn();

    // 5. Active Target Source
    $activeStmt = $pdo->query("SELECT * FROM sources WHERE status IN ('ACTIVE', 'ROTATED') ORDER BY failover_priority ASC LIMIT 1");
    $activeSource = $activeStmt->fetch();
    if (!$activeSource) {
        $activeSource = [
            'name' => 'SCA & Associates',
            'domain' => 'scaca.in',
            'status' => 'ACTIVE',
            'is_primary' => 1
        ];
    }

    // 6. Last Scraped Date & Updated Count
    $lastScraped = $pdo->query("SELECT MAX(run_timestamp) FROM execution_logs WHERE status IN ('SUCCESS', 'COMPLETED', 'RUNNING', 'ROTATED')")->fetchColumn();
    if (!$lastScraped) {
        $lastScraped = $pdo->query("SELECT MAX(collected_date) FROM knowledge_bank")->fetchColumn();
    }
    $updatedArticles = (int)$pdo->query("SELECT COUNT(*) FROM knowledge_bank WHERE last_updated_at IS NOT NULL")->fetchColumn();

    // 7. Cron Settings & Next Scheduled Sync
    $cronSettings = [
        'cron_enabled' => '1',
        'cron_interval_hours' => '24',
        'retry_limits' => '3',
        'request_timeout' => '30'
    ];
    try {
        $cStmt = $pdo->query("SELECT setting_key, setting_value FROM cron_settings");
        foreach ($cStmt->fetchAll() as $cRow) {
            $cronSettings[$cRow['setting_key']] = $cRow['setting_value'];
        }
    } catch (Exception $cErr) {}

    $intervalHours = (int)($cronSettings['cron_interval_hours'] ?? 24);
    if ($intervalHours <= 0) $intervalHours = 24;

    if ($lastScraped && $lastScraped !== 'Not yet run') {
        $lastTs = strtotime($lastScraped);
        $nextTs = $lastTs + ($intervalHours * 3600);
        $nextScheduledSync = date('Y-m-d H:i:s', $nextTs);
    } else {
        $nextScheduledSync = date('Y-m-d H:i:s', time() + ($intervalHours * 3600));
    }

    // 8. Category Distribution
    $catStmt = $pdo->query("SELECT authority_category as category, COUNT(*) as count FROM knowledge_bank GROUP BY authority_category ORDER BY count DESC");
    $categoryDistribution = $catStmt->fetchAll();

    // 9. Recent Execution Activity
    $logsStmt = $pdo->query("
        SELECT el.*, s.name as source_name, s.domain as source_domain 
        FROM execution_logs el 
        LEFT JOIN sources s ON el.source_id = s.id 
        ORDER BY el.id DESC LIMIT 5
    ");
    $recentActivity = $logsStmt->fetchAll();

    echo json_encode([
        'success' => true,
        'data' => [
            'total_articles' => $totalArticles,
            'added_today' => $addedToday,
            'updated_articles' => $updatedArticles,
            'total_pdfs' => $totalPDFs,
            'total_sources' => $totalSources,
            'active_sources_count' => $activeSourcesCount,
            'failed_sources_count' => $failedSourcesCount,
            'active_source' => $activeSource,
            'last_scraped_at' => $lastScraped ? $lastScraped : 'Not yet run',
            'next_scheduled_sync' => $nextScheduledSync,
            'cron_settings' => $cronSettings,
            'category_distribution' => $categoryDistribution,
            'recent_activity' => $recentActivity
        ]
    ]);
} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}

