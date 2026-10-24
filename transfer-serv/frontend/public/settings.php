<?php

$title = 'Settings - File Transfer';

header('Cache-Control: no-store');

require __DIR__ . '/../includes/header.php';
?>

<div class="reading-column auth-column">
    <p class="text-uppercase text-secondary small fw-semibold">
        Your account
    </p>

    <h1 class="fw-bold mb-4">Settings</h1>

    <section class="card mb-4">
        <div class="card-body">
            <h2 class="h5 mb-3">Account information</h2>

            <label
                for="settings-username"
                class="form-label"
            >
                Username
            </label>

            <input
                id="settings-username"
                class="form-control"
                type="text"
                readonly
            >
        </div>
    </section>

    <section class="card">
        <div class="card-body">
            <h2 class="h5 mb-3">Change password</h2>

            <p
                id="settings-password-help"
                class="small text-secondary"
            >
                Use at least 12 characters. Updating your password
                signs out every session, including this one.
            </p>

            <form
                id="settings-form"
                method="post"
                action="/settings.php"
                aria-describedby="settings-password-help"
            >
                <div class="mb-3">
                    <label
                        for="settings-current-password"
                        class="form-label"
                    >
                        Current password
                    </label>

                    <input
                        id="settings-current-password"
                        class="form-control"
                        type="password"
                        name="current-password"
                        maxlength="128"
                        required
                    >
                </div>

                <div class="mb-3">
                    <label
                        for="settings-new-password"
                        class="form-label"
                    >
                        New password
                    </label>

                    <input
                        id="settings-new-password"
                        class="form-control"
                        type="password"
                        name="new_password"
                        autocomplete="new-password"
                        minlength="12"
                        maxlength="128"
                        required
                    >
                </div>

                <div class="mb-3">
                    <label
                        for="settings-confirm-password"
                        class="form-label"
                    >
                        Confirm new password
                    </label>

                    <input
                        id="settings-confirm-password"
                        class="form-control"
                        type="password"
                        name="password_confirmation"
                        autocomplete="new-password"
                        minlength="12"
                        maxlength="128"
                        required
                    >
                </div>

                <button
                    id="settings-submit"
                    class="btn btn-primary w-100"
                    type="submit"
                    disabled
                >
                    Update password
                </button>

                <p
                    id="settings-status"
                    class="small mt-3 mb-0"
                    role="status"
                >
                    Checking your account...
                </p>
            </form>
        </div>
    </section>

    <a
        href="/dashboard.php"
        class="d-inline-block mt-4"
    >
        Back to your files
    </a>

    <noscript>
        <p class="text-warning mt-3">
            Enable JavaScript to use account settings.
        </p>
    </noscript>
</div>

<?php require __DIR__ . '/../includes/footer.php'; ?>