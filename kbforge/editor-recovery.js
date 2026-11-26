function setupDraftRecovery(form) {
    const prefix = "kbforge:draft:v1:" + form.dataset.draftKey + ":";
    const base = form.elements.fingerprint.value;
    const panel = document.querySelector("#editor-recovery");
    const choices = document.querySelector("#recovery-drafts");
    const note = document.querySelector("#recovery-note");
    const restore = document.querySelector("#recovery-restore");
    const discard = document.querySelector("#recovery-discard");
    const review = document.querySelector("#recovery-review");
    const reviewBody = document.querySelector("#recovery-body");
    const reviewFields = document.querySelector("#recovery-fields");
    const storageStatus = document.querySelector("#recovery-storage-status");
    const snapshot = () => Object.fromEntries(
        [...new FormData(form)].filter(([name]) => name !== "_token" && name !== "fingerprint")
    );
    const initial = snapshot();
    let key = prefix + crypto.randomUUID();
    let previous = new Map();
    let copies = new Map();
    let timer;
    let pending = false;

    function storageMessage(message) {
        storageStatus.textContent = message;
        storageStatus.hidden = !message;
    }

    function checkpoint() {
        clearTimeout(timer);
        if (!pending) return true;
        const fields = Object.fromEntries(
            Object.entries(snapshot()).filter(([name, value]) => value !== initial[name])
        );
        try {
            if (Object.keys(fields).length) {
                localStorage.setItem(key, JSON.stringify({base, fields, updated: Date.now()}));
                storageMessage("Recovery copy stored in this browser.");
            } else {
                localStorage.removeItem(key);
                storageMessage("");
            }
            pending = false;
            return true;
        } catch {
            storageMessage("Could not store a recovery copy. Save or copy your edits before leaving.");
            return false;
        }
    }

    function showChoice() {
        const draft = copies.get(choices.value);
        if (!draft) return;
        const fields = Object.entries(draft.fields);
        const compatible = fields.every(([name, value]) => {
            if (!Object.hasOwn(initial, name)) return false;
            const field = form.elements.namedItem(name);
            return !field.options || [...field.options].some(option => option.value === value);
        });
        restore.hidden = draft.base !== base || !compatible;
        note.textContent = restore.hidden
            ? "The saved article or its fields changed. Review the recovered text and copy the edits you want to keep."
            : "Restoring fills the editor. Select Save changes when you are ready.";
        reviewBody.value = draft.fields.body ?? "";
        reviewBody.parentElement.hidden = !Object.hasOwn(draft.fields, "body");
        reviewFields.replaceChildren();
        for (const [name, value] of fields) {
            if (name === "body") continue;
            const label = document.createElement("dt");
            const field = Object.hasOwn(initial, name) ? form.elements.namedItem(name) : null;
            label.textContent = field?.labels?.[0]?.childNodes[0]?.textContent?.trim() || name;
            const text = document.createElement("dd");
            text.textContent = value || "(empty)";
            reviewFields.append(label, text);
        }
        review.open = restore.hidden;
        review.hidden = false;
    }

    function listCopies() {
        const selected = choices.value;
        copies = new Map();
        try {
            for (let index = 0; index < localStorage.length; index++) {
                const storedKey = localStorage.key(index);
                if (!storedKey?.startsWith(prefix) || storedKey === key) continue;
                const raw = localStorage.getItem(storedKey);
                try {
                    const draft = JSON.parse(raw);
                    if (typeof draft?.base === "string" && Number.isFinite(draft.updated)
                        && draft.fields && Object.values(draft.fields).every(value => typeof value === "string")) {
                        copies.set(storedKey, {...draft, raw});
                    }
                } catch {
                    // An unreadable browser entry must not block the editor.
                }
            }
        } catch {
            storageMessage("Draft recovery is unavailable in this browser.");
        }
        const ordered = [...copies].sort(([, left], [, right]) => right.updated - left.updated);
        choices.replaceChildren(...ordered.map(([id, draft], index) =>
            new Option(`Draft ${index + 1} · ${new Date(draft.updated).toLocaleString()}`, id)
        ));
        if (copies.has(selected)) choices.value = selected;
        panel.hidden = !copies.size;
        showChoice();
    }

    choices.addEventListener("change", showChoice);
    restore.addEventListener("click", () => {
        const selected = choices.value;
        const draft = copies.get(selected);
        if (restore.hidden || !draft || !checkpoint()) return;
        previous.set(selected, draft.raw);
        key = prefix + crypto.randomUUID();
        for (const [name, original] of Object.entries(initial)) {
            form.elements.namedItem(name).value = draft.fields[name] ?? original;
        }
        form.elements.body.dispatchEvent(new Event("input", {bubbles: true}));
        if (checkpoint()) {
            try {
                if (localStorage.getItem(selected) === draft.raw) localStorage.removeItem(selected);
            } catch {
                storageMessage("The original recovery copy is still in this browser.");
            }
        }
        listCopies();
    });
    discard.addEventListener("click", () => {
        const selected = choices.value;
        try {
            const draft = copies.get(selected);
            if (draft && localStorage.getItem(selected) === draft.raw) localStorage.removeItem(selected);
            listCopies();
        } catch {
            storageMessage("Could not remove this recovery copy.");
        }
    });
    window.addEventListener("pagehide", checkpoint);
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) checkpoint();
    });
    listCopies();
    return {
        changed() {
            pending = true;
            clearTimeout(timer);
            timer = setTimeout(checkpoint, 400);
        },
        checkpoint,
        saved() {
            clearTimeout(timer);
            pending = false;
            try {
                localStorage.removeItem(key);
                for (const [id, raw] of previous) {
                    if (localStorage.getItem(id) === raw) localStorage.removeItem(id);
                }
            } catch {
                // A successful article save remains valid if browser storage is unavailable.
            }
        },
    };
}
