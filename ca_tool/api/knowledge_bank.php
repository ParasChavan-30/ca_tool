<?php
require_once __DIR__ . '/db.php';

try {
    $pdo = getDBConnection();

    $page = isset($_GET['page']) ? max(1, (int)$_GET['page']) : 1;
    $limit = isset($_GET['limit']) ? max(1, min(100, (int)$_GET['limit'])) : 15;
    $offset = ($page - 1) * $limit;

    $search = trim($_GET['search'] ?? '');
    $category = trim($_GET['category'] ?? '');
    $authority = trim($_GET['authority'] ?? '');
    $dateFrom = trim($_GET['date_from'] ?? '');
    $dateTo = trim($_GET['date_to'] ?? '');
    $sourceId = isset($_GET['source_id']) ? (int)$_GET['source_id'] : 0;

    $whereClauses = [];
    $params = [];

    if ($search !== '') {
        $searchTerms = array_filter(explode(' ', $search));
        $subClauses = [];
        $i = 0;
        foreach ($searchTerms as $term) {
            $i++;
            $subClauses[] = "(kb.title LIKE :s1_{$i} OR kb.authority_category LIKE :s2_{$i} OR kb.source_url LIKE :s3_{$i} OR EXISTS (SELECT 1 FROM sub_pages sp WHERE sp.knowledge_bank_id = kb.id AND (sp.sub_page_title LIKE :s4_{$i} OR sp.sub_page_url LIKE :s5_{$i})))";
            $params[":s1_{$i}"] = "%{$term}%";
            $params[":s2_{$i}"] = "%{$term}%";
            $params[":s3_{$i}"] = "%{$term}%";
            $params[":s4_{$i}"] = "%{$term}%";
            $params[":s5_{$i}"] = "%{$term}%";
        }
        if (!empty($subClauses)) {
            $whereClauses[] = '(' . implode(' OR ', $subClauses) . ')';
        }
    }

    if ($category !== '') {
        $whereClauses[] = "kb.authority_category = :category";
        $params[':category'] = $category;
    }

    if ($authority !== '') {
        $whereClauses[] = "kb.authority_category LIKE :authority";
        $params[':authority'] = "%{$authority}%";
    }

    if ($dateFrom !== '') {
        $whereClauses[] = "DATE(kb.collected_date) >= :date_from";
        $params[':date_from'] = $dateFrom;
    }

    if ($dateTo !== '') {
        $whereClauses[] = "DATE(kb.collected_date) <= :date_to";
        $params[':date_to'] = $dateTo;
    }

    if ($sourceId > 0) {
        $whereClauses[] = "kb.source_id = :source_id";
        $params[':source_id'] = $sourceId;
    }

    $whereSQL = count($whereClauses) > 0 ? 'WHERE ' . implode(' AND ', $whereClauses) : '';

    // Count Total
    $countSql = "SELECT COUNT(*) FROM knowledge_bank kb {$whereSQL}";
    $countStmt = $pdo->prepare($countSql);
    $countStmt->execute($params);
    $totalRecords = (int)$countStmt->fetchColumn();
    $totalPages = ceil($totalRecords / $limit);

    // Fetch Paginated List
    $sql = "
        SELECT kb.id, kb.source_id, kb.source_url, kb.title, kb.authority_category, kb.notification_number, kb.summary, kb.published_date, kb.collected_date, kb.wp_post_id, kb.wp_synced_at, kb.created_at,
               s.name as source_name, s.domain as source_domain,
               (SELECT COUNT(*) FROM attachments WHERE knowledge_bank_id = kb.id) as pdf_count,
               (SELECT COUNT(*) FROM sub_pages WHERE knowledge_bank_id = kb.id) as subpage_count,
               (SELECT COUNT(*) FROM knowledge_bank_sources WHERE knowledge_bank_id = kb.id) as backup_source_count
        FROM knowledge_bank kb
        LEFT JOIN sources s ON kb.source_id = s.id
        {$whereSQL}
        ORDER BY kb.id DESC
        LIMIT :limit OFFSET :offset
    ";

    $stmt = $pdo->prepare($sql);
    foreach ($params as $k => $v) {
        $stmt->bindValue($k, $v);
    }
    $stmt->bindValue(':limit', $limit, PDO::PARAM_INT);
    $stmt->bindValue(':offset', $offset, PDO::PARAM_INT);
    $stmt->execute();

    $items = $stmt->fetchAll();

    // Fetch PDF Attachments for these items
    if (count($items) > 0) {
        $itemIds = array_column($items, 'id');
        $inClause = implode(',', array_fill(0, count($itemIds), '?'));
        
        $attStmt = $pdo->prepare("SELECT * FROM attachments WHERE knowledge_bank_id IN ({$inClause})");
        $attStmt->execute($itemIds);
        $attachments = $attStmt->fetchAll();

        $attMap = [];
        foreach ($attachments as $att) {
            $attMap[$att['knowledge_bank_id']][] = $att;
        }

        foreach ($items as &$item) {
            $item['attachments'] = $attMap[$item['id']] ?? [];
        }
    }

    // Categories list for filter dropdown
    $categoriesStmt = $pdo->query("SELECT DISTINCT authority_category FROM knowledge_bank ORDER BY authority_category ASC");
    $categories = $categoriesStmt->fetchAll(PDO::FETCH_COLUMN);

    echo json_encode([
        'success' => true,
        'data' => $items,
        'pagination' => [
            'total_records' => $totalRecords,
            'total_pages' => $totalPages,
            'current_page' => $page,
            'limit' => $limit
        ],
        'categories' => $categories
    ]);
} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
