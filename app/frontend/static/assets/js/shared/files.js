
const LOADING_TABLE = `<tr class="skeleton-row">
                                    <td>
                                        <div class="skeleton-line" style="width: 60%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 30%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 20%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 30%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 20%;"></div>
                                    </td>
                                </tr>
                                <tr class="skeleton-row">
                                    <td>
                                        <div class="skeleton-line" style="width: 60%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 30%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 20%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 30%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 20%;"></div>
                                    </td>
                                </tr>
                                <tr class="skeleton-row">
                                    <td>
                                        <div class="skeleton-line" style="width: 60%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 30%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 20%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 30%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 20%;"></div>
                                    </td>
                                </tr>
                                <tr class="skeleton-row">
                                    <td>
                                        <div class="skeleton-line" style="width: 60%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 30%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 20%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 30%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 20%;"></div>
                                    </td>
                                </tr>
                                <tr class="skeleton-row">
                                    <td>
                                        <div class="skeleton-line" style="width: 60%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 30%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 20%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 30%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 20%;"></div>
                                    </td>
                                </tr>
                                <tr class="skeleton-row">
                                    <td>
                                        <div class="skeleton-line" style="width: 60%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 30%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 20%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 30%;"></div>
                                    </td>
                                    <td>
                                        <div class="skeleton-line" style="width: 20%;"></div>
                                    </td>
                                </tr>`

async function getTreeView(path) {
    const token = getCookie("_xsrf");
    $("#files-table-body").html(LOADING_TABLE);
    let res = await fetch(`/api/v2/servers/${serverId}/files`, {
        method: "POST",
        headers: {
            "X-XSRFToken": token,
        },
        body: JSON.stringify({ page: "files", path: path }),
    });
    let responseData = await res.json();
    if (responseData.status === "ok") {
        console.log(responseData);
        process_tree_response(responseData);
    } else {
        bootbox.alert({
            title: responseData.error,
            message: responseData.error_data
        });
    }
}

function fileIcon(value) {
    if (value.dir) return '<i class="fa-regular fa-folder text-info"></i>';
    if (value.can_open) return '<i class="fa-regular fa-file text-success"></i>';
    return '<i class="fa-regular fa-file-excel text-danger"></i>';
}

function process_tree_response(response) {
    const tbody = document.querySelector("tbody");
    console.log(response)
    let path = response.data.root_path.path;
    let file_nav = ``;
    console.log(path)
    path = path.split("\\").join("/"); //Remove \ marks
    console.log(path)
    path_list = path.split("/");

    const container = document.querySelector("#table-nav"); // your container
    $(container).html("") // clear previous content

    path_list.forEach((part, index) => {
        // Create the span
        const span = document.createElement("span");
        span.className = "tree-nav";
        const previous = path_list.slice(0, index);
        local_path = previous.join("/") + "/" + part
        span.dataset.path = local_path; // or set the actual path if needed
        span.textContent = part; // safe text

        // Append the span
        container.appendChild(span);

        // Append the separator except after the last element
        if (index < path_list.length - 1) {
            container.appendChild(document.createTextNode(" > "));
        }
    });
    $("#files-table-body").html("");
    Object.entries(response.data).forEach(([key, value]) => {
        if (key === "root_path" || key === "db_stats") return;

        const tr = document.createElement("tr");
        tr.className = value.dir ? "directory" : "file";
        tr.dataset.path = value.path;
        tr.dataset.can_open = value.can_open;

        // Column 1: icon + filename
        const td1 = document.createElement("td");
        const iconSpan = document.createElement("span");
        iconSpan.innerHTML = fileIcon(value);
        td1.appendChild(iconSpan);
        td1.appendChild(document.createTextNode("\u00A0\u00A0\u00A0"));
        td1.appendChild(document.createTextNode(key));

        // Column 2: MIME or "Dir"
        const td2 = document.createElement("td");
        if (value.mime || value.dir) {
            td2.textContent = value.mime ? value.mime : "Dir"; // safe text
        } else {
            td2.innerHTML = `<i class="fa fa-question-circle" aria-hidden="true"></i>`;
        }

        // Column 3: modified date
        const td3 = document.createElement("td");
        td3.textContent = value.modified;

        // Column 4: size
        const td4 = document.createElement("td");
        td4.textContent = value.size || "-";

        // Column 5: context button
        const td5 = document.createElement("td");
        td5.className = "context-button";
        td5.textContent = "...";

        [td1, td2, td3, td4, td5].forEach(td => tr.appendChild(td));

        tbody.appendChild(tr);
    });
    $(".directory").click(function (e) {
        console.log("dir clicked")
        // Prevent the click from firing if it’s on the context menu button
        if ($(e.target).closest(".context-button").length) return;
        console.log("directory")
        getTreeView($(this).data("path"))
    });
    $(".file").click(function (e) {
        // Prevent the click from firing if it’s on the context menu button
        if ($(e.target).closest(".context-button").length) return;
        if (!$(this).data("can_open")) return;
        window.open(`/panel/edit_file?server_id=${serverId}&file=${encodeURI($(this).data("path"))}`, "_blank")
    });
    $(".tree-nav").click(function (e) {
        // Prevent the click from firing if it’s on the context menu button
        if ($(e.target).closest(".context-button").length) return;
        console.log("nav")
        getTreeView($(this).data("path"))
    });
}