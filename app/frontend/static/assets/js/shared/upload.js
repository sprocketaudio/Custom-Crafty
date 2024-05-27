async function uploadFile(type) {
    file = $("#file")[0].files[0]
    const fileId = uuidv4();
    const token = getCookie("_xsrf")
    document.getElementById("upload_input").innerHTML = '<div class="progress" style="width: 100%;"><div id="upload-progress-bar" class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" aria-valuenow="100" aria-valuemin="0" aria-valuemax="100" style="width: 100%">&nbsp;<i class="fa-solid fa-spinner"></i></div></div>'
    if (!file) {
        alert("Please select a file first.");
        return;
    }

    const chunkSize = 1024 * 1024; // 1MB
    const totalChunks = Math.ceil(file.size / chunkSize);

    const uploadPromises = [];
    let res = await fetch(`/api/v2/servers/import/upload/`, {
        method: 'POST',
        headers: {
            'X-XSRFToken': token,
            'chunked': true,
            'fileSize': file.size,
            'type': type,
            'total_chunks': totalChunks,
            'filename': file.name,
            'fileId': fileId,
        },
        body: null,
    });

    let responseData = await res.json();

    let file_id = ""
    if (responseData.status === "ok") {
        file_id = responseData.data["file-id"]
    }
    for (let i = 0; i < totalChunks; i++) {
        const start = i * chunkSize;
        const end = Math.min(start + chunkSize, file.size);
        const chunk = file.slice(start, end);

        const uploadPromise = fetch(`/api/v2/servers/import/upload/`, {
            method: 'POST',
            body: chunk,
            headers: {
                'Content-Range': `bytes ${start}-${end - 1}/${file.size}`,
                'Content-Length': chunk.size,
                'fileSize': file.size,
                'chunked': true,
                'type': type,
                'total_chunks': totalChunks,
                'filename': file.name,
                'fileId': fileId,
                'chunkId': i,
            },
        }).then(response => response.json())
            .then(data => {
                if (data.status === "completed") {
                    $("#upload_input").html(`<div class="card-header header-sm d-flex justify-content-between align-items-center" style="width: 100%;"><input value="${file.name}" type="text" id="file-uploaded" disabled></input> 🔒</div>`);
                    if (type === "import") {
                        document.getElementById("lower_half").style.visibility = "visible";
                        document.getElementById("lower_half").hidden = false;
                    } else if (type === "background") {
                        setTimeout(function () {
                            location.href = `/panel/custom_login`
                        }, 2000)

                    }
                } else if (data.status !== "partial") {
                    throw new Error(data.message);
                }
                // Update progress bar
                const progress = (i + 1) / totalChunks * 100;
                updateProgressBar(Math.round(progress));
            });

        uploadPromises.push(uploadPromise);
    }

    try {
        await Promise.all(uploadPromises);
    } catch (error) {
        bootbox.alert("Error uploading file: " + error.message);
    }
}

function updateProgressBar(progress) {
    $(`#upload-progress-bar`).css('width', progress + '%');
    $(`#upload-progress-bar`).html(progress + '%');
}

function uuidv4() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        const r = Math.random() * 16 | 0,
            v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}