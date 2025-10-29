
let selected_row = null;

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
    let path = response.data.root_path.path;
    console.log(response.data.root_path)
    path = path.split("\\").join("/"); //Remove \ marks
    path_list = path.split("/");

    const container = document.querySelector("#table-nav"); // your container
    $(container).html("") // clear previous content
    $(container).attr("data-cur-path", path)
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

        const $tr = $("<tr>")
            .addClass(value.dir ? "directory" : "file")
            .attr("data-path", value.path)
            .attr("data-can_open", value.can_open);

        // Column 1: icon + filename
        const $td1 = $("<td>")
            .addClass("column-1")
            .attr("data-name", key)
            .append($("<span>").html(fileIcon(value)))
            .append("\u00A0\u00A0\u00A0")
            .append(document.createTextNode(key));

        // Column 2: MIME or "Dir"
        const $td2 = $("<td>");
        if (value.mime || value.dir) {
            $td2.text(value.mime ? value.mime : "Dir");
        } else {
            $td2.html('<i class="fa fa-question-circle" aria-hidden="true"></i>');
        }

        // Column 3: modified date
        const $td3 = $("<td>").text(value.modified);

        // Column 4: size
        const $td4 = $("<td>").text(value.size || "-");

        // Column 5: context button
        const $td5 = $("<td>")
            .addClass("context-button")
            .text("...");

        // Append all columns to the row
        $tr.append($td1, $td2, $td3, $td4, $td5);

        // Append row to tbody (also as jQuery object)
        $(tbody).append($tr);
    });
    $(".directory").click(function (e) {
        console.log("dir clicked")
        // Prevent the click from firing if it’s on the context menu button
        if ($(e.target).closest(".context-button").length) return;
        if ($(this).children(".column-1").hasClass("editing")) return;
        console.log("directory")
        getTreeView($(this).attr("data-path"))
    });
    $(".file").click(function (e) {
        // Prevent the click from firing if it’s on the context menu button
        if ($(e.target).closest(".context-button").length) return;
        if (!$(this).data("can_open")) return;
        if ($(this).children(".column-1").hasClass("editing")) return;
        window.open(`/panel/edit_file?server_id=${serverId}&file=${encodeURI($(this).attr("data-path"))}`, "_blank")
    });
    $(".tree-nav").click(function (e) {
        // Prevent the click from firing if it’s on the context menu button
        if ($(e.target).closest(".context-button").length) return;
        getTreeView($(this).attr("data-path"))
    });
}

function loadMenuContent(tr) {
    const ctxMenuItems = ["rename", "unzip", "download", "delete"];
    console.log("Loading menu 1")
    const menu = $("#context-menu");
    menu.empty(); // clear previous content
    const path = $(tr).attr("data-path")
    selected_row = tr
    let zipFile = false;
    if (path) {
        zipFile = String(path).endsWith(".zip");
    }
    for (const arr_item of ctxMenuItems) {
        if (arr_item === "unzip" && !zipFile) {
            continue;
        }
        const itemContainer = $("<div>").addClass("menu-item").attr("id", arr_item);
        const item = $("<h6>").html(`<span class="${arr_item}-btn">${$("#files_table").data(arr_item)}</span>`);
        itemContainer.append(item);
        menu.append(itemContainer);
    }
    $("<input>").val()
    add_rename_listener();
    add_delete_listener();
    add_download_listener();

}
async function renameItem(path, name) {
    const token = getCookie("_xsrf");
    let res = await fetch(`/api/v2/servers/${serverId}/files/create/`, {
        method: "PATCH",
        headers: {
            "X-XSRFToken": token,
        },
        body: JSON.stringify({ path: path, new_name: name }),
    });
    let responseData = await res.json();
    if (responseData.status === "ok") {
        console.log("sent ok")
        $(selected_row).children(".column-1").empty()
        let icon = '<i class="fa-regular fa-file-excel text-danger"></i>'
        if ($(selected_row).hasClass("directory")) icon = '<i class="fa-regular fa-folder text-info"></i>';
        if ($(selected_row).hasClass("file")) icon = '<i class="fa-regular fa-file text-success"></i>';
        $(selected_row).children(".column-1").append($("<span>").html(icon))
            .append("\u00A0\u00A0\u00A0")
            .append(document.createTextNode(name));
        $(selected_row).children(".column-1").attr("data-name", name)
    } else {
        bootbox.alert({
            title: responseData.error,
            message: responseData.error_data
        });
    }
}

