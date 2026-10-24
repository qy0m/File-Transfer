<section
    id="storage-panel"
    class="card mb-4"
    aria-labelledby="storage-heading"
    hidden
>
    <div class="card-body">
        <h2 id="storage-heading" class="h5 mb-3">
            Upload storage
        </h2>

        <div class="row g-3 mb-4">
            <div class="col-sm-4">
                <p class="small text-secondary mb-1">
                    Storage remaining
                </p>
                <p id="storage-available" class="h4 mb-0">—</p>
            </div>

            <div class="col-sm-4">
                <p class="small text-secondary mb-1">
                    Storage used
                </p>
                <p id="storage-account" class="h4 mb-0">—</p>
            </div>

            <div class="col-sm-4">
                <p class="small text-secondary mb-1">
                    Your storage limit
                </p>
                <p id="storage-budget" class="h4 mb-0">—</p>
            </div>
        </div>

        <p
            id="storage-budget-label"
            class="small text-secondary mb-2"
        ></p>

        <progress
            id="storage-progress"
            class="upload-progress"
            max="100"
            value="0"
            aria-labelledby="storage-budget-label"
        ></progress>

        <p
            id="storage-note"
            class="small text-secondary mt-3 mb-0"
            role="status"
        >
            Checking storage…
        </p>

        <p class="small text-secondary mt-2 mb-0">
            Your upload storage allowance is 5 GB.
        </p>
    </div>
</section>