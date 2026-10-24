<?php

function escape(string $value): string
{
    return htmlspecialchars(
        $value,
        ENT_QUOTES | ENT_SUBSTITUTE,
        'UTF-8'
    );
}

$title = $title ?? 'File Transfer';
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

    <link
        rel="stylesheet"
        href="/assets/vendor/bootstrap/bootstrap.min.css"
    >

    <link
        rel="stylesheet"
        href="/assets/css/styles.css"
    >
</head>
<body>
<nav class="navbar site-nav" aria-label="Main navigation">
    <div class="container">
        <a class="navbar-brand fw-bold" href="/">
            File Transfer
        </a>

        <div class="site-nav-links">
            <a class="nav-links" href="/about.php">
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
