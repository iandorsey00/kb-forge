(() => {
    const search = document.querySelector("#reader-search");
    const input = search.querySelector("input");
    const status = search.querySelector("[role=status]");
    const updates = document.querySelector(".reader-updates");
    const index = [...document.querySelectorAll("[data-search]")].map(
        item => [item, item.dataset.search.normalize("NFKC").toLowerCase()]
    );
    search.hidden = false;
    search.addEventListener("submit", event => event.preventDefault());
    function filter() {
        const query = input.value.normalize("NFKC").toLowerCase().trim();
        const terms = query ? query.split(/\s+/) : [];
        if (updates) updates.hidden = Boolean(query);
        let matches = 0;
        for (const [item, text] of index) {
            const visible = terms.every(term => text.includes(term));
            item.hidden = !visible;
            if (visible) matches += 1;
        }
        status.textContent = query
            ? (matches ? status.dataset.count.replace("{count}", String(matches)) : status.dataset.empty)
            : "";
    }
    input.addEventListener("input", filter);
    input.addEventListener("search", filter);
    filter();
})();
