<?php

$title = 'Your files - File Transfer';

header('Cache-Control: no-store');

require __DIR__ . '/../includes/header.php';
?>


<div class="dashbaord-column">
    <div class="d-flex flex-wrap align-items-center justify-content-between gap-3">
        <div>
            <p class="text-uppercase text-secondary small fw-semibold">
                Account dashboard
            </p>

            <h1 class="fw-bold mb-0">Your files</h1>
        </div>

        <a href="/" class="btn btn-primary">
            Upload files
        </a>
    </div>

    <p class="text-secondary mt-3">
        Your current transfers, including uploads still in progress.
        Files expire 24 hours after their transfer is created.
    </p>

    <p class="small text-secondary">
        Keep the upload page open to resume an interrupted upload.
    </p>

    <div class="d-flex flex-wrap align-items-center justify-content-between gap-2 my-4">
        <p
            id="dashboard-summary"
            class="small text-secondary mb-0"
        ></p>

        <button
            id="dashboard-refresh"
            class="btn btn-outline-primary btn-sm"
            type="button"
        >
            Refresh
        </button>
    </div>


    <p
        id="dashboard-status"
        class="small text-secondary"
        role="status"
    >
        Checking your account...
    </p>

    <?php require __DIR__ . '/../includes/storage-panel.php'; ?>

    <div id="dashboard-empty" class="card" hidden>
        <div class="card-body">
            <h2 class="h5">No current files</h2>

            <p class="text-secondary mb-0">
                Upload files while signed in to see them here.
                Expired transfers are removed automatically.
            </p>
        </div>
    </div>

    <div id="dashboard-list"></div>

    <nav
        class="d-flex gap-2 mt-4"
        aria-label="Dashboard pages"
    >
        <button
            id="dashboard-prev"
            class="btn btn-outline-primary btn-sm"
            type="button"
            disabled
        >
            Previous
        </button>

        <button
            id="dashboard-next"
            class="btn btn-outline-primary btn-sm"
            type="button"
            disabled
        >
            Next
        </button>
    </nav>

    <noscript>
        <p class="text-warning mt-3">
            Enabled JavaScript to view your account dashboard.
        </p>
    </noscript>
</div>

<?php require __DIR__ . '/../includes/footer.php'; ?>