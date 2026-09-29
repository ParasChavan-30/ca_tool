<?php
require_once __DIR__ . '/db.php';

header('Content-Type: text/html; charset=utf-8');

$pdo = getDBConnection();
$id = isset($_GET['id']) ? (int)$_GET['id'] : 0;
$subId = isset($_GET['sub_id']) ? (int)$_GET['sub_id'] : 0;

$htmlContent = '';
$baseUrl = '';

if ($subId > 0) {
    $stmt = $pdo->prepare("SELECT sub_page_html, sub_page_url FROM sub_pages WHERE id = :sub_id");
    $stmt->execute([':sub_id' => $subId]);
    $row = $stmt->fetch();
    if ($row) {
        $htmlContent = $row['sub_page_html'];
        $baseUrl = $row['sub_page_url'];
    }
} elseif ($id > 0) {
    $stmt = $pdo->prepare("SELECT full_html_content, source_url FROM knowledge_bank WHERE id = :id");
    $stmt->execute([':id' => $id]);
    $row = $stmt->fetch();
    if ($row) {
        $htmlContent = $row['full_html_content'];
        $baseUrl = $row['source_url'];
    }
}

if (empty($htmlContent)) {
    echo "<!DOCTYPE html><html><head><title>No Content</title></head><body style='font-family:sans-serif; padding:2rem; color:#666;'><h3>No HTML content available for this entry.</h3></body></html>";
    exit();
}

// 1. Neutralize Framebuster JS scripts so the modal iframe does not redirect the parent window
$htmlContent = preg_replace('/top\.location\s*=\s*[^;]+;/i', '// framebuster disabled', $htmlContent);
$htmlContent = preg_replace('/window\.top\.location\s*=\s*[^;]+;/i', '// framebuster disabled', $htmlContent);
$htmlContent = preg_replace('/if\s*\(\s*top\.location\s*!=\s*self\.location\s*\)/i', 'if (false)', $htmlContent);
$htmlContent = preg_replace('/if\s*\(\s*top\s*!=\s*self\s*\)/i', 'if (false)', $htmlContent);
$htmlContent = preg_replace('/target\s*=\s*["\']_top["\']/i', 'target="_blank"', $htmlContent);
$htmlContent = preg_replace('/target\s*=\s*["\']_parent["\']/i', 'target="_blank"', $htmlContent);

// 2. Rewrite all relative & root-relative URLs (href, src, action, url()) to absolute URLs
if (!empty($baseUrl)) {
    $parsed = parse_url($baseUrl);
    $scheme = $parsed['scheme'] ?? 'https';
    $host = $parsed['host'] ?? 'scaca.in';
    $domainRoot = $scheme . '://' . $host;

    $path = $parsed['path'] ?? '/';
    $dirPath = substr($path, 0, strrpos($path, '/') + 1);
    if (empty($dirPath)) {
        $dirPath = '/';
    }
    $baseDir = $domainRoot . $dirPath;

    $toAbs = function($url) use ($domainRoot, $baseDir) {
        $url = trim($url);
        if (empty($url)) return $url;
        if (preg_match('/^(https?:|\/\/|data:|javascript:|mailto:|#)/i', $url)) {
            if (strpos($url, '//') === 0) {
                return 'https:' . $url;
            }
            return $url;
        }
        if (strpos($url, '/') === 0) {
            return $domainRoot . $url;
        }
        return $baseDir . $url;
    };

    // Rewrite quoted href, src, action, poster, data-src attributes
    $htmlContent = preg_replace_callback('/(href|src|action|poster|data-src)\s*=\s*(["\'])(.*?)\2/i', function($matches) use ($toAbs) {
        $attr = $matches[1];
        $quote = $matches[2];
        $val = $matches[3];
        if (strpos($val, '#') === 0 || strpos(strtolower($val), 'javascript:') === 0) {
            return $matches[0];
        }
        $abs = $toAbs($val);
        return $attr . '=' . $quote . $abs . $quote;
    }, $htmlContent);

    // Rewrite unquoted href, src, action attributes
    $htmlContent = preg_replace_callback('/(href|src|action|poster|data-src)\s*=\s*([^"\'>\s]+)/i', function($matches) use ($toAbs) {
        $attr = $matches[1];
        $val = $matches[2];
        if (strpos($val, '#') === 0 || strpos(strtolower($val), 'javascript:') === 0) {
            return $matches[0];
        }
        $abs = $toAbs($val);
        return $attr . '="' . $abs . '"';
    }, $htmlContent);

    // Rewrite url(...) in inline styles or style tags
    $htmlContent = preg_replace_callback('/url\(\s*(["\']?)(.*?)\1\s*\)/i', function($matches) use ($toAbs) {
        $quote = $matches[1];
        $val = trim($matches[2]);
        if (empty($val) || preg_match('/^(data:|http:|https:|\/\/)/i', $val)) {
            return $matches[0];
        }
        $abs = $toAbs($val);
        return 'url(' . $quote . $abs . $quote . ')';
    }, $htmlContent);
}

// 3. Base tag & Framebuster Guard & Style enhancements for perfect layout
$headInjection = '';

if (!empty($baseUrl)) {
    $parsed = parse_url($baseUrl);
    $domainRoot = ($parsed['scheme'] ?? 'https') . '://' . ($parsed['host'] ?? 'scaca.in') . '/';
    $headInjection .= '<base href="' . htmlspecialchars($domainRoot) . '" target="_blank">';
}

$headInjection .= '<meta name="viewport" content="width=device-width, initial-scale=1.0">';
$headInjection .= '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">';
$headInjection .= '
<script>
  try {
    Object.defineProperty(window, "top", { get: function() { return window.self; } });
  } catch(e) {}
</script>
<style>
  html, body {
    width: 100% !important;
    background-color: #ffffff !important;
    margin: 0 !important;
    padding: 0 !important;
    box-sizing: border-box !important;
  }
  /* Fix nav hover dropdowns & list styles */
  .navbar-nav .dropdown:hover > .dropdown-menu {
    display: block !important;
  }
  .dropdown-menu {
    margin-top: 0;
  }
</style>
';

// Inject headInjection into <head> or at beginning of document
if (strpos($htmlContent, '<head>') !== false) {
    $htmlContent = str_replace('<head>', '<head>' . $headInjection, $htmlContent);
} else {
    $htmlContent = '<head>' . $headInjection . '</head>' . $htmlContent;
}

echo $htmlContent;
