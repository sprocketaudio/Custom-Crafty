async function getTreeView(path) {
    const token = getCookie("_xsrf");
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
    console.log(response)
    let path = response.data.root_path.path;
    let text = ``;
    Object.entries(response.data).forEach(([key, value]) => {
        if (key === "root_path" || key === "db_stats") {
            //continue is not valid in for each. Return acts as a continue.
            return;
        }
        let dpath = value.path;
        let filename = key;
        text += `
        <tr>
        <td>${fileIcon(value)}&nbsp;&nbsp;&nbsp;<a class="text-secondary" href="/panel/servers/${serverId}/files/${filename}/edit">${filename}</a></td>
        <td>${value.mime ? value.mime : "Dir"}</td>
        <td>${value.modified}</td>
        <td>Size</td>
        <td>...</td>
        </tr>
        `
        $("#files-table-body").html(text)
    });
}