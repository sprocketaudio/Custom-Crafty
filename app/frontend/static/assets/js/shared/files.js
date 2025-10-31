
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
    let path = response.data.root_path.local_path;
    path = path.split("\\").join("/"); //Remove \ marks
    let path_list = path.split("/");
    const container = document.querySelector("#table-nav"); // your container
    $(container).html("") // clear previous content
    $(container).attr("data-cur-path", path);

    const span = document.createElement("span");
    span.className = "tree-nav";
    let local_path = serverId
    span.dataset.path = local_path; // or set the actual path if needed
    span.innerHTML = `<i class="fa-solid fa-server"></i>`; //Set root text as server icon
    container.appendChild(span);
    for (let [index, part] of path_list.entries()) {
        console.log("part", part, "index", index)
        if (!(part === serverId && index === 0)) {
            container.appendChild(document.createTextNode(" > "));
            // Create the span
            const span = document.createElement("span");
            span.className = "tree-nav";
            const previous = path_list.slice(0, index);
            if (index === 0) {
                local_path = previous.join("/") + part
            } else {
                local_path = previous.join("/") + "/" + part
            }
            console.log(local_path)
            span.dataset.path = local_path; // or set the actual path if needed // if we're on the first iteration and it's the server ID ignore it
            span.textContent = part; // safe text;


            // Append the span
            container.appendChild(span);
        }
    }
    $("#files-table-body").html("");
    const response_entries = Object.entries(response.data)
    console.log(response_entries)
    for (let [key, value] of response_entries) {
        console.log(key)
        if (key === "root_path" || key === "db_stats") continue;

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
    };

    $(".directory").click(function (e) {
        // Prevent the click from firing if it’s on the context menu button
        if ($(e.target).closest(".context-button").length) return;
        if ($(this).children(".column-1").hasClass("editing")) return;
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
    add_unzip_listener();

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
    } else {
        bootbox.alert({
            title: responseData.error,
            message: responseData.error_data
        });
    }
}

function add_rename_listener() {
    $("#rename").on("click", function () {
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
                    console.log($(selected_row).children(".column-1").attr("data-name"), result)
                    $(selected_row).attr("data-path", $(selected_row).attr("data-path").replace($(selected_row).children(".column-1").attr("data-name"), result))

                    $(selected_row).children(".column-1").empty()
                    let icon = '<i class="fa-regular fa-file-excel text-danger"></i>'
                    if ($(selected_row).hasClass("directory")) icon = '<i class="fa-regular fa-folder text-info"></i>';
                    if ($(selected_row).hasClass("file")) icon = '<i class="fa-regular fa-file text-success"></i>';
                    $(selected_row).children(".column-1").append($("<span>").html(icon))
                        .append("\u00A0\u00A0\u00A0")
                        .append(document.createTextNode(result));
                    $(selected_row).children(".column-1").attr("data-name", result)
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
            create(cur_dir, result, true);
        }
    );
})

$("#create-file").on("click", function () {
    bootbox.prompt(
        "{% raw translate('serverFiles', 'createDirQuestion', data['lang']) %}",
        function (result) {
            if (!result) return;
            const cur_dir = $("#table-nav").attr("data-cur-path");
            create(cur_dir, result, false);
        }
    );
})

