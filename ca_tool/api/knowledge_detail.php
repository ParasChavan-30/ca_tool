<?php
require_once __DIR__ . '/db.php';

try {
    $pdo = getDBConnection();
    $id = isset($_GET['id']) ? (int)$_GET['id'] : 0;

    if ($id <= 0) {
        echo json_encode(['success' => false, 'error' => 'Invalid or missing Item ID parameter']);
        exit();
    }

    // Fetch Knowledge Bank main item
    $stmt = $pdo->prepare("
        SELECT kb.*, s.name as source_name, s.domain as source_domain 
        FROM knowledge_bank kb 
        LEFT JOIN sources s ON kb.source_id = s.id 
        WHERE kb.id = :id
    ");
    $stmt->execute([':id' => $id]);
    $item = $stmt->fetch();

    if (!$item) {
        echo json_encode(['success' => false, 'error' => 'Knowledge Bank item not found']);
        exit();
    }

    // Fetch Sub-pages
    $subStmt = $pdo->prepare("SELECT id, sub_page_url, sub_page_title, sub_page_html, created_at FROM sub_pages WHERE knowledge_bank_id = :id ORDER BY id ASC");
    $subStmt->execute([':id' => $id]);
    $subPages = $subStmt->fetchAll();

    // Fetch PDF Attachments
    $attStmt = $pdo->prepare("SELECT * FROM attachments WHERE knowledge_bank_id = :id ORDER BY id ASC");
    $attStmt->execute([':id' => $id]);
    $attachments = $attStmt->fetchAll();

    $item['sub_pages'] = $subPages;
    $item['attachments'] = $attachments;

    echo json_encode([
        'success' => true,
        'data' => $item
    ]);
} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
