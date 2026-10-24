<?php

require_once __DIR__ . '/../includes/transfers.php';

header('Cache-Control: no-store');
header('Referrer-Policy: no-referrer');

$transfer = null;
$errorMessage = null;

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';

try {
    if (!in_array($method, ['GET', 'HEAD'], true)) {
        header('Allow: GET, HEAD');

        throw new TransferException(
            405,
            'Method not allowed.',
        );
    }

    $id = transfer_query_id('id');
    $transfer = transfer_lookup($id);
} catch (TransferException $error) {
    http_response_code($error->status);
    $errorMessage = $error->getMessage();
}

$title = $transfer
    ? 'Download files — File Transfer'
    : 'Transfer unavailable';

require __DIR__ . '/../includes/header.php';
?>

<div class="reading-column">
    <?php if ($transfer === null): ?>
        <h1 class="fw-bold">
            Transfer unavailable
        </h1>

        <p class="lead text-secondary">
            <?= escape($errorMessage ?? 'Transfer unavailable.') ?>
        </p>

        <a href="/" class="btn btn-primary">
            Send your own files
        </a>
    <?php else: ?>
        <p class="text-uppercase text-secondary small fw-semibold">
            Files shared with you
        </p>

        <h1 class="fw-bold mb-3">
            Download your files
        </h1>

        <p class="lead text-secondary">
            <?= count($transfer['files']) ?> file(s) ·
            <?= escape(transfer_format_bytes($transfer['total_bytes'])) ?>
        </p>

        <p class="small text-secondary">
            Available until
            <?= escape(gmdate('Y-m-d H:i:s', $transfer['expires_at'])) ?>
            UTC.
        </p>

        <?php
        require_once __DIR__ . '/../includes/folder-tree.php';
        ?>

        <div class="mt-4">
            <div data-folder-actions class="mb-4">
                <div class="dropdown">
                    <button
                        id="transfer-download-menu"
                        type="button"
                        class="btn btn-primary dropdown-toggle"
                        data-bs-toggle="dropdown"
                        aria-expanded="false"
                    >
                        Download
                    </button>

                    <ul
                        class="dropdown-menu dropdown-menu-dark"
                        aria-labelledby="transfer-download-menu"
                    >
                        <li>
                            <button
                                type="button"
                                class="dropdown-item"
                                data-download-folder
                                data-download-all="true"
                                data-transfer-id="<?= escape($transfer['id']) ?>"
                            >
                                Standard download
                            </button>
                        </li>

                        <li>
                            <a
                                class="dropdown-item"
                                href="<?= escape(transfer_download_url(
                                    $transfer['id'],
                                    ['archive' => '1'],
                                )) ?>"
                            >
                                Download as a ZIP file
                            </a>
                        </li>
                    </ul>
                </div>

                <p
                    class="small text-secondary mt-2 mb-0"
                    data-folder-status
                    role="status"
                >
                    Standard download saves a new copy with its folder structure.
                    Keep this page open while saving.
                </p>
            </div>

            <?php
            transfer_render_tree(
                transfer_build_tree($transfer['files']),
                $transfer['id'],
            );
            ?>
        </div>

        <a href="/" class="d-inline-block mt-4">
            Send your own files
        </a>
    <?php endif; ?>
</div>

<?php require __DIR__ . '/../includes/footer.php'; ?>