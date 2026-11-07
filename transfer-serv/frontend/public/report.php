<?php
$title = 'Report abuse - Transfer Service';
header('Cache-Control: no-store');
header('Referrer-Policy: no-referrer');
header('X-Robots-Tag: noindex');

require __DIR__ . '/../includes/header.php';

$transferId = $_GET['transfer'] ?? '';
if (
    !is_string($transferId) ||
    preg_match('/^[A-Za-z0-9_-]{32}$/D', $transferId) !== 1
) {
    $transferId = '';
}
?>

<div class="reading-column auth-column">
    <header class="page-intro">
        <span class="icon-badge tone-amber">
            <?php filevoya_icon('exclamation-circle'); ?>
        </span>
        <h1>Report Abuse</h1>
        <p class="lead">
            Report suspected malware, phishing, unlawful content,
            indecent material, copyrighted material, or a privacy violation.
        </p>
    </header>

    <section class="card">
        <div class="card-body">
            <p>
                Files must not be used to distribute malware, commit fraud,
                share unlawful material, share unwanted indecent material, infringe copyrighted content,
                or violate another person's privacy or rights.
            </p>
            <p>
                Reports contain a transfer ID, a category, and any optional
                description you provide. The description is stored as text
                that administrators can read; it is not end-to-end encrypted.
                If you paste a full share link in the link field, its key is removed
                in your browser before submission.
                Do not send file contents or decryption keys.
            </p>
            <p>
                Transfer Service cannot inspect end-to-end encrypted file contents.
                An administrator can disable a transfer without decrypting it.
                Reports are scheduled for deletion after 30 days.
                A hash derived from the reporting connection's IP address
                is stored for abuse control. Reports are reviewed manually;
                removal is not automatic or guaranteed.
            </p>

            <form id="abuse-form" method="post" action="/report.php">
                <label class="form-label" for="abuse-transfer">
                    Share link or transfer ID
                </label>
                <input
                    id="abuse-transfer"
                    class="form-control mb-3"
                    type="text"
                    maxlength="2048"
                    value="<?= escape($transferId) ?>"
                    autocomplete="off"
                    spellcheck="false"
                    required
                >

                <label class="form-label" for="abuse-category">
                    Reason
                </label>
                <select
                    id="abuse-category"
                    class="form-select mb-3"
                    required
                >
                    <option value="">Choose a reason</option>
                    <option value="malware">Malware</option>
                    <option value="phishing">Phishing or fraud</option>
                    <option value="illegal">Unlawful content</option>
                    <option value="indecent">Indecent material</option>
                    <option value="copyright">Copyright infringement</option>
                    <option value="privacy">Privacy or right violation</option>
                    <option value="other">Other abuse</option>
                </select>

                <label class="form-label" for="abuse-description">
                    Description (optional)
                </label>
                <textarea
                    id="abuse-description"
                    class="form-control mb-2"
                    rows="5"
                    maxlength="2000"
                    autocomplete="off"
                    spellcheck="false"
                    aria-describedby="abuse-description-help"
                ></textarea>
                <p id="abuse-description-help" class="small text-secondary mb-3">
                    Up to 2,000 characters. Briefly explain the issue.
                    Do not include decryption keys, passwords, personal
                    information, or file contents. Include copyrighted work
                    details only as needed to identify the alleged infringement.
                </p>

                <button
                    id="abuse-submit"
                    class="btn btn-primary"
                    type="submit"
                >
                    Submit report
                </button>
            </form>

            <p
                id="abuse-status"
                class="text-secondary mt-3 mb-0"
                role="status"
                aria-live="polite"
            ></p>

            <noscript>
                <p>
                    Enable JavaScript to submit a report without sending
                    a decryption key.
                </p>
            </noscript>
        </div>
    </section>
</div>

<script type="module" src="/assets/js/abuse.js"></script>

<?php require __DIR__ . '/../includes/footer.php'; ?>