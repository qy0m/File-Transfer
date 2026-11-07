<?php
// Public metadata never uses Host, query strings, or decryption keys.
$publicPages = [
    '/index.php' => [
        '/',
        'Transfer Service — Encrypted file sharing',
        'Share files and folders with browser-based end-to-end encryption. Send a share link and download files individually or as a ZIP.',
    ],
    '/about.php' => [
        '/about.php',
        'Privacy & security — Transfer Service',
        'Learn how Transfer Service protects temporary file transfers, how encryption works, and the limits of guest sharing.',
    ],
    '/terms.php' => [
        '/terms.php',
        'Terms of Service — Transfer Service',
        'Read the rules for using Transfer Service, including temporary storage, link security, acceptable use, and abuse reporting.',
    ],
];

$script = $_SERVER['SCRIPT_NAME'] ?? '';
$publicPage = $publicPages[$script] ?? null;
$metaTitle = $publicPage[1] ?? 'Transfer Service — Encrypted file sharing';
$metaDescription = $publicPage[2] ??
    'Temporary file sharing with browser-based end-to-end encryption. Keep your full share link and decryption key private.';
$metaUrl = 'https://example.com' . ($publicPage[0] ?? '/');
$metaImage = 'https://example.com/assets/branding/site-mark.png';

$metaTags = [
    'og:type' => 'website',
    'og:site_name' => 'Transfer Service',
    'og:title' => $metaTitle,
    'og:description' => $metaDescription,
    'og:url' => $metaUrl,
    'og:image' => $metaImage,
    'og:image:type' => 'image/png',
    'og:image:width' => '512',
    'og:image:height' => '512',
    'og:image:alt' => 'Transfer Service white T on a slate background',
];
?>
<meta name="description" content="<?= escape($metaDescription) ?>">
<?php if ($publicPage !== null): ?>
<link rel="canonical" href="<?= escape($metaUrl) ?>">
<?php else: ?>
<meta name="robots" content="noindex, nofollow, noarchive">
<?php endif; ?>

<?php foreach ($metaTags as $property => $content): ?>
<meta property="<?= escape($property) ?>" content="<?= escape($content) ?>">
<?php endforeach; ?>

<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="<?= escape($metaTitle) ?>">
<meta name="twitter:description" content="<?= escape($metaDescription) ?>">
<meta name="twitter:image" content="<?= escape($metaImage) ?>">
<meta name="twitter:image:alt" content="Transfer Service white T on a slate background">
<meta name="theme-color" content="#34495e">

<link rel="icon" type="image/png" sizes="512x512"
      href="/assets/branding/site-mark.png">
<link rel="icon" type="image/svg+xml" sizes="any" href="/favicon.svg">
<link rel="apple-touch-icon" href="/assets/branding/site-mark.png">
