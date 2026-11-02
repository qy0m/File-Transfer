<?php

$title = 'Storage - Filevoya';

header('Cache-Control: no-store');

require __DIR__ . '/../includes/header.php';
?>

<div id="storage-page" class="row justify-content-center">
    <div class="col-12 site-column">
<header class="page-intro">
<span class="icon-badge tone-teal"><?php filevoya_icon('hdd'); ?></span>
        <p class="text-uppercase text-secondary small fw-semibold">
            Your allowance
        </p>

        <h1 class="display-5 fw-bold mb-3">
            Upload storage
        </h1>

        <p
            id="storage-context"
            class="lead text-secondary"
            role="status"
        >
            Checking your storage allowance...
        </p>

        <div class="d-flex flex-wrap gap-2 mb-4">
            <a href="/" class="btn btn-outline-secondary">
                Back to uploads
            </a>

            <button
                id="dashboard-refresh"
                type="button"
                class="btn btn-primary"
            >
                Refresh
            </button>
        </div>

        </header>

        <?php require __DIR__ . '/../includes/storage-panel.php'; ?>

        <p class="small text-secondary">
            Pending uploads reserve space immediately.
            Space becomes available again after uploaded files
            are deleted or removed by automatic cleanup.
        </p>
    </div>
</div>

<?php require __DIR__ . '/../includes/footer.php'; ?>