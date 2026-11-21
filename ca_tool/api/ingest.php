<?php
/**
 * CA Knowledge Bank - Remote Ingest API
 * Receives scraped data, logs, and status from GitHub Actions (or external workers)
 * and securely saves them into the local cPanel MySQL database.
 */

ini_set('display_errors', '0');
error_reporting(E_ALL & ~E_NOTICE & ~E_WARNING);

header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, X-API-KEY, Authorization');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit();
}

require_once __DIR__ . '/db.php';

// -------------------------------------------------------------
// 1. Authentication
// -------------------------------------------------------------
$headers = function_exists('getallheaders') ? getallheaders() : [];
$providedKey = $_SERVER['HTTP_X_API_KEY'] ?? ($headers['X-API-KEY'] ?? ($headers['x-api-key'] ?? ''));

if (!$providedKey && isset($_SERVER['HTTP_AUTHORIZATION'])) {
    if (preg_match('/Bearer\s+(.*)$/i', $_SERVER['HTTP_AUTHORIZATION'], $m)) {
        $providedKey = trim($m[1]);
    }
}

// Load configured secret
$configuredSecret = getenv('API_SECRET') ?: getenv('INGEST_KEY');
$configFile = __DIR__ . '/../db_config.json';
if (!$configuredSecret && file_exists($configFile)) {
    $cfg = json_decode(file_get_contents($configFile), true);
    if (!empty($cfg['api_secret'])) {
        $configuredSecret = trim($cfg['api_secret']);
    }
}

if (!$configuredSecret) {
    $configuredSecret = 'catool_secret_ingest_key_2026';
}

if (empty($providedKey) || !hash_equals($configuredSecret, $providedKey)) {
    http_response_code(401);
    echo json_encode([
        'success' => false,
        'error' => 'Unauthorized: Invalid or missing X-API-KEY header.'
    ]);
    exit();
}

// -------------------------------------------------------------
// 2. Parse Request Body
// -------------------------------------------------------------
$rawInput = file_get_contents('php://input');
$payload = json_decode($rawInput, true);
if (!$payload || !is_array($payload)) {
    $payload = $_POST;
}

$action = $payload['action'] ?? ($_GET['action'] ?? 'ping');
$pdo = getDBConnection();
$lockFile = __DIR__ . '/../storage/scraper.lock';

