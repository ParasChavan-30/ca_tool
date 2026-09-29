<?php
require_once __DIR__ . '/db.php';

try {
    $pdo = getDBConnection();
    $action = $_GET['action'] ?? ($_POST['action'] ?? 'list');
    $input = json_decode(file_get_contents('php://input'), true) ?? $_REQUEST;

    if ($action === 'add') {
        $name = trim($input['name'] ?? '');
        $domain = trim($input['domain'] ?? '');
        $url = trim($input['url'] ?? '');
        $priority = isset($input['failover_priority']) ? (int)$input['failover_priority'] : 99;
        $isPrimary = !empty($input['is_primary']) ? 1 : 0;
        $status = !empty($input['status']) ? trim($input['status']) : 'ACTIVE';

        if (empty($name) || empty($domain) || empty($url)) {
            echo json_encode(['success' => false, 'error' => 'Name, domain, and URL are required.']);
            exit();
        }

        // Clean domain
        $domain = preg_replace('/^https?:\/\//i', '', $domain);
        $domain = rtrim($domain, '/');

        $stmt = $pdo->prepare("INSERT INTO sources (name, domain, url, failover_priority, is_primary, status, failure_count) VALUES (:name, :domain, :url, :priority, :is_primary, :status, 0)");
        $stmt->execute([
            'name' => $name,
            'domain' => $domain,
            'url' => $url,
            'priority' => $priority,
            'is_primary' => $isPrimary,
            'status' => $status
        ]);

        echo json_encode(['success' => true, 'message' => 'Source added successfully!']);
        exit();
    }

    if ($action === 'edit') {
        $id = (int)($input['id'] ?? 0);
        $name = trim($input['name'] ?? '');
        $domain = trim($input['domain'] ?? '');
        $url = trim($input['url'] ?? '');
        $priority = isset($input['failover_priority']) ? (int)$input['failover_priority'] : 99;
        $isPrimary = !empty($input['is_primary']) ? 1 : 0;
        $status = !empty($input['status']) ? trim($input['status']) : 'ACTIVE';

        if ($id <= 0 || empty($name) || empty($domain) || empty($url)) {
            echo json_encode(['success' => false, 'error' => 'Valid Source ID, Name, domain, and URL are required.']);
            exit();
        }

        $domain = preg_replace('/^https?:\/\//i', '', $domain);
        $domain = rtrim($domain, '/');

        $stmt = $pdo->prepare("UPDATE sources SET name = :name, domain = :domain, url = :url, failover_priority = :priority, is_primary = :is_primary, status = :status WHERE id = :id");
        $stmt->execute([
            'name' => $name,
            'domain' => $domain,
            'url' => $url,
            'priority' => $priority,
            'is_primary' => $isPrimary,
            'status' => $status,
            'id' => $id
        ]);

        echo json_encode(['success' => true, 'message' => 'Source updated successfully!']);
        exit();
    }

    if ($action === 'toggle_status') {
        $id = (int)($input['id'] ?? 0);
        if ($id <= 0) {
            echo json_encode(['success' => false, 'error' => 'Invalid source ID.']);
            exit();
        }

        $stmt = $pdo->prepare("SELECT status FROM sources WHERE id = :id");
        $stmt->execute(['id' => $id]);
        $current = $stmt->fetchColumn();

        $newStatus = ($current === 'DISABLED') ? 'ACTIVE' : 'DISABLED';

        $update = $pdo->prepare("UPDATE sources SET status = :status WHERE id = :id");
        $update->execute(['status' => $newStatus, 'id' => $id]);

        echo json_encode(['success' => true, 'message' => "Source status updated to {$newStatus}.", 'new_status' => $newStatus]);
        exit();
    }

    if ($action === 'set_priority') {
        $id = (int)($input['id'] ?? 0);
        $priority = (int)($input['priority'] ?? 99);
        if ($id <= 0) {
            echo json_encode(['success' => false, 'error' => 'Invalid source ID.']);
            exit();
        }

        $update = $pdo->prepare("UPDATE sources SET failover_priority = :priority WHERE id = :id");
        $update->execute(['priority' => $priority, 'id' => $id]);

        echo json_encode(['success' => true, 'message' => 'Source priority updated!']);
        exit();
    }

    if ($action === 'test_source') {
        $id = (int)($input['id'] ?? 0);
        if ($id <= 0) {
            echo json_encode(['success' => false, 'error' => 'Invalid source ID.']);
            exit();
        }

        $stmt = $pdo->prepare("SELECT * FROM sources WHERE id = :id");
        $stmt->execute(['id' => $id]);
        $source = $stmt->fetch();

        if (!$source) {
            echo json_encode(['success' => false, 'error' => 'Source not found.']);
            exit();
        }

        $startTime = microtime(true);
        $url = $source['url'];
        
        $ctx = stream_context_create([
            'http' => [
                'method' => 'GET',
                'timeout' => 10,
                'header' => "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) CA-Tool-Validator/2.0\r\n"
            ],
            'ssl' => [
                'verify_peer' => false,
                'verify_peer_name' => false
            ]
        ]);

        $html = @file_get_contents($url, false, $ctx);
        $latency = round((microtime(true) - $startTime) * 1000);

        if ($html !== false && strlen($html) > 100) {
            // Extract title
            preg_match('/<title[^>]*>(.*?)<\/title>/is', $html, $matches);
            $pageTitle = isset($matches[1]) ? trim(html_entity_decode($matches[1])) : 'Title Extracted Successfully';
            
            // Count headings/links to test parser potential
            preg_match_all('/<a\s+[^>]*href=["\']([^"\']+)["\']/i', $html, $links);
            $linkCount = count($links[1] ?? []);

            $pdo->prepare("UPDATE sources SET last_checked = NOW(), failure_count = 0, status = CASE WHEN status = 'DISABLED' THEN 'DISABLED' ELSE 'ACTIVE' END WHERE id = :id")
                ->execute(['id' => $id]);

            echo json_encode([
                'success' => true,
                'data' => [
                    'source_id' => $id,
                    'name' => $source['name'],
                    'url' => $url,
                    'http_status' => 200,
                    'latency_ms' => $latency,
                    'page_title' => $pageTitle,
                    'parsed_links_count' => $linkCount,
                    'status' => 'HEALTHY',
                    'message' => "Successfully connected to {$source['name']} in {$latency}ms! Found {$linkCount} links."
                ]
            ]);
        } else {
            $pdo->prepare("UPDATE sources SET last_checked = NOW(), failure_count = failure_count + 1, status = CASE WHEN status = 'DISABLED' THEN 'DISABLED' ELSE 'FAILED' END WHERE id = :id")
                ->execute(['id' => $id]);

            echo json_encode([
                'success' => false,
                'data' => [
                    'source_id' => $id,
                    'name' => $source['name'],
                    'url' => $url,
                    'http_status' => 500,
                    'latency_ms' => $latency,
                    'status' => 'FAILED',
                    'message' => "Failed to connect or fetch content from {$source['name']} ({$url})."
                ]
            ]);
        }
        exit();
    }

    if ($action === 'ping_all') {
        // Run health check via python rotator
        $cmd = 'python ' . escapeshellarg(__DIR__ . '/../scraper/runner.py') . ' --once';
        exec($cmd);
    }

    // Default: list all sources
    $stmt = $pdo->query("SELECT * FROM sources ORDER BY failover_priority ASC");
    $sources = $stmt->fetchAll();

    echo json_encode([
        'success' => true,
        'data' => $sources
    ]);
} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