async function create(parent, name, dir = false) {
    const token = getCookie("_xsrf");
    let res = await fetch(`/api/v2/servers/${serverId}/files/create/`, {
        method: "PUT",
        headers: {
            "X-XSRFToken": token,
        },
        body: JSON.stringify({ parent: parent, name: name, directory: dir }),
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

function add_unzip_listener() {
    $("#unzip").on("click", async function () {
        const path = $(selected_row).attr("data-path");
        const cur_dir = $("#table-nav").attr("data-cur-path");
        console.log(path)
        let res = await fetch(`/api/v2/servers/${serverId}/files/zip/`, {
            method: "POST",
            headers: {
                "X-XSRFToken": token,
            },
            body: JSON.stringify({ folder: path }),
        });
        let responseData = await res.json();
        if (responseData.status === "ok") {
            setTimeout(function () {
                getTreeView(cur_dir);
            }, 3000);
        } else {
            bootbox.alert({
                title: responseData.error,
                message: responseData.error_data
            });
        }
    });
}

$(document).ready(function () {

    $('#status').collapse({
        toggle: true
    })
    const $dropZone = $("#drop-zone");

    $dropZone.on("dragover", function (e) {
        e.preventDefault();
        e.stopPropagation();
        $dropZone.addClass("drop-hover");
    });

    $dropZone.on("dragleave", function (e) {
        e.preventDefault();
        e.stopPropagation();
        $dropZone.removeClass("drop-hover");
    });

    $dropZone.on("drop", function (e) {
        e.preventDefault();
        e.stopPropagation();
        $dropZone.removeClass("drop-hover");

        const files = e.originalEvent.dataTransfer.files;
        if (files.length === 0) return;

        handleUpload(files, $("#table-nav").attr("data-cur-path"));
    });
});

$("#upload-file").on("click", async function uploadFilesE(event) {
    const path = $("#table-nav").attr("data-cur-path");
    $(function () {
        let uploadHtml =
            "<div>" +
            '<form id="upload-file-form"  enctype="multipart/form-data">' +
            "<label class='upload-area' style='width:100%;text-align:center;' for='files'>" +
            "<i class='fa fa-cloud-upload fa-3x'></i>" +
            "<br />" +
            "{{translate('serverFiles', 'clickUpload', data['lang'])}}" +
            "<input style='margin-left: 21%;' id='files' name='files' type='file' multiple='true'>" +
            "</label></form>" +
            "<br />" +
            "<ul style='margin-left:5px !important;' id='fileList'></ul>" +
            "</div><div class='clearfix'></div>";
        bootbox.dialog({
            message: uploadHtml,
            title:
                "{{ translate('serverFiles', 'uploadTitle', data['lang'])}}" + path,
            buttons: {
                success: {
                    label: "{{ translate('serverFiles', 'upload', data['lang']) }}",
                    className: "btn-default",
                    callback: async function () {
                        if ($("#files").get(0).files.length === 0) {
                            return hideUploadBox();
                        }

                        let files = document.getElementById("files");
                        handleUpload(files.files, path);
                    },
                },
            },
        });
    });
});


async function handleUpload(files, path) {

    let nFiles = files.length;
    const uploadPromises = [];

    for (let i = 0; i < nFiles; i++) {
        const file = files[i];
        const progressHtml = `
      <div style="width: 100%; min-width: 100%;">
          ${file.name}:
          <br><div
              id="upload-progress-bar-${i + 1}"
              class="progress-bar progress-bar-striped progress-bar-animated"
              role="progressbar"
              style="width: 100%; height: 10px;"
              aria-valuenow="0"
              aria-valuemin="0"
              aria-valuemax="100"
          ></div>
      </div><br>
      `;

        $("#upload-progress-bar-parent").append(progressHtml);

        const uploadPromise = uploadFile(
            "server_upload",
            file,
            path,
            i,
            (progress) => {
                $(`#upload-progress-bar-${i + 1}`).attr(
                    "aria-valuenow",
                    progress
                );
                $(`#upload-progress-bar-${i + 1}`).css(
                    "width",
                    progress + "%"
                );
            }
        );
        uploadPromises.push(uploadPromise);
    }

    await Promise.all(uploadPromises);
}

async function calculateFileHash(file) {
    const arrayBuffer = await file.arrayBuffer();
    const hashBuffer = await crypto.subtle.digest("SHA-256", arrayBuffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const hashHex = hashArray
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");

    return hashHex;
}

$(".move-dialogue").on("click", function () {

});