// -------------------------------------------------------------
// 3. Action Handlers
// -------------------------------------------------------------
try {
    switch ($action) {
        // --- Health Check / Ping ---
        case 'ping':
            echo json_encode([
                'success' => true,
                'message' => 'Ingest endpoint active and database connected successfully.',
                'server_time' => date('Y-m-d H:i:s')
            ]);
            break;

        // --- Status Update (Starts / Stops Dashboard Active Badge) ---
        case 'set_status':
            $status = strtoupper(trim($payload['status'] ?? 'RUNNING'));
            $details = $payload['details'] ?? "Status updated to {$status} from GitHub Actions.";

            if ($status === 'RUNNING') {
                @file_put_contents($lockFile, "RUNNING_GHA:" . time());
                $pdo->prepare("INSERT INTO execution_logs (status, items_scraped, log_details) VALUES ('STARTED', 0, :msg)")
                    ->execute(['msg' => $details]);
            } else {
                if (file_exists($lockFile)) {
                    @unlink($lockFile);
                }
                $statusFlag = ($status === 'FAILED') ? 'FAILED' : 'SUCCESS';
                $pdo->prepare("INSERT INTO execution_logs (status, items_scraped, log_details) VALUES (:st, 0, :msg)")
                    ->execute(['st' => $statusFlag, 'msg' => $details]);
            }

            echo json_encode(['success' => true, 'status' => $status]);
            break;

        // --- Get Sources List for Scraper Worker ---
        case 'get_sources':
            $stmt = $pdo->query("SELECT id, name, domain, url, is_primary, status, failover_priority, total_scraped_items FROM sources ORDER BY failover_priority ASC");
            $sources = $stmt->fetchAll();
            echo json_encode(['success' => true, 'sources' => $sources]);
            break;

        // --- Update Source Status / Metrics ---
        case 'update_source':
            $sourceId = (int)($payload['source_id'] ?? 0);
            $newStatus = $payload['status'] ?? 'ACTIVE';
            $scrapedDelta = (int)($payload['scraped_delta'] ?? 0);

            if ($sourceId > 0) {
                $stmt = $pdo->prepare("UPDATE sources SET status = :status, last_checked = NOW(), total_scraped_items = total_scraped_items + :delta WHERE id = :id");
                $stmt->execute([
                    'status' => $newStatus,
                    'delta'  => $scrapedDelta,
                    'id'     => $sourceId
                ]);
            }
            echo json_encode(['success' => true]);
            break;

        // --- Ingest Scraped Knowledge Item ---
        case 'save_knowledge':
            $sourceId = (int)($payload['source_id'] ?? 1);
            $sourceUrl = trim($payload['source_url'] ?? '');
            $title = trim($payload['title'] ?? '');
            $category = trim($payload['authority_category'] ?? 'General');
            $htmlContent = $payload['full_html_content'] ?? '';
            $contentHash = $payload['content_hash'] ?? (!empty($htmlContent) ? md5($htmlContent) : null);
            $notifNumber = !empty($payload['notification_number']) ? trim($payload['notification_number']) : null;
            $summary = !empty($payload['summary']) ? trim($payload['summary']) : null;
            $publishedDate = !empty($payload['published_date']) ? trim($payload['published_date']) : null;
            $collectedDate = !empty($payload['collected_date']) ? trim($payload['collected_date']) : date('Y-m-d H:i:s');

            if (empty($sourceUrl) || empty($title)) {
                http_response_code(400);
                echo json_encode(['success' => false, 'error' => 'Missing source_url or title.']);
                exit();
            }

            // Deduplication & Matching
            $existing = null;

            // 1. Primary match by exact source_url
            $stmt = $pdo->prepare("SELECT id, source_url, content_hash, wp_post_id FROM knowledge_bank WHERE source_url = :url");
            $stmt->execute(['url' => $sourceUrl]);
            $existing = $stmt->fetch();

            // 1b. Secondary match in linked sources table
            if (!$existing) {
                $stmt = $pdo->prepare("SELECT kb.id, kb.source_url, kb.content_hash, kb.wp_post_id FROM knowledge_bank_sources kbs JOIN knowledge_bank kb ON kbs.knowledge_bank_id = kb.id WHERE kbs.source_url = :url");
                $stmt->execute(['url' => $sourceUrl]);
                $existing = $stmt->fetch();
            }

            // 2. Match by notification number + category
            if (!$existing && $notifNumber && !in_array(strtoupper($notifNumber), ['N/A', 'NONE', ''])) {
                $stmt = $pdo->prepare("SELECT id, source_url, content_hash, wp_post_id FROM knowledge_bank WHERE notification_number = :notif AND authority_category = :cat");
                $stmt->execute(['notif' => $notifNumber, 'cat' => $category]);
                $existing = $stmt->fetch();
            }

            // 3. Match by title + published date (or title + category)
            if (!$existing && strlen($title) > 10) {
                if ($publishedDate) {
                    $stmt = $pdo->prepare("SELECT id, source_url, content_hash, wp_post_id FROM knowledge_bank WHERE title = :title AND (published_date = :pdate OR DATE(collected_date) = :pdate)");
                    $stmt->execute(['title' => $title, 'pdate' => $publishedDate]);
                    $existing = $stmt->fetch();
                }
                if (!$existing) {
                    $stmt = $pdo->prepare("SELECT id, source_url, content_hash, wp_post_id FROM knowledge_bank WHERE title = :title AND authority_category = :cat");
                    $stmt->execute(['title' => $title, 'cat' => $category]);
                    $existing = $stmt->fetch();
                }
            }

            // 4. Match by content hash
            if (!$existing && $contentHash) {
                $stmt = $pdo->prepare("SELECT id, source_url, content_hash, wp_post_id FROM knowledge_bank WHERE content_hash = :hash");
                $stmt->execute(['hash' => $contentHash]);
                $existing = $stmt->fetch();
            }

            $kbId = null;
            $statusResult = 'UNCHANGED';

            if ($existing) {
                $kbId = (int)$existing['id'];
                $existingUrl = $existing['source_url'];
                $existingHash = $existing['content_hash'];

                // Cross-source duplicate -> Link to canonical post
                if ($existingUrl !== $sourceUrl) {
                    try {
                        $linkStmt = $pdo->prepare("INSERT IGNORE INTO knowledge_bank_sources (knowledge_bank_id, source_id, source_url) VALUES (:kbid, :sid, :url)");
                        $linkStmt->execute(['kbid' => $kbId, 'sid' => $sourceId, 'url' => $sourceUrl]);
                    } catch (Exception $e) {}
                    $statusResult = 'LINKED';
                } else if ($existingHash !== $contentHash) {
                    // Content changed -> Update
                    $updStmt = $pdo->prepare("UPDATE knowledge_bank SET title = :title, authority_category = :cat, notification_number = :notif, summary = :sum, published_date = :pdate, full_html_content = :html, content_hash = :hash, last_updated_at = NOW() WHERE id = :id");
                    $updStmt->execute([
                        'title' => $title,
                        'cat'   => $category,
                        'notif' => $notifNumber,
                        'sum'   => $summary,
                        'pdate' => $publishedDate,
                        'html'  => $htmlContent,
                        'hash'  => $contentHash,
                        'id'    => $kbId
                    ]);
                    $statusResult = 'UPDATED';
                }
            } else {
                // New Item -> Insert
                $insStmt = $pdo->prepare("INSERT INTO knowledge_bank (source_id, source_url, title, authority_category, notification_number, summary, published_date, full_html_content, content_hash, collected_date) VALUES (:sid, :url, :title, :cat, :notif, :sum, :pdate, :html, :hash, :colldate)");
                $insStmt->execute([
                    'sid'      => $sourceId,
                    'url'      => $sourceUrl,
                    'title'    => $title,
                    'cat'      => $category,
                    'notif'    => $notifNumber,
                    'sum'      => $summary,
                    'pdate'    => $publishedDate,
                    'html'     => $htmlContent,
                    'hash'     => $contentHash,
                    'colldate' => $collectedDate
                ]);
                $kbId = (int)$pdo->lastInsertId();
                $statusResult = 'ADDED';

                // Increment source total
                try {
                    $pdo->prepare("UPDATE sources SET total_scraped_items = total_scraped_items + 1 WHERE id = :sid")
                        ->execute(['sid' => $sourceId]);
                } catch (Exception $e) {}
            }

            // Process optional attachments bundled in item
            if ($kbId && !empty($payload['attachments']) && is_array($payload['attachments'])) {
                foreach ($payload['attachments'] as $att) {
                    try {
                        $attStmt = $pdo->prepare("INSERT INTO attachments (knowledge_bank_id, file_name, file_url, local_storage_path, file_size_bytes) VALUES (:kbid, :name, :url, :path, :size)");
                        $attStmt->execute([
                            'kbid' => $kbId,
                            'name' => $att['file_name'] ?? 'attachment.pdf',
                            'url'  => $att['file_url'] ?? '',
                            'path' => $att['local_storage_path'] ?? '',
                            'size' => (int)($att['file_size_bytes'] ?? 0)
                        ]);
                    } catch (Exception $e) {}
                }
            }

            // Process optional sub-pages bundled in item
            if ($kbId && !empty($payload['sub_pages']) && is_array($payload['sub_pages'])) {
                foreach ($payload['sub_pages'] as $sp) {
                    try {
                        $spStmt = $pdo->prepare("INSERT INTO sub_pages (knowledge_bank_id, sub_page_url, sub_page_title, sub_page_html) VALUES (:kbid, :url, :title, :html)");
                        $spStmt->execute([
                            'kbid'  => $kbId,
                            'url'   => $sp['sub_page_url'] ?? '',
                            'title' => $sp['sub_page_title'] ?? '',
                            'html'  => $sp['sub_page_html'] ?? ''
                        ]);
                    } catch (Exception $e) {}
                }
            }

            echo json_encode([
                'success' => true,
                'id'      => $kbId,
                'status'  => $statusResult
            ]);
            break;

        // --- Save Single Attachment ---
        case 'save_attachment':
            $kbId = (int)($payload['knowledge_bank_id'] ?? 0);
            if ($kbId <= 0) {
                http_response_code(400);
                echo json_encode(['success' => false, 'error' => 'Invalid knowledge_bank_id.']);
                exit();
            }
            $stmt = $pdo->prepare("INSERT INTO attachments (knowledge_bank_id, file_name, file_url, local_storage_path, file_size_bytes) VALUES (:kbid, :name, :url, :path, :size)");
            $stmt->execute([
                'kbid' => $kbId,
                'name' => $payload['file_name'] ?? 'attachment.pdf',
                'url'  => $payload['file_url'] ?? '',
                'path' => $payload['local_storage_path'] ?? '',
                'size' => (int)($payload['file_size_bytes'] ?? 0)
            ]);
            echo json_encode(['success' => true, 'id' => (int)$pdo->lastInsertId()]);
            break;

        // --- Save Single Sub-Page ---
        case 'save_sub_page':
            $kbId = (int)($payload['knowledge_bank_id'] ?? 0);
            if ($kbId <= 0) {
                http_response_code(400);
                echo json_encode(['success' => false, 'error' => 'Invalid knowledge_bank_id.']);
                exit();
            }
            $stmt = $pdo->prepare("INSERT INTO sub_pages (knowledge_bank_id, sub_page_url, sub_page_title, sub_page_html) VALUES (:kbid, :url, :title, :html)");
            $stmt->execute([
                'kbid'  => $kbId,
                'url'   => $payload['sub_page_url'] ?? '',
                'title' => $payload['sub_page_title'] ?? '',
                'html'  => $payload['sub_page_html'] ?? ''
            ]);
            echo json_encode(['success' => true, 'id' => (int)$pdo->lastInsertId()]);
            break;

        // --- Record Execution Log & Update Cron Timestamps ---
        case 'add_log':
            $sid = !empty($payload['source_id']) ? (int)$payload['source_id'] : null;
            $status = $payload['status'] ?? 'SUCCESS';
            $itemsScraped = (int)($payload['items_scraped'] ?? 0);
            $itemsAdded = (int)($payload['items_added'] ?? 0);
            $itemsUpdated = (int)($payload['items_updated'] ?? 0);
            $itemsUnchanged = (int)($payload['items_unchanged'] ?? 0);
            $wpUpdated = (int)($payload['wp_posts_updated'] ?? 0);
            $details = $payload['log_details'] ?? '';
            $err = $payload['error_message'] ?? null;

            $stmt = $pdo->prepare("INSERT INTO execution_logs (source_id, status, items_scraped, items_added, items_updated, items_unchanged, wp_posts_updated, log_details, error_message) VALUES (:sid, :status, :scraped, :added, :updated, :unchanged, :wp, :details, :err)");
            $stmt->execute([
                'sid'       => $sid,
                'status'    => $status,
                'scraped'   => $itemsScraped,
                'added'     => $itemsAdded,
                'updated'   => $itemsUpdated,
                'unchanged' => $itemsUnchanged,
                'wp'        => $wpUpdated,
                'details'   => $details,
                'err'       => $err
            ]);

            // Update last_cron_run timestamp in cron_settings
            try {
                $now = date('Y-m-d H:i:s');
                $pdo->prepare("INSERT INTO cron_settings (setting_key, setting_value, updated_at) VALUES ('last_cron_run', :now, :now) ON DUPLICATE KEY UPDATE setting_value = :now, updated_at = :now")
                    ->execute(['now' => $now]);
            } catch (Exception $e) {}

            echo json_encode(['success' => true, 'log_id' => (int)$pdo->lastInsertId()]);
            break;

        default:
            http_response_code(400);
            echo json_encode(['success' => false, 'error' => "Unknown action: {$action}"]);
            break;
    }
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode([
        'success' => false,
        'error'   => 'Ingest Error: ' . $e->getMessage()
    ]);
}
