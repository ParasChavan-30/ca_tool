<?php
require_once __DIR__ . '/db.php';

$file = $_GET['file'] ?? '';
if (empty($file)) {
    http_response_code(400);
    echo "Missing file parameter.";
    exit();
}

$safeFilename = basename($file);
$pdfPath = realpath(__DIR__ . '/../storage/pdfs/' . $safeFilename);

if (!$pdfPath || !file_exists($pdfPath)) {
    http_response_code(404);
    echo "PDF File not found.";
    exit();
}

header('Content-Type: application/pdf');
header('Content-Disposition: inline; filename="' . $safeFilename . '"');
header('Content-Length: ' . filesize($pdfPath));
readfile($pdfPath);
exit();
