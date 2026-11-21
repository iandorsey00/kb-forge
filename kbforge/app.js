document.querySelector("#print")?.addEventListener("click", () => window.print());

const updatesLink = document.querySelector("#updates-link");
if (updatesLink) {
    async function refreshUpdateLabel() {
        if (document.hidden) return;
        try {
            const response = await fetch("/update-status");
            if (!response.ok) return;
            const label = await response.text();
            if (updatesLink.textContent !== label) {
                updatesLink.textContent = label;
                updatesLink.classList.toggle("update-available", label === "Update app…");
            }
        } catch {
            // Navigation stays available if a status request fails.
        }
    }
    refreshUpdateLabel();
    window.setInterval(refreshUpdateLabel, 30_000);
    document.addEventListener("visibilitychange", refreshUpdateLabel);
}

const upload = document.querySelector("#image-upload");
if (upload) {
    const input = upload.querySelector("#image-file");
    const queue = upload.querySelector("#image-queue");
    const status = upload.querySelector("#upload-error");
    const button = upload.querySelector("button[type=submit]");
    const body = document.querySelector("textarea[name=body]");
    const save = body.form.querySelector("button");
    const entries = new Map();

    function queueImages(files) {
        if (button.disabled) return;
        const rejected = [];
        for (const file of files) {
            if (!/\.(png|jpe?g|gif|webp)$/i.test(file.name) || file.size > 8 * 1024 * 1024 || !file.size) {
                rejected.push(file.name);
                continue;
            }
            const row = document.createElement("div");
            row.className = "image-entry";
            const label = document.createElement("label");
            label.textContent = "Alternative text for " + file.name;
            const alt = document.createElement("input");
            alt.required = true;
            alt.value = file.name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ");
            label.append(alt);
            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "button secondary";
            remove.textContent = "Remove";
            remove.setAttribute("aria-label", "Remove " + file.name);
            remove.addEventListener("click", () => {
                entries.delete(row);
                row.remove();
            });
            row.append(label, remove);
            queue.append(row);
            entries.set(row, {file, alt});
        }
        status.textContent = rejected.length
            ? "Use PNG, JPEG, GIF, or WebP up to 8 MiB. Skipped " + rejected.join(", ") + "."
            : entries.size + " image(s) ready. Review the alternative text, then attach.";
    }

    input.addEventListener("change", () => {
        queueImages(input.files);
        input.value = "";
    });

    for (const target of [upload, body]) {
        target.addEventListener("dragover", event => {
            if (event.dataTransfer.types.includes("Files")) event.preventDefault();
        });
        target.addEventListener("drop", event => {
            if (!event.dataTransfer.files.length) return;
            event.preventDefault();
            queueImages(event.dataTransfer.files);
        });
    }

    body.addEventListener("paste", event => {
        const files = [...event.clipboardData.files].filter(file => file.type.startsWith("image/"));
        if (!files.length || event.clipboardData.getData("text/plain")) return;
        event.preventDefault();
        queueImages(files);
    });

    function readImage(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onerror = () => reject(new Error("Could not read the file."));
            reader.onload = () => resolve(
                reader.result.split(",")[1].replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "")
            );
            reader.readAsDataURL(file);
        });
    }

    body.form.addEventListener("submit", event => {
        if (button.disabled) event.preventDefault();
    });

    upload.addEventListener("submit", async event => {
        event.preventDefault();
        if (button.disabled) return;
        if (!entries.size) {
            status.textContent = "Choose at least one image.";
            return;
        }
        const width = upload.elements.width.value;
        const indentOverride = upload.elements.indent.value;
        const references = [];
        const failed = [];
        button.disabled = input.disabled = save.disabled = true;
        for (const control of queue.querySelectorAll("input,button")) control.disabled = true;
        try {
            for (const [row, {file, alt}] of entries) {
                status.textContent = "Attaching " + file.name + "…";
                try {
                    const form = new URLSearchParams({
                        _token: upload.elements._token.value,
                        filename: file.name,
                        alt: alt.value,
                        width,
                        insert: "draft",
                        image: await readImage(file),
                    });
                    const response = await fetch(upload.action, {method: "POST", body: form});
                    if (!response.ok) throw new Error("Upload failed.");
                    const {markdown} = await response.json();
                    references.push(markdown);
                    entries.delete(row);
                    row.remove();
                } catch {
                    failed.push(file.name);
                }
            }
            if (references.length) {
                const position = body.selectionEnd;
                const lineEnd = body.value.indexOf("\n", position);
                const insertAt = lineEnd < 0 ? body.value.length : lineEnd;
                const lineStart = position === 0 ? 0 : body.value.lastIndexOf("\n", position - 1) + 1;
                const line = body.value.slice(lineStart, insertAt);
                const marker = line.match(/^ *(?:[-+*]|\d{1,9}[.)]) +/);
                const indent = " ".repeat(indentOverride === "" ? (marker?.[0].length ?? 0) : Number(indentOverride));
                const images = references.map(reference => indent + reference).join("\n\n");
                const prefix = insertAt ? "\n\n" : "";
                body.setRangeText(prefix + images + "\n", insertAt, insertAt, "end");
                body.focus();
            }
            const inserted = references.length ? references.length + " image(s) inserted. Save the article. " : "";
            status.textContent = inserted + (failed.length ? "Could not attach " + failed.join(", ") + ". Those files can be retried." : "");
        } finally {
            button.disabled = input.disabled = save.disabled = false;
            for (const control of queue.querySelectorAll("input,button")) control.disabled = false;
        }
    });
}
