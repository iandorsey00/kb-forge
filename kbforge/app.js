document.querySelector("#print")?.addEventListener("click", () => window.print());

const upload = document.querySelector("#image-upload");
upload?.addEventListener("submit", event => {
    event.preventDefault();
    const file = upload.querySelector("#image-file").files[0];
    const status = upload.querySelector("#upload-error");
    const button = upload.querySelector("button[type=submit]");
    const body = document.querySelector("textarea[name=body]");
    if (!file || file.size > 8 * 1024 * 1024) {
        status.textContent = "Choose an image up to 8 MiB.";
        return;
    }

    // Capture the original caret. If typing continues during upload, use the live caret.
    const original = body.value;
    const caret = body.selectionEnd;
    button.disabled = true;
    status.textContent = "Attaching image…";
    const reader = new FileReader();
    reader.onerror = () => {
        status.textContent = "Could not read the selected file.";
        button.disabled = false;
    };
    reader.onload = async () => {
        const form = new URLSearchParams(new FormData(upload));
        form.set("filename", file.name);
        form.set("insert", "draft");
        form.set("image", reader.result.split(",")[1].replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, ""));
        try {
            const response = await fetch(upload.action, {method: "POST", body: form});
            if (!response.ok) {
                throw new Error("Could not attach the image. Check its file type and try again.");
            }
            const {markdown} = await response.json();
            const position = body.value === original ? caret : body.selectionEnd;
            body.setRangeText("\n\n" + markdown + "\n\n", position, position, "end");
            body.focus();
            status.textContent = "Image inserted. Save changes to keep the reference.";
            upload.reset();
        } catch (error) {
            status.textContent = error.message;
        } finally {
            button.disabled = false;
        }
    };
    reader.readAsDataURL(file);
});
