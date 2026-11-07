<?php

function escape(string $value): string
{
    return htmlspecialchars(
        $value,
        ENT_QUOTES | ENT_SUBSTITUTE,
        'UTF-8'
    );
}

function filevoya_icon(string $name, string $class = 'site-icon'): void
{
    ?>
    <svg
        class="<?= escape($class) ?>"
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
        focusable="false"
    >
        <use href="/assets/icons/site-icons.svg#<?= escape($name) ?>"></use>
    </svg>
    <?php
}

$title = $title ?? 'Transfer Service';
?>
<!doctype html>
<html lang="en" data-bs-theme="dark">
<head>
    <meta charset="utf-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1"
    >

    <title><?= escape($title) ?></title>

    <?php require __DIR__ . "/metadata.php"; ?>

    <link
        rel="stylesheet"
        href="/assets/vendor/bootstrap/bootstrap.min.css"
    >

    <link
        rel="stylesheet"
        href="/assets/css/styles.css"
    >

    <link rel="stylesheet" href="/assets/css/theme.css">

    <?php foreach (($pageStylesheets ?? []) as $stylesheet): ?>
        <link
            rel="stylesheet"
            href="<?= escape($stylesheet) ?>"
        >
    <?php endforeach; ?>

    <link rel="stylesheet" href="/assets/css/modern.css">
</head>
<body>
<nav class="navbar site-nav" aria-label="Main navigation">
    <div class="container">
        <a class="navbar-brand fw-bold" href="/">
            <?php filevoya_icon('cloud-arrow-up'); ?>
            Transfer Service
        </a>

        <div class="site-nav-links">
            <a class="nav-link" href="/about.php">
                About
            </a>

            <span
                id="account-status"
                class="small text-secondary"
                role="status"
            >
                Checking account...
            </span>

            <div id="account-guest" hidden>
                <div class="d-flex align-items-center gap-2">
                    <a class="nav-link" href="/login.php">
                        Sign in
                    </a>

                    <a
                        class="btn btn-primary btn-sm"
                        href="/register.php"
                    >
                        Create account
                    </a>
                </div>
            </div>

            <div id="account-member" hidden>
                <div class="d-flex align-items-center gap-2">
                    <a class="nav-link" href="/dashboard.php">
                        Your files
                    </a>

                    <div class="dropdown account-dropdown">
                        <button
                            id="account-name"
                            class="btn btn-outline-primary btn-sm dropdown-toggle"
                            type="button"
                            data-bs-toggle="dropdown"
                            aria-expanded="false"
                        ></button>

                        <ul
                            class="dropdown-menu dropdown-menu-end"
                            aria-labelledby="account-name"
                        >
                            <li>
                                <a
                                    class="dropdown-item"
                                    href="/settings.php"
                                >
                                    Settings
                                </a>
                            </li>

                            <li>
                                <hr class="dropdown-divider">
                            </li>

                            <li>
                                <button
                                    id="account-logout"
                                    class="dropdown-item"
                                    type="button"
                                >
                                    Sign out
                                </button>
                            </li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    </div>
</nav>

<main class="container py-5">
