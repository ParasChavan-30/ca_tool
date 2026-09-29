<?php
require_once __DIR__ . '/db.php';

try {
    $pdo = getDBConnection();

    $page = isset($_GET['page']) ? max(1, (int)$_GET['page']) : 1;
    $limit = isset($_GET['limit']) ? max(1, min(100, (int)$_GET['limit'])) : 20;
    $offset = ($page - 1) * $limit;
    $status = trim($_GET['status'] ?? '');

    $whereClauses = [];
    $params = [];

    if ($status !== '') {
        $whereClauses[] = "el.status = :status";
        $params[':status'] = $status;
    }

    $whereSQL = count($whereClauses) > 0 ? 'WHERE ' . implode(' AND ', $whereClauses) : '';

    $countSql = "SELECT COUNT(*) FROM execution_logs el {$whereSQL}";
    $countStmt = $pdo->prepare($countSql);
    $countStmt->execute($params);
    $totalRecords = (int)$countStmt->fetchColumn();

    $sql = "
        SELECT el.*, s.name as source_name, s.domain as source_domain 
        FROM execution_logs el 
        LEFT JOIN sources s ON el.source_id = s.id 
        {$whereSQL} 
        ORDER BY el.id DESC 
        LIMIT :limit OFFSET :offset
    ";

    $stmt = $pdo->prepare($sql);
    foreach ($params as $k => $v) {
        $stmt->bindValue($k, $v);
    }
    $stmt->bindValue(':limit', $limit, PDO::PARAM_INT);
    $stmt->bindValue(':offset', $offset, PDO::PARAM_INT);
    $stmt->execute();

    $logs = $stmt->fetchAll();

    echo json_encode([
        'success' => true,
        'data' => $logs,
        'pagination' => [
            'total_records' => $totalRecords,
            'total_pages' => ceil($totalRecords / $limit),
            'current_page' => $page,
            'limit' => $limit
        ]
    ]);
} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
