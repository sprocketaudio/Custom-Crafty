
let selected_row = null;
let move = false;
let copy = false;
let move_copy_source = "";
let move_copy_target = "";
let modified_time = 1.5;
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
///////////////////////////////////////////////////////////////////////////////////////
//LOADING FILES FUNCTIONS
///////////////////////////////////////////////////////////////////////////////////////
async function getTreeView(path) {
    const token = getCookie("_xsrf");
    const cur_body = $("#files-table-body").html();
    $("#files-table-body").html(LOADING_TABLE);
    let res = await fetch(`/api/v2/servers/${serverId}/files`, {
        method: "POST",
        headers: {
            "X-XSRFToken": token,
        },
        body: JSON.stringify({ page: "files", path: path, modified_epoch: modified_time }),
    });
    if (res.status === 304) {
        console.log("Already up to date!")
        $("#files-table-body").html(cur_body);
        return;
    }
    let responseData = await res.json();
    if (responseData.status === "ok") {
        modified_time = responseData.data.root_path.modified;
        console.log(modified_time)
        process_tree_response(responseData);
        location.hash = "";
        location.hash = "context-container"
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

function setup_table_nav(response) {
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
    span.innerHTML = `<i class="fa-solid fa-server"></i>${path_list[0] === serverId ? '&nbsp; <i class="fa-solid fa-rotate-right"></i>' : ""}`; //Set root text as server icon
    container.appendChild(span);
    for (let [index, part] of path_list.entries()) {
        if (!(part === serverId && index === 0)) {
            container.appendChild(document.createTextNode(" > "));
            // Create the span
            const span = document.createElement("span");
            const refresh = document.createElement("span");
            span.className = "tree-nav";
            const previous = path_list.slice(0, index);
            if (index === 0) {
                local_path = previous.join("/") + part
            } else {
                local_path = previous.join("/") + "/" + part
            }
            span.dataset.path = local_path; // or set the actual path if needed // if we're on the first iteration and it's the server ID ignore it
            span.textContent = part; // safe text;
            if (index == path_list.length - 1) {
                refresh.innerHTML = `&nbsp; <i class="fa-solid fa-rotate-right"></i>`;
                span.appendChild(refresh);
            }


            // Append the span
            container.appendChild(span);
        }
    }
}

function setup_table_body(response) {
    const tbody = document.querySelector("tbody");
    const response_entries = Object.entries(response.data)
    for (let [key, value] of response_entries) {
        if (key === "root_path" || key === "db_stats") continue;

        const $tr = $("<tr>")
            .addClass(value.dir ? "directory" : "file")
            .attr("data-path", value.path)
            .attr("data-can_open", value.can_open);

        const $td1 = $("<td>").append($("<div>").append($("<input>").attr("type", "checkbox").addClass("row-select").attr("data-name", key)).addClass("custom-check").addClass("checkbox-lg")).addClass("justify-content-center");

        // Column 1: icon + filename
        const $td2 = $("<td>")
            .addClass("column-1")
            .attr("data-name", key)
            .append($("<span>").html(fileIcon(value)))
            .append("\u00A0\u00A0\u00A0")
            .append(document.createTextNode(key));

        // Column 2: MIME or "Dir"
        const $td3 = $("<td>");
        if (value.mime || value.dir) {
            $td3.text(value.mime ? value.mime : "Dir");
        } else {
            $td3.html('<i class="fa fa-question-circle" aria-hidden="true"></i>');
        }

        // Column 3: modified date
        const $td4 = $("<td>").text(value.modified);

        // Column 4: size
        const $td5 = $("<td>").text(value.size || "-");

        // Column 5: context button
        const $td6 = $("<td>")
            .addClass("context-button")
            .text("...");
        if ($("#files_table thead tr:first th:visible").length > 1) {

            // Append all columns to the row
            $tr.append($td1, $td2, $td3, $td4, $td5, $td6);
        } else {
            $tr.append($td2)
        }

        // Append row to tbody (also as jQuery object)
        $(tbody).append($tr);
    };
}

function process_tree_response(response) {
    setup_table_nav(response);
    update_copy_move_nav();
    $("#files-table-body").html("");
    setup_table_body(response);

    $(".directory").click(function (e) {
        // Prevent the click from firing if it’s on the context menu button
        if ($(e.target).closest(".context-button").length) return;
        if ($(e.target).closest(".row-select").length) return;
        if ($(this).children(".column-1").hasClass("editing")) return;
        getTreeView($(this).attr("data-path"))
    });
    $(".file").click(function (e) {
        // Prevent the click from firing if it’s on the context menu button
        if ($(e.target).closest(".context-button").length) return;
        if ($(e.target).closest(".row-select").length) return;
        if (!$(this).data("can_open")) return;
        if ($(this).children(".column-1").hasClass("editing")) return;
        window.open(`/panel/edit_file?server_id=${serverId}&file=${encodeURI($(this).attr("data-path"))}`, "_blank")
    });
    $(".tree-nav").click(function (e) {
        // Prevent the click from firing if it’s on the context menu button
        if ($(e.target).closest(".context-button").length) return;
        getTreeView($(this).attr("data-path"))
    });
    setup_row_select_listener();
}

function loadMenuContent(tr) {
    const ctxMenuItems = ["rename", "unzip", "download", "copy", "move", "delete"];
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
    add_move_listener();
    add_copy_listener();

}

///////////////////////////////////////////////////////////////////////////////////////
//RENAME FILES/DIRECTORIES FUNCTIONS
///////////////////////////////////////////////////////////////////////////////////////
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
                    renameItem($(selected_row).attr("data-path"), result)
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

///////////////////////////////////////////////////////////////////////////////////////
//CREATE FILES/DIRECTORIES FUNCTIONS
///////////////////////////////////////////////////////////////////////////////////////
function setup_nav_listeners() {
    $("#create-dir").on("click", function () {
        bootbox.prompt(
            "{% raw translate('serverFiles', 'createDirQuestion', data['lang']) %}",
            function (result) {
                if (!result) return;
                const cur_dir = $("#table-nav").attr("data-cur-path");
                create(cur_dir, result, true);
            }
        );
    });

    $("#create-file").on("click", function () {
        bootbox.prompt(
            "{% raw translate('serverFiles', 'createDirQuestion', data['lang']) %}",
            function (result) {
                if (!result) return;
                const cur_dir = $("#table-nav").attr("data-cur-path");
                create(cur_dir, result, false);
            }
        );
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
}

function setup_select_nav() {
    if ($('.row-select:checked').length > 0) {
        move = false;
        copy = false;
        const container = $("#table-nav-buttons");
        const delete_button = $("<button>").attr("id", "delete-files").addClass("btn").addClass("btn-danger").text($("#files_table").attr("data-delete"));

        container.html("")
        container.append("&nbsp;&nbsp;");
        container.append(delete_button);

        $("#delete-files").on("click", function () {
            console.log("deleting files")
        });
    } else {
        default_nav();
    }
}

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
///////////////////////////////////////////////////////////////////////////////////////
//DELETE FILES/DIRECTORIES FUNCTIONS
///////////////////////////////////////////////////////////////////////////////////////
function add_delete_listener() {
    $("#delete").on("click", function () {
        const path = $(selected_row).attr("data-path");
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

///////////////////////////////////////////////////////////////////////////////////////
//DOWNLOAD FILES/DIRECTORIES FUNCTIONS
///////////////////////////////////////////////////////////////////////////////////////
function add_download_listener() {
    $("#download").on("click", function () {
        const path = $(selected_row).attr("data-path");
        window.open(`/api/v2/servers/${serverId}/files/${encodeURIComponent(path)}/download`, '_blank');
    });
}

function add_unzip_listener() {
    $("#unzip").on("click", async function () {
        const path = $(selected_row).attr("data-path");
        const unzip_id = uuidv4()
        const name = $(selected_row).children(".column-1").attr("data-name");
        const unzip_progress = `      
        <div style="width: 100%; min-width: 100%;" id="upload-progress-bar-${unzip_id}-container">
          <small>${name}:</small>
          <br>
        <div class="d-flex">
          <span class="upload-percent" id="upload-percent-${unzip_id}"></span>
          <div
              id="upload-progress-bar-${unzip_id}"
              class="progress-bar progress-bar-striped progress-bar-animated files-progress bg-warning"
              role="progressbar"
              style="width: 100%; height: 10px;"
              aria-valuenow="0"
              aria-valuemin="0"
              aria-valuemax="100"
          ></div>
          </div>
      </div>`
        let res = await fetch(`/api/v2/servers/${serverId}/files/zip/`, {
            method: "POST",
            headers: {
                "X-XSRFToken": token,
            },
            body: JSON.stringify({ folder: path, proc_id: unzip_id }),
        });
        let responseData = await res.json();
        if (responseData.status === "ok") {
            $("#upload-progress-bar-parent").append(unzip_progress);
        } else {
            bootbox.alert({
                title: responseData.error,
                message: responseData.error_data
            });
        }
    });
}

///////////////////////////////////////////////////////////////////////////////////////
//UPLOAD FILES FUNCTIONS
///////////////////////////////////////////////////////////////////////////////////////
$(document).ready(function () {
    //DROPZONE INITIALIZATION
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

function uuidv4() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replaceAll(/[xy]/g, function (c) {
        const r = Math.trunc(Math.random() * 16),
            v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

async function handleUpload(files, path) {

    let nFiles = files.length;
    const uploadPromises = [];
    for (let i = 0; i < nFiles; i++) {
        let file_id = uuidv4();
        const file = files[i];
        const progressHtml = `
      <div style="width: 100%; min-width: 100%;" id="upload-progress-bar-${file_id}-container">
          <small>${file.name}:</small>
          <br>
          <div class="d-flex">
          <span class="upload-percent" id="upload-percent-${file_id}"></span>
          <div
              id="upload-progress-bar-${file_id}"
              class="progress-bar progress-bar-striped progress-bar-animated files-progress"
              role="progressbar"
              style="width: 100%; height: 10px;"
              aria-valuenow="0"
              aria-valuemin="0"
              aria-valuemax="100"
          ></div>
          </div>
      </div>
      `;

        $("#upload-progress-bar-parent").append(progressHtml);

        const uploadPromise = uploadFile(
            "server_upload",
            file,
            path,
            i,
            file_id,
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

///////////////////////////////////////////////////////////////////////////////////////
//MOVE/COPY FILES FUNCTIONS
///////////////////////////////////////////////////////////////////////////////////////
function add_move_listener() {
    $("#move").on("click", function () {
        move = true;
        copy = false;
        move_copy_source = $(selected_row).attr("data-path");
        setup_copy_move_table_nav();
    });
}
function add_copy_listener() {
    $("#copy").on("click", function () {
        move = false;
        copy = true;
        move_copy_source = $(selected_row).attr("data-path");
        setup_copy_move_table_nav();
    });
}

function setup_copy_move_table_nav() {
    const container = $("#table-nav-buttons");
    container.html("");
    const nbsp = "&nbsp;&nbsp;&nbsp;";
    let move_button = $("<button>").attr("id", "move-op").addClass("btn").addClass("btn-info").text($("#files_table").attr("data-move"));
    if (copy) {
        move_button = $("<button>").attr("id", "copy-op").addClass("btn").addClass("btn-info").text($("#files_table").attr("data-copy"));
    }
    const move_source = $("<span>").attr("id", "copy-move-source").text(move_copy_source.replace(serverId, "/"));
    const move_target = $("<span>").attr("id", "copy-move-target");
    const move_arrow = $("<span>").attr("id", "copy-move-arrow").html(`<i class="fa-solid fa-arrow-right"></i>`);
    const cancel = $("<button>").attr("id", "copy-move-cancel").addClass("btn").addClass("btn-secondary").text($("#files_table").attr("data-cancel"));
    container.html("");
    container.append(move_source);
    container.append(nbsp);
    container.append(move_arrow)
    container.append(nbsp);
    container.append(move_target);
    container.append(nbsp);
    container.append(nbsp);
    container.append(move_button);
    container.append(nbsp);
    container.append(cancel);
    setup_move_listener();
}

function update_copy_move_nav() {

    move_copy_target = $("#table-nav").attr("data-cur-path");
    $("#copy-move-target").text(move_copy_target.replace(serverId, "/"));

}


function default_nav() {
    move = false;
    copy = false;
    const container = $("#table-nav-buttons");
    const createDir = $("<button>").attr("id", "create-dir").addClass("btn").addClass("btn-info").text($("#table-nav-buttons").attr("data-dir"));
    const createFile = $("<button>").attr("id", "create-file").addClass("btn").addClass("btn-info").text($("#table-nav-buttons").attr("data-file"));
    const upload = $("<button>").attr("id", "upload-file").addClass("btn").addClass("btn-info").text($("#table-nav-buttons").attr("data-upload"));

    container.html("")
    container.append(createDir);
    container.append("&nbsp;&nbsp;");
    container.append(createFile)
    container.append("&nbsp;&nbsp;");
    container.append(upload);
    setup_nav_listeners();
}

function setup_move_listener() {
    $("#copy-move-cancel").on("click", function () {
        default_nav();
    });
    if (copy) {
        $("#copy-op").on("click", async function () {
            const cur_dir = $("#table-nav").attr("data-cur-path");
            let res = await fetch(`/api/v2/servers/${serverId}/files/copy/`, {
                method: "POST",
                headers: {
                    "X-XSRFToken": token,
                },
                body: JSON.stringify({ source_path: move_copy_source, target_path: move_copy_target }),
            });
            let responseData = await res.json();
            if (responseData.status === "ok") {
                getTreeView(cur_dir);
                default_nav();
            } else {
                bootbox.alert({
                    title: responseData.error,
                    message: responseData.error_data
                });
            }
        });
    } else {
        $("#move-op").on("click", async function () {
            const cur_dir = $("#table-nav").attr("data-cur-path");
            let res = await fetch(`/api/v2/servers/${serverId}/files/move/`, {
                method: "POST",
                headers: {
                    "X-XSRFToken": token,
                },
                body: JSON.stringify({ source_path: move_copy_source, target_path: move_copy_target }),
            });
            let responseData = await res.json();
            if (responseData.status === "ok") {
                getTreeView(cur_dir);
                default_nav();
            } else {
                bootbox.alert({
                    title: responseData.error,
                    message: responseData.error_data
                });
            }
        });
    }
}


///////////////////////////////////////////////////////////////////////////////////////
//PAGE FUNCTIONS
///////////////////////////////////////////////////////////////////////////////////////

$(document).ready(function () {
    setup_nav_listeners();
    $("#file-status").on("click", function () {
        $("#file-status-content").toggleClass("d-none");
        if ($("#file-status-content").hasClass("d-none")) {
            $("#status-caret").html(`<i class="fa-solid fa-caret-up"></i>`)
        } else {
            $("#status-caret").html(`<i class="fa-solid fa-caret-down"></i>`)
        }
    });
    if (webSocket) {
        webSocket.on('zip_status', function (data) {
            if (data.complete) {
                const cur_dir = $("#table-nav").attr("data-cur-path");
                removeProgressItem(data.id);
                getTreeView(cur_dir);
            } else {
                updateProgressBar(data.percent, "server_upload", 1, data.id);
            }
        });
    }
});

function setup_row_select_listener() {
    console.log('listener setup')
    $(".row-select").on("change", function () {
        if ($(this).prop("checked")) {
            $(this).closest("tr").addClass("highlight-row");
        } else {
            $(this).closest("tr").removeClass("highlight-row");
        }
        setup_select_nav();
    });
    $(".root-select").on("change", function () {
        const checkboxes = document.querySelectorAll('.row-select');
        const main_checked = $(this).prop("checked");
        for (const row of checkboxes) {
            $(row).prop("checked", main_checked).trigger("change");
        }
    });
}