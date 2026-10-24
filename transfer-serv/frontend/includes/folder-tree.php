<?php

function transfer_build_tree(array $files): array
{
    $tree = ['folders' => [], 'files' => []];

    foreach ($files as $file) {
        $parts = explode(
            '/',
            $file['relative_path'] ?? $file['name'],
        );

        array_pop($parts);
        $node = &$tree;

        foreach ($parts as $part) {
            if (!isset($node['folders'][$part])) {
                $node['folders'][$part] = [
                    'folders' => [],
                    'files' => [],
                ];
            }

            $node = &$node['folders'][$part];
        }

        $node['files'][] = $file;
        unset($node);
    }

    return $tree;
}


function transfer_download_url(
    string $transferId,
    array $parameters,
): string {
    return '/download.php?' . http_build_query(
        ['transfer' => $transferId] + $parameters,
        '',
        '&',
        PHP_QUERY_RFC3986,
    );
}


function transfer_render_tree(
    array $node,
    string $transferId,
    string $prefix = '',
): void {
    ksort(
        $node['folders'],
        SORT_NATURAL | SORT_FLAG_CASE,
    );

    foreach ($node['folders'] as $name => $child):
        $path = $prefix === ''
            ? (string) $name
            : $prefix . '/' . $name;
        ?>

        <details class="card mb-3">
            <summary class="card-body py-3">
                <strong>
                    <?= escape((string) $name) ?>
                </strong>

                <span class="small text-secondary ms-2">
                    Folder
                </span>
            </summary>

            <div class="card-body pt-0">
                <?php
                transfer_render_tree(
                    $child,
                    $transferId,
                    $path,
                );
                ?>
            </div>
        </details>

        <?php
    endforeach;

    if (!$node['files']) return;
    ?>

    <ul class="list-group mb-3">
        <?php foreach ($node['files'] as $file): ?>
            <li class="list-group-item d-flex flex-wrap gap-3 align-items-center">
                <div class="flex-grow-1 text-break">
                    <strong>
                        <?= escape($file['name']) ?>
                    </strong>

                    <div class="small text-secondary">
                        <?= escape(transfer_format_bytes(
                            $file['size_bytes'],
                        )) ?>
                    </div>
                </div>

                <a
                    class="btn btn-primary btn-sm"
                    href="<?= escape(transfer_download_url(
                        $transferId,
                        ['file' => $file['id']],
                    )) ?>"
                >
                    Download
                </a>
            </li>
        <?php endforeach; ?>
    </ul>

    <?php
}