function add_rename_listener() {
    $("#rename").on("click", function () {
        const path = $(selected_row).attr("data-path");
        const name = $(selected_row).children(".column-1").attr("data-name");
        bootbox.prompt({
            title:
                "{% raw translate('serverFiles', 'renameItemQuestion', data['lang']) %}",
            value: name,
            callback: function (result) {
                if (!result) return;
                if ($(selected_row).children(".column-1").attr("data-name") != result) {
                    console.log("sending path" + result)
                    renameItem($(selected_row).attr("data-path"), result)
                    new_path = $(selected_row).attr("data-path").replace($(selected_row).children(".column-1").attr("data-name"), result)
                    $(selected_row).attr("data-path", result)
                }
            },
        });
    });
}


$("#create-dir").on("click", function () {
    bootbox.prompt(
        "{% raw translate('serverFiles', 'createDirQuestion', data['lang']) %}",
        function (result) {
            if (!result) return;
            const cur_dir = $("#table-nav").attr("data-cur-path");
            createDir(cur_dir, result, function () {
                getTreeView(cur_dir);
            });
        }
    );
})

async function createDir(parent, name, callback) {
    const token = getCookie("_xsrf");
    let res = await fetch(`/api/v2/servers/${serverId}/files/create/`, {
        method: "PUT",
        headers: {
            "X-XSRFToken": token,
        },
        body: JSON.stringify({ parent: parent, name: name, directory: true }),
    });
    let responseData = await res.json();
    if (responseData.status === "ok") {
        const cur_dir = $("#table-nav").attr("data-cur-path");
        getTreeView(cur_dir);
    } else {
        bootbox.alert({
            title: responseData.error,
            message: responseData.error_data
        });
    }
}

function add_delete_listener() {
    $("#delete").on("click", function () {
        const path = $(selected_row).attr("data-path");
        console.log(path)
        bootbox.confirm({
            size: "",
            title:
                "{% raw translate('serverFiles', 'deleteItemQuestion', data['lang']) %}",
            closeButton: false,
            message:
                "{% raw translate('serverFiles', 'deleteItemQuestionMessage', data['lang']) %}",
            buttons: {
                confirm: {
                    label: "{{ translate('serverFiles', 'yesDelete', data['lang']) }}",
                    className: "btn-danger",
                },
                cancel: {
                    label: "{{ translate('serverFiles', 'noDelete', data['lang']) }}",
                    className: "btn-link",
                },
            },
            callback: function (result) {
                if (!result) return;
                deleteItem(path);
            },
        });
    });
}


async function deleteItem(path) {
    const token = getCookie("_xsrf");
    let res = await fetch(`/api/v2/servers/${serverId}/files`, {
        method: "DELETE",
        headers: {
            "X-XSRFToken": token,
        },
        body: JSON.stringify({ filename: String(path) }),
    });
    let responseData = await res.json();
    if (responseData.status === "ok") {
        $(selected_row).remove()
    } else {
        bootbox.alert({
            title: responseData.error,
            message: responseData.error_data
        });
    }
}

function add_download_listener() {
    $("#download").on("click", function () {
        const path = $(selected_row).attr("data-path");
        window.open(`/api/v2/servers/${serverId}/files/${encodeURIComponent(path)}/download`, '_blank');
    });
}