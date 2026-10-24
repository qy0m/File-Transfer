<?php 

class TransferException extends RuntimeException
{
    public function __construct(
        public readonly int $status,
        string $message,
    ) {
        parent::__construct($message);
    }
}


function transfer_query_id(string $key): string
{
    $value = $_GET[$key] ?? '';

    if (
        !is_string($value) ||
        preg_match('/^[A-Za-z0-9_-]{32}$/D', $value) !== 1
    ) {
        throw new TransferException(
            404,
            'Transfer or file not found.',
        );
    }

    return $value;
}

function transfer_lookup(string $id): array
{
    if (preg_match('/^[A-Za-z0-9_-]{32}$/D', $id) !== 1) {
        throw new TransferException(404, 'Transfer not found.');
    }

    $base = rtrim(
        getenv('TRANSFER_API_URL') ?: 'http://api:8000',
        '/',
    );

    $context = stream_context_create([
        'http' => [
            'method' => 'GET',
            'header' => "Accept: application/json\r\nConnection: close\r\n",
            'timeout' => 8,
            'ignore_errors' => true,
            'follow_location' => 0,
        ],
    ]);

    $stream = @fopen(
        $base . '/transfers/' .$id,
        'rb',
        false,
        $context,
    );

    if ($stream == false) {
        throw new TransferException(
            503,
            'Transfer service unavailable',
        );
    }

    try {
        $metadata = stream_get_meta_data($stream);
        $status = 0;

        foreach (($metadata['wrapper_data'] ?? []) as $line) {
            if (preg_match('/^HTTP\/\S+\s+(\d{3})/', $line, $match)) {
                $status = (int) $match[1];
                break;
            }
        }

        $body = stream_get_contents($stream, 262_145);
        $metadata = stream_get_meta_data($stream);

        if (
            $body === false ||
            strlen($body) > 262_144 ||
            ($metadata['timed_out'] ?? false)
        ) {
            throw new TransferException(
                503,
                'Transfer service unavailable.',
            );
        }
    } finally {
        fclose($stream);
    }

    if ($status === 404) {
        throw new TransferException(
            404,
            'Transfer not found or incomplete.',
        );
    }

    if ($status === 410) {
        throw new TransferException(
            410,
            'This transfer has expired.',
        );
    }

    if ($status !== 200) {
        throw new TransferException(
            503,
            'Transfer service unavailable.',
        );
    }

    try {
        $data = json_decode(
            $body,
            true,
            64,
            JSON_THROW_ON_ERROR,
        );
    } catch (JsonException $error) {
        throw new TransferException(
            502,
            'Invalid transfer response.',
        );
    }

    if (
        !is_array($data) ||
        ($data['id'] ?? null) !== $id ||
        ($data['state'] ?? null) !== 'ready' ||
        !is_int($data['created_at'] ?? null) ||
        !is_int($data['expires_at'] ?? null) ||
        !is_int($data['total_bytes'] ?? null) ||
        $data['total_bytes'] < 0 ||
        $data['total_bytes'] > 5_000_000_000 ||
        !is_array($data['files'] ?? null) ||
        !array_is_list($data['files']) ||
        count($data['files']) < 1 ||
        count($data['files']) > 25
    ) {
        throw new TransferException(
            502,
            'Invalid transfer response.',
        );
    }

    if ($data['expires_at'] <= time()) {
        throw new TransferException(
            410,
            'This transfer has expired.',
        );
    }

    $seen = [];
    $total = 0;
    $files = [];

    foreach ($data['files'] as $file) {
        if (
            !is_array($file) ||
            !is_string($file['id'] ?? null) ||
            preg_match('/^[A-Za-z0-9_-]{32}$/D', $file['id']) !== 1 ||
            isset($seen[$file['id']]) ||
            !is_string($file['name'] ?? null) ||
            trim($file['name']) === '' ||
            strlen($file['name']) > 1020 ||
            str_contains($file['name'], '/') ||
            str_contains($file['name'], '\\') ||
            preg_match('/[\x00-\x1F\x7F]/', $file['name']) !== 0 ||
            !is_int($file['size_bytes'] ?? null) ||
            $file['size_bytes'] < 0 ||
            $file['size_bytes'] > 5_000_000_000
        ) {
            throw new TransferException(
                502,
                'Invalid file response.',
            );
        }

        $relativePath = $file['relative_path'] ?? $file['name'];

        if (
            !is_string($relativePath) ||
            $relativePath === '' ||
            strlen($relativePath) > 1024 ||
            str_contains($relativePath, chr(92)) ||
            preg_match('/[\x00-\x1F\x7F]/', $relativePath) !== 0 ||
            preg_match('/^[A-Za-z]:\//', $relativePath) === 1
        ) {
            throw new TransferException(
                502,
                'Invalid folder path.',
            );
        }

        $parts = explode('/', $relativePath);

        foreach ($parts as $part) {
            if ($part === '' || $part === '.' || $part === '..') {
                throw new TransferException(
                    502,
                    'Invalid folder path.',
                );
            }
        }

        if (end($parts) !== $file['name']) {
            throw new TransferException(
                502,
                'Invalid folder path.',
            );
        }

        $seen[$file['id']] = true;
        $total += $file['size_bytes'];

        $files[] = [
            'id' => $file['id'],
            'name' => $file['name'],
            'relative_path' => $relativePath,
            'size_bytes' => $file['size_bytes'],
        ];
    }

    if ($total !== $data['total_bytes']) {
        throw new TransferException(
            502,
            'Invalid transfer size.',
        );
    }

    return [
        'id' => $id,
        'created_at' => $data['created_at'],
        'expires_at' => $data['expires_at'],
        'total_bytes' => $total,
        'files' => $files,
    ];
}

function transfer_format_bytes(int $bytes): string
{
    if ($bytes < 1000) {
        return $bytes . ' B';
    }

    if ($bytes < 1_000_000) {
        return number_format($bytes / 1000, 1) . ' KB';
    }

    if ($bytes < 1_000_000_000) {
        return number_format($bytes / 1_000_000, 1) . ' MB';
    }

    return number_format($bytes / 1_000_000_000, 2) . ' GB';
}