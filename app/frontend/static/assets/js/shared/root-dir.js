
function show_file_tree() {
    $("#dir_select").modal();
}
function getDirView(event = false) {
    if (event) {
        try {
            let path = event.target.parentElement.getAttribute('data-path');
            if (!$(event.target).closest(".tree-folder").hasClass('clicked')) {
                getTreeView(path);
                return;
            }
        } catch {
            console.log("Well that failed");
        }
    } else {
        getTreeView();
    }
}


async function getTreeView(path = "") {
    const token = getCookie("_xsrf");

    let res = await fetch(`/api/v2/import/archive/select`, {
        method: 'POST',
        headers: {
            'X-XSRFToken': token
        },
        body: JSON.stringify({ "file_name": $("#file-uploaded").val(), "local_path": path, }),
    });
    let responseData = await res.json();
    if (responseData.status === "ok") {
        process_tree_response(responseData);
        let x = document.querySelector('.bootbox');
        if (x) {
            x.remove()
        }
        x = document.querySelector('.modal-backdrop');
        if (x) {
            x.remove()
        }
        show_file_tree();

    } else {

        bootbox.alert({
            title: responseData.error,
            message: responseData.error_data
        });
    }
}

function process_tree_response(response) {
    document.getElementById('upload_submit').disabled = false;

    let path = response.data.request_path
    let text = `<ul class="tree-nested d-block" id="${path}-ul">`;
    Object.entries(response.data).forEach(([key, value]) => {
        if (key === "top" || key === "request_path") {
            //continue is not valid in for each. Return acts as a continue.
            return;
        }

        let dpath = value.path;
        let filename = key;
        if (value.dir) {
            text += `<li class="tree-item" id="${dpath}li"  data-path="${dpath}">
                    <div id="${dpath}" data-path="${dpath}" data-name="${filename}" class="tree-caret tree-ctx-item tree-folder">
                    <input type="radio" class="root-input" name="root_path" value="${dpath}">
                    <span id="${dpath}-span" class="files-tree-title" data-path="${dpath}" data-name="${filename}" onclick="getDirView(event)">
                      <i class="far fa-folder text-info"></i>
                      <i class="far fa-folder-open text-info"></i>
                      ${filename}
                      </span>
                    </input></div><li>`
        } else {
            text += `<li
          class="d-block tree-ctx-item tree-file"
          data-path="${dpath}"
          data-name="${filename}"
          onclick="" id="${dpath}li"><input type='radio' class="checkBoxClass d-none file-check" name='root_path' value="${dpath}" disabled><span style="margin-right: 6px;">
          <i class="far fa-file"></i></span></input>${filename}</li>
      `
        }
    });
    text += `</ul>`;

    if (response.data.top) {
        try {
            document.getElementById('main-tree-div').innerHTML += text;
            document.getElementById('main-tree').parentElement.classList.add("clicked");
        } catch {
            document.getElementById('files-tree').innerHTML = text;
        }
    } else {
        try {
            document.getElementById(path + "-span").classList.add('tree-caret-down');
            document.getElementById(path).innerHTML += text;
            document.getElementById(path).classList.add("clicked");
        } catch {
            console.log("Bad")
        }

        let toggler = document.getElementById(`${path}-span`);

        if (toggler.classList.contains('files-tree-title')) {
            document.getElementById(path + "-span").addEventListener("click", function caretListener() {
                document.getElementById(path + "-ul").classList.toggle("d-block");
                document.getElementById(path + "-span").classList.toggle("tree-caret-down");
            });
        }
    }
}

function getToggleMain(event) {
    const path = event.target.parentElement.getAttribute('data-path');
    document.getElementById("files-tree").classList.toggle("d-block");
    document.getElementById(path + "-span").classList.toggle("tree-caret-down");
    document.getElementById(path + "-span").classList.toggle("tree-caret");
}

document.getElementById("root_upload_button").addEventListener("click", function (event) {
    if (document.getElementById('root_upload_button').classList.contains('clicked')) {
        show_file_tree();
        return;
    } else {
        document.getElementById('root_upload_button').classList.add('clicked')
    }
    bootbox.dialog({
        message: `<div class="progress" style="width: 100%;"><div id="upload-progress-bar" class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" aria-valuenow="100" aria-valuemin="0" aria-valuemax="100" style="width: 100%">&nbsp;<i class="fa-solid fa-spinner"></i></div></div>`,
        closeButton: false
    });
    setTimeout(function () {
        getDirView();
    }, 2000);
});