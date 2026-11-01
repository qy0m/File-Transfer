<?php

$title = 'About — Filevoya';
$pageStylesheets = ['/assets/css/about.css'];

require __DIR__ . '/../includes/header.php';

function filevoya_about_icon(string $name): void
{
    filevoya_icon($name, 'about-icon');
}

$features = [
    [
        'shield-lock',
        'amber',
        'Encrypted connections',
        'HTTPS protects traffic to the public website. WireGuard encrypts the connection between the public relay and the storage server.',
    ],
    [
        'hdd',
        'red',
        'Encrypted storage',
        'Files stay on our self-hosted storage server. Its data partition and swap are encrypted. Disk encryption protects stored data while the volume is locked.',
    ],
    [
        'person-check',
        'violet',
        'Protected accounts',
        'Passwords are hashed with Argon2. Secure session settings and ownership checks protect account access and transfer management.',
    ],
    [
        'cloud-arrow-up',
        'amber',
        'Validated uploads',
        'File paths, sizes, upload tokens, and chunk offsets are checked. Request limits and pending-upload limits help reduce abuse.',
    ],
];
?>

<div class="reading-column about-page">
    <header class="about-hero">
        <span class="about-eyebrow">
            <?php filevoya_about_icon('cloud-arrow-up'); ?>
            About Filevoya
        </span>

        <h1>
            Simple sharing.<br>
            <span>Clear privacy.</span>
        </h1>

        <p class="about-intro">
            Files and folders, shared on your terms. Upload without an
            account, send an expiring link, and understand how your files
            are protected.
        </p>

        <div class="d-flex flex-wrap gap-2">
            <a class="btn btn-primary" href="/">
                <?php filevoya_about_icon('cloud-arrow-up'); ?>
                Share files
            </a>

            <a
                class="btn btn-outline-primary"
                href="https://github.com/qy0m/File-Transfer"
                rel="noreferrer"
            >
                <?php filevoya_about_icon('github'); ?>
                View the source
            </a>
        </div>

        <dl class="about-stats">
            <div>
                <dt>5 GB</dt>
                <dd>Regular storage allowance</dd>
            </div>

            <div>
                <dt>25 files</dt>
                <dd>Per regular transfer</dd>
            </div>

            <div>
                <dt>24 hours</dt>
                <dd>Until a transfer expires</dd>
            </div>
        </dl>
    </header>

    <section
        class="about-panel about-guest"
        aria-labelledby="guest-heading"
    >
        <span class="about-icon-box about-tone-red">
            <?php filevoya_about_icon('incognito'); ?>
        </span>

        <div>
            <p class="about-kicker">No registration required</p>

            <h2 id="guest-heading">
                Guest sharing, with clear boundaries.
            </h2>

            <p>
                No email address or account is needed to upload.
                A guest cookie identifies your browser to track its
                storage allowance. An optional account gives you a
                dashboard for managing your transfers.
            </p>

            <p class="about-muted mb-0">
                Guest access does not guarantee anonymity. IP addresses
                are processed for request limits, and connection
                information may appear in server or hosting-provider logs.
            </p>
        </div>
    </section>

    <section
        class="about-section"
        aria-labelledby="security-heading"
    >
        <div class="about-section-heading">
            <p class="about-kicker">Protection at each layer</p>

            <h2 id="security-heading">
                How your transfers are protected
            </h2>
        </div>

        <div class="row g-3">
            <?php foreach ($features as [$icon, $tone, $heading, $description]): ?>
                <div class="col-md-6">
                    <article class="about-feature about-panel h-100">
                        <span class="about-icon-box about-tone-<?= escape($tone) ?>">
                            <?php filevoya_about_icon($icon); ?>
                        </span>

                        <h3><?= escape($heading) ?></h3>

                        <p class="about-muted mb-0">
                            <?= escape($description) ?>
                        </p>
                    </article>
                </div>
            <?php endforeach; ?>
        </div>
    </section>

    <section
        class="about-panel about-lifetime"
        aria-labelledby="lifetime-heading"
    >
        <div class="about-section-heading">
            <p class="about-kicker">Made for temporary sharing</p>

            <h2 id="lifetime-heading">
                A link with an expiration date.
            </h2>
        </div>

        <div class="row g-4">
            <div class="col-md-6">
                <h3 class="about-inline-heading">
                    <?php filevoya_about_icon('hourglass-split'); ?>
                    Automatic expiration
                </h3>

                <p class="about-muted mb-0">
                    Transfers expire after 24 hours and are cleaned up
                    automatically. Pending uploads expire after
                    15 minutes without a successful chunk. Account owners
                    can delete their transfers sooner.
                </p>
            </div>

            <div class="col-md-6">
                <h3 class="about-inline-heading">
                    <?php filevoya_about_icon('link-45deg'); ?>
                    Keep your link private
                </h3>

                <p class="about-muted mb-0">
                    Anyone with a share link can download its available
                    files. Expiration or deletion stops access through
                    Filevoya; it cannot remove copies someone has
                    already downloaded.
                </p>
            </div>
        </div>
    </section>

    <section
        class="about-disclosure"
        aria-labelledby="limits-heading"
    >
        <span class="about-icon-box about-tone-amber">
            <?php filevoya_about_icon('shield-lock'); ?>
        </span>

        <div>
            <h2 id="limits-heading">
                A clear word about encryption
            </h2>

            <p class="mb-0">
                New browser uploads are end-to-end encrypted,
                including file contents, names, and folder paths. The full
                share link contains the key; Filevoya cannot recover it.
                Older transfers remain unencrypted until they expire.
                The server still sees encrypted sizes, file counts, account
                ownership, and connection information. Encryption relies on
                trustworthy browser code delivered by this website.
            </p>
        </div>
    </section>
</div>

<?php require __DIR__ . '/../includes/footer.php'; ?>