document.querySelector("#print")?.addEventListener("click", () => window.print());

const upload = document.querySelector("#image-upload");
upload?.addEventListener("submit", event => {
    event.preventDefault();
    const file = upload.querySelector("#image-file").files[0];
    const status = upload.querySelector("#upload-error");
    if (!file || file.size > 8 * 1024 * 1024) {
        status.textContent = "Choose an image up to 8 MiB.";
        return;
    }
    // Encode the upload for the same URL-encoded form parser used by text fields.
    const reader = new FileReader();
    reader.onerror = () => { status.textContent = "Could not read the selected file."; };
    reader.onload = () => {
        upload.elements.filename.value = file.name;
        upload.elements.image.value = reader.result.split(",")[1].replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
        HTMLFormElement.prototype.submit.call(upload);
    };
    reader.readAsDataURL(file);
});
