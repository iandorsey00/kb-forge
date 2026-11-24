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

const editor = document.querySelector("#article-editor");
const body = editor?.elements.body;
const save = document.querySelector("#editor-save");
if (editor) {
    const tools = document.querySelector("#markdown-tools");
    const modes = document.querySelector("#editor-modes");
    const panes = document.querySelector(".editor-panes");
    const source = document.querySelector(".editor-source");
    const preview = document.querySelector(".editor-preview");
    const previewStatus = document.querySelector("#editor-preview-status");
    const previewContent = document.querySelector("#editor-preview-content");
    const saveState = document.querySelector("#editor-save-state");
    const lineCount = document.querySelector("#editor-line-count");
    let dirty = false;
    let timer;
    let pending;

    function showLineCount() {
        const lines = body.value.split("\n").length;
        lineCount.textContent = lines === 1 ? "1 line" : lines + " lines";
    }

    function queuePreview(delay) {
        clearTimeout(timer);
        pending?.abort();
        if (!preview.hidden) timer = setTimeout(renderPreview, delay);
    }

    async function renderPreview() {
        const markdown = body.value;
        if (!markdown.trim()) {
            previewContent.replaceChildren();
            previewStatus.textContent = "Start writing to see a preview.";
            return;
        }
        pending = new AbortController();
        const {signal} = pending;
        previewStatus.textContent = "Rendering preview…";
        try {
            const response = await fetch(editor.dataset.preview, {
                method: "POST",
                body: new URLSearchParams({_token: editor.elements._token.value, body: markdown}),
                signal,
            });
            if (!response.ok) throw new Error("Preview failed.");
            const html = await response.text();
            if (signal.aborted) return;
            const fragment = document.createElement("template");
            fragment.innerHTML = html;
            // Keep heading anchors local to the preview and article links away from the draft.
            for (const element of fragment.content.querySelectorAll("[id]")) {
                element.id = "preview-" + element.id;
            }
            for (const link of fragment.content.querySelectorAll("a[href]")) {
                const href = link.getAttribute("href");
                if (href.startsWith("#")) {
                    link.setAttribute("href", "#preview-" + href.slice(1));
                } else {
                    link.target = "_blank";
                    link.rel = "noopener noreferrer";
                }
            }
            previewContent.replaceChildren(fragment.content);
            previewStatus.textContent = "";
        } catch {
            if (!signal.aborted) {
                previewContent.replaceChildren();
                previewStatus.textContent = "Could not render the preview. You can continue editing.";
            }
        }
    }

    function updateMode(mode) {
        panes.dataset.mode = mode;
        source.hidden = tools.hidden = mode === "preview";
        preview.hidden = mode === "write";
        for (const button of modes.querySelectorAll("button")) {
            button.setAttribute("aria-pressed", String(button.dataset.mode === mode));
        }
        queuePreview(0);
    }

    modes.addEventListener("click", event => {
        const button = event.target.closest("button[data-mode]");
        if (button) updateMode(button.dataset.mode);
    });

    tools.addEventListener("click", event => {
        const button = event.target.closest("button[data-format]");
        if (!button) return;
        const format = button.dataset.format;
        let {selectionStart: start, selectionEnd: end} = body;
        if (format === "heading" || format === "list") {
            start = start === 0 ? 0 : body.value.lastIndexOf("\n", start - 1) + 1;
            const lineEnd = body.value.indexOf("\n", end > start && body.value[end - 1] === "\n" ? end - 1 : end);
            end = lineEnd < 0 ? body.value.length : lineEnd;
        }
        const selected = body.value.slice(start, end);
        const replacement = {
            heading: () => "## " + (selected || "Heading"),
            list: () => (selected || "List item").split("\n").map(line => "- " + line).join("\n"),
            bold: () => "**" + (selected || "bold text") + "**",
            italic: () => "_" + (selected || "italic text") + "_",
            link: () => "[" + (selected || "link text") + "](https://example.com)",
        }[format]();
        body.focus();
        body.setRangeText(replacement, start, end, "end");
        if (format === "link") {
            body.setSelectionRange(start + replacement.lastIndexOf("(") + 1, start + replacement.length - 1);
        } else if (!selected) {
            const offset = {heading: 3, list: 2, bold: 2, italic: 1}[format];
            const suffix = format === "bold" || format === "italic" ? offset : 0;
            body.setSelectionRange(start + offset, start + replacement.length - suffix);
        }
        body.dispatchEvent(new Event("input", {bubbles: true}));
    });

    document.addEventListener("input", event => {
        if (event.target.form !== editor) return;
        if (!dirty) {
            dirty = true;
            saveState.textContent = "Unsaved changes";
        }
        if (event.target === body) {
            showLineCount();
            queuePreview(450);
        }
    });

    document.addEventListener("invalid", event => {
        if (event.target.form !== editor && event.target.form?.id !== "image-upload") return;
        const section = event.target.closest("details");
        if (section) section.open = true;
    }, true);

    document.addEventListener("keydown", event => {
        if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
            event.preventDefault();
            save.click();
        }
    });

    editor.addEventListener("submit", event => {
        if (save.disabled) event.preventDefault();
        else dirty = false;
    });

    window.addEventListener("beforeunload", event => {
        if (dirty) {
            event.preventDefault();
            event.returnValue = "";
        }
    });

    tools.hidden = modes.hidden = lineCount.hidden = false;
    showLineCount();
}

const upload = document.querySelector("#image-upload");
if (upload) {
    const input = upload.querySelector("#image-file");
    const queue = upload.querySelector("#image-queue");
    const status = upload.querySelector("#upload-error");
    const button = upload.querySelector("button[type=submit]");
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
                if (body.closest(".editor-source").hidden) {
                    document.querySelector('#editor-modes [data-mode="write"]').click();
                }
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
                body.dispatchEvent(new Event("input", {bubbles: true}));
            }
            const inserted = references.length ? references.length + " image(s) inserted. Save the article. " : "";
            status.textContent = inserted + (failed.length ? "Could not attach " + failed.join(", ") + ". Those files can be retried." : "");
        } finally {
            button.disabled = input.disabled = save.disabled = false;
            for (const control of queue.querySelectorAll("input,button")) control.disabled = false;
        }
    });
}
