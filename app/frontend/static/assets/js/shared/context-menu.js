document.addEventListener("DOMContentLoaded", () => {
    const icon = document.querySelector(".context-icon");
    const menu = document.querySelector(".context-menu");
    const contextArea = document.querySelector("#context-container")
    // Show context menu at click position
    function showMenu(x, y) {
        console.log("Showing menu")
        // Make visible to get dimensions
        menu.style.display = "flex";
        menu.style.position = "fixed";
        menu.style.opacity = "0";
        menu.classList.add("show");

        // Wait one frame so DOM updates before measuring
        requestAnimationFrame(() => {
            const rect = menu.getBoundingClientRect();
            let newX = x + 5;
            let newY = y + 5;

            // Keep inside viewport
            if (newX + rect.width > window.innerWidth) {
                newX = window.innerWidth - rect.width - 10;
            }
            if (newY + rect.height > window.innerHeight) {
                newY = window.innerHeight - rect.height - 10;
            }

            menu.style.left = `${newX}px`;
            menu.style.top = `${newY}px`;
            menu.style.opacity = "1";
        });
    }

    try {
        // Left-click on gear icon
        icon.addEventListener("click", (event) => {
            event.stopPropagation();
            loadMenuContent();
            const isVisible = menu.classList.contains("show");
            document.querySelectorAll(".context-menu.show").forEach((m) => m.classList.remove("show"));

            if (!isVisible) showMenu(event.clientX, event.clientY);
        });
    } catch {
        console.log("Could Not find icon to set context")
    }
    // Right-click anywhere
    try {
        contextArea.addEventListener("contextmenu", (event) => {
            const th = event.target.closest("th");
            const tr = event.target.closest("tr");

            if (!th && tr) { //only allow right click menu on folder items
                event.preventDefault();
                loadMenuContent(tr);
                showMenu(event.clientX, event.clientY);
            }
        });
    } catch {
        console.log("Could not find context area to set")
    }

    // Click outside closes menu
    document.addEventListener("click", (event) => {
        if (!event.target.classList.contains("edit-configure")) {
            menu.classList.remove("show");
            menu.style.display = "none";
        }
    });
});
