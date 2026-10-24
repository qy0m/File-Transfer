<?php

$register = ($accountMode ?? 'login') === 'register';

$title = $register
    ? 'Create account — File Transfer'
    : 'Sign in — File Transfer';

header('Cache-Control: no-store');

require __DIR__ . '/header.php';
?>

<div class="reading-column auth-column">
    <p class="text-uppercase text-secondary small fw-semibold">
        Your account
    </p>

    <h1 class="fw-bold mb-3">
        <?= $register ? 'Create an account' : 'Welcome back' ?>
    </h1>

    <p class="text-secondary">
        Keep your current uploads together in one dashboard.
    </p>

    <section class="card mt-4">
        <div class="card-body">
            <form
                id="account-form"
                data-mode="<?= $register ? 'register' : 'login' ?>"
                method="post"
                action="<?= $register ? '/register.php' : '/login.php' ?>"
            >
                <div class="mb-3">
                    <label
                        for="account-username"
                        class="form-label"
                    >
                        Username
                    </label>

                    <input
                        id="account-username"
                        name="username"
                        type="text"
                        class="form-control"
                        autocomplete="username"
                        autocapitalize="none"
                        spellcheck="false"
                        minlength="3"
                        maxlength="32"
                        pattern="[A-Za-z0-9_\-]{3,32}"
                        aria-describedby="username-help"
                        required
                    >

                    <p
                        id="username-help"
                        class="small text-secondary mt-2 mb-0"
                    >
                        3–32 letters, numbers, underscores, or hyphens.
                    </p>
                </div>

                <div class="mb-3">
                    <label
                        for="account-password"
                        class="form-label"
                    >
                        Password
                    </label>

                    <input
                        id="account-password"
                        name="password"
                        type="password"
                        class="form-control"
                        autocomplete="<?= $register ? 'new-password' : 'current-password' ?>"
                        minlength="12"
                        maxlength="128"
                        required
                    >

                    <?php if ($register): ?>
                        <p class="small text-secondary mt-2 mb-0">
                            Use at least 12 characters.
                        </p>
                    <?php endif; ?>
                </div>

                <?php if ($register): ?>
                    <div class="mb-3">
                        <label
                            for="account-confirm"
                            class="form-label"
                        >
                            Confirm password
                        </label>

                        <input
                            id="account-confirm"
                            name="password_confirmation"
                            type="password"
                            class="form-control"
                            autocomplete="new-password"
                            minlength="12"
                            maxlength="128"
                            required
                        >
                    </div>
                <?php endif; ?>

                <button
                    id="account-submit"
                    type="submit"
                    class="btn btn-primary w-100"
                    disabled
                >
                    <?= $register ? 'Create account' : 'Sign in' ?>
                </button>

                <p
                    id="account-form-status"
                    class="small mt-3 mb-0"
                    role="status"
                ></p>
            </form>

            <noscript>
                <p class="text-warning mt-3">
                    Enable JavaScript to use account features.
                </p>
            </noscript>
        </div>
    </section>

    <p class="small text-secondary mt-4">
        <?php if ($register): ?>
            Already have an account?
            <a href="/login.php">Sign in</a>.
        <?php else: ?>
            New here?
            <a href="/register.php">Create an account</a>.
        <?php endif; ?>
    </p>
</div>

<?php require __DIR__ . '/footer.php'; ?>