<?php

require_once __DIR__ . '/../includes/transfers.php';


function download_error(int $status, string $message): never
{
    http_response_code($status);

    header('Content-Type: text/plain; charset=utf-8');
    header('Cache-Control: no-store');
    header('X-Content-Type-Options: nosniff');

    echo $message;
    exit;
}


$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';

if (!in_array($method, ['GET', 'HEAD'], true)) {
    header('Allow: GET, HEAD');
    download_error(405, 'Method not allowed.');
}

try {
    $transferId = transfer_query_id('transfer');

    if (($_GET['archive'] ?? '') === '1') {
        $path = '/transfers/' . $transferId . '/archive';
        $folder = $_GET['folder'] ?? null;

        if ($folder !== null) {
            if (
                !is_string($folder) ||
                $folder === '' ||
                strlen($folder) > 1024
            ) {
                download_error(400, 'Invalid folder path.');
            }

            $path .= '?folder=' . rawurlencode($folder);
        }
    } else {
        $fileId = transfer_query_id('file');

        $path = '/transfers/' . $transferId .
            '/files/' . $fileId . '/download';
    }
} catch (TransferException $error) {
    download_error(
        $error->status,
        $error->getMessage(),
    );
}

$base = rtrim(
    getenv('TRANSFER_API_URL') ?: 'http://api:8000',
    '/',
);

$context = stream_context_create([
    'http' => [
        'method' => 'GET',
        'header' => "Connection: close\r\n",
        'timeout' => 30,
        'ignore_errors' => true,
        'follow_location' => 0,
    ],
]);

$stream = @fopen(
    $base . $path,
    'rb',
    false,
    $context,
);

if ($stream === false) {
    download_error(503, 'Download service unavailable.');
}

$metadata = stream_get_meta_data($stream);
$status = 0;
$headers = [];

foreach (($metadata['wrapper_data'] ?? []) as $line) {
    if (preg_match('/^HTTP\/\S+\s+(\d{3})/', $line, $match)) {
        $status = (int) $match[1];
    } elseif (str_contains($line, ':')) {
        [$key, $value] = explode(':', $line, 2);

        $headers[strtolower(trim($key))] = trim($value);
    }
}

if ($status !== 200) {
    $body = stream_get_contents($stream, 65_536);
    fclose($stream);

    $data = is_string($body)
        ? json_decode($body, true)
        : null;

    $message = is_array($data) &&
        is_string($data['detail'] ?? null)
        ? $data['detail']
        : 'Download unavailable.';

    download_error(
        $status >= 400 && $status <= 599 ? $status : 502,
        $message,
    );
}

ini_set('zlib.output_compression', '0');

while (ob_get_level() > 0) {
    if (!ob_end_clean()) break;
}

header(
    'Content-Type: ' .
    ($headers['content-type'] ?? 'application/octet-stream')
);

if (isset($headers['content-disposition'])) {
    header(
        'Content-Disposition: ' .
        $headers['content-disposition']
    );
}

if (
    isset($headers['content-length']) &&
    ctype_digit($headers['content-length'])
) {
    header('Content-Length: ' . $headers['content-length']);
}

header('Cache-Control: no-store');
header('Referrer-Policy: no-referrer');
header('X-Content-Type-Options: nosniff');
header('X-Accel-Buffering: no');

if ($method === 'HEAD') {
    fclose($stream);
    exit;
}

set_time_limit(0);

while (!feof($stream) && !connection_aborted()) {
    $chunk = fread($stream, 64 * 1024);

    if ($chunk === false || $chunk === '') break;

    echo $chunk;
    flush();
}

fclose($stream);
exit;