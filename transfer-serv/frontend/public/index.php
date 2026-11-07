<?php

$title = 'Transfer Service — Upload';

require __DIR__ . '/../includes/header.php';
?>

<div class="row justify-content-center">
    <div class="col-12 site-column">
<header class="page-intro">
<span class="icon-badge tone-red"><?php filevoya_icon('cloud-arrow-up'); ?></span>
        <p class="text-uppercase text-secondary small fw-semibold">
            Simple file sharing
        </p>

        <h1 class="display-5 fw-bold mb-3">
            Send files.<br><span class="accent-text">Share a link.</span>
        </h1>

        <p class="lead text-secondary">
            <span id="upload-file-limit">
                Choose files or a folder, with up to 25 files per transfer.
            </span>

            <span id="upload-allowance">
                Checking your upload allowance...
            </span>
        </p>

        </header>

        <p class="small text-secondary">
            New transfers are end-to-end encrypted in your browser, including filenames.
            Save the full share link: its key cannot be recovered by Transfer Service.
            Encryption overhead counts toward your storage allowance.
        </p>

        <section
            id="drop-zone"
            class="card shadow-sm border-0 mt-4 upload-area"
            aria-labelledby="upload-heading"
        >
            <div
                id="drop-overlay"
                class="upload-drop-overlay"
                hidden
                aria-hidden="true"
            >
                <div>
                    <strong>Drop files or folders here</strong>
                    <span>Review your selection before uploading</span>
                </div>
            </div>

            <div class="card-body p-4">
                <h2 id="upload-heading" class="h5 mb-3">
                    <span class="icon-badge tone-amber"><?php filevoya_icon('folder-plus'); ?></span>
                    Select your files
                </h2>

                <label for="files" class="form-label">
                    Files to transfer
                </label>

                <div class="dropdown mb-3">
                    <button
                        id="upload-picker"
                        type="button"
                        class="btn btn-secondary btn-sm dropdown-toggle"
                        data-bs-toggle="dropdown"
                        aria-expanded="false"
                    >
                        Upload
                    </button>

                    <ul
                        class="dropdown-menu dropdown-menu-dark"
                        aria-labelledby="upload-picker"
                    >
                        <li>
                            <button
                                id="browse-files"
                                type="button"
                                class="dropdown-item"
                            >
                                Browse files
                            </button>
                        </li>

                        <li>
                            <button
                                id="browse-folder"
                                type="button"
                                class="dropdown-item"
                            >
                                Browse folder
                            </button>
                        </li>
                    </ul>
                </div>

                <p class="small text-secondary mb-3">
                    Or drag files or folders onto this panel.
                </p>

                <input
                    id="files"
                    type="file"
                    multiple
                    hidden
                    aria-describedby="selection-status"
                >

                <input
                    id="folder-files"
                    type="file"
                    webkitdirectory
                    multiple
                    hidden
                    aria-describedby="selection-status"
                >

                <p class="small text-secondary mt-2 mb-0">
                    Folder selection includes files in subfolders.
                    Empty folders are not included.
                    A new selection replaces the previous selection.
                </p>

                <p
                    id="selection-status"
                    class="small text-secondary mt-3"
                    role="status"
                >
                    No files selected.
                </p>

                <ul
                    id="file-list"
                    class="list-group list-group-flush mb-3"
                ></ul>

                <p class="small text-secondary">
                    Uploading files is subject to our
                    <a href="/terms.php">Terms of Service</a>.
                </p>

                <button
                    id="upload-button"
                    class="btn btn-primary w-100"
                    type="button"
                    disabled
                >
                    Upload files
                </button>

                <div class="mt-4">
                    <label
                        for="upload-progress"
                        class="form-label small"
                    >
                        Overall upload progress
                    </label>

                    <progress
                        id="upload-progress"
                        class="upload-progress"
                        max="100"
                        value="0"
                        aria-describedby="progress-details"
                    ></progress>

                    <p
                        id="progress-details"
                        class="small text-secondary mt-2 mb-0"
                    >
                        0% · 0 B of 0 B
                    </p>
                </div>

                <p
                    id="upload-status"
                    class="small text-secondary mt-3"
                    role="status"
                ></p>

                <section
                    id="share-result"
                    class="border rounded p-3 mb-3"
                    aria-labelledby="share-heading"
                    hidden
                >

                    <h3 id="share-heading" class="h6">
                        Your files are ready to share
                    </h3>

                    <label for="share-link" class="form-label small">
                        Share link:
                    </label>

                    <input
                        id="share-link"
                        type="text"
                        class="form-control"
                        readonly
                    >

                    <div class="d-flex flex-wrap gap-2 mt-3">
                        <button
                            id="copy-link"
                            type="button"
                            class="btn btn-primary btn-sm"
                        >
                            Copy link
                        </button>

                        <a
                            id="open-transfer"
                            class="btn btn-outline-primary btn-sm"
                            href="/"
                        >

                            Open download page
                        </a>
                    </div>

                    <p id="copy-status" class="small mt-2 mb-0" role="status"></p>

                    <p class="small text-secondary mt-2 mb-0">
                        Anyone with this link can download the files
                        until the transfer expires.
                    </p>
                </section>

                <p class="small text-secondary mb-0">
                    Available for 24 hours after creation.
                    Expired files are automatically deleted.
                </p>

                <p class="small text-secondary mt-3 mb-0">
                    Each account or guest browser includes
                    5 GB of total upload storage.
                    <a href="/storage.php">
                        Check your remaining storage
                    </a>
                </p>
            </div>
        </section>

        <p
            id="service-status"
            class="small text-secondary mt-4"
            role="status"
        >
            Checking service connection…
        </p>
    </div>
</div>

<dialog
    id="drop-confirmation"
    class="upload-confirmation"
    aria-labelledby="drop-title"
    aria-describedby="drop-summary"
>
    <h2 id="drop-title" class="h5">
        Upload your files?
    </h2>

    <p id="drop-summary" class="text-secondary small"></p>

    <ul
        id="drop-file-list"
        class="upload-review-list"
    ></ul>

    <p class="small text-secondary">
        Folder structure will be preserved.
        Files expire after 24 hours.
        This replaces any previous selection on this page.
    </p>

    <div class="d-flex justify-content-end gap-2 mt-4">
        <button
            id="drop-cancel"
            type="button"
            class="btn btn-secondary"
            autofocus
        >
            Cancel
        </button>

        <button
            id="drop-upload"
            type="button"
            class="btn btn-primary"
        >
            Upload
        </button>
    </div>
</dialog>

<?php require __DIR__ . '/../includes/footer.php'; ?>