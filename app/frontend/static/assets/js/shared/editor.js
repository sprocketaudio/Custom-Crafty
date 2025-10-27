const urlParams = new URLSearchParams(window.location.search);
const serverId = urlParams.get("server_id");
let serverFileContent = "";

let editor = ace.edit("editor", {
    mode: "ace/mode/javascript",  // or your language
    theme: "ace/theme/monokai",
    selectionStyle: "text",
    enableBasicAutocompletion: true,
    enableLiveAutocompletion: true,
    enableSnippets: true,
    behavioursEnabled: true,  // this enables auto-closing pairs
    wrapBehavioursEnabled: true
});
editor.setOptions({
    behavioursEnabled: true
});
editor.session.setUseSoftTabs(true);
editor.commands.addCommand({
    name: "saveFile",
    bindKey: {
        win: "Ctrl-S",
        mac: "Command-S",
        sender: "editor|cli",
    },
    exec: function (env, args, request) {
        save();
    },
});

let extensionChanges = [
    {
        regex: /^js$/,
        replaceWith: "ace/mode/javascript",
    },
    {
        regex: /^py$/,
        replaceWith: "ace/mode/python",
    },
    {
        regex: /^html$/,
        replaceWith: "ace/mode/html",
    },
    {
        regex: /^yml$/,
        replaceWith: "ace/mode/yaml",
    },
    {
        regex: /^yaml$/,
        replaceWith: "ace/mode/yaml",
    },
    {
        regex: /^txt$/,
        replaceWith: "ace/mode/text",
    },
    {
        regex: /^json$/,
        replaceWith: "ace/mode/json",
    },
    {
        regex: /^java$/,
        replaceWith: "ace/mode/java",
    },
    {
        regex: /^cpp$/,
        replaceWith: "ace/mode/c_cpp",
    },
    {
        regex: /^c$/,
        replaceWith: "ace/mode/c_cpp",
    },
    {
        regex: /^css$/,
        replaceWith: "ace/mode/css",
    },
    {
        regex: /^scss$/,
        replaceWith: "ace/mode/scss",
    },
    {
        regex: /^sass$/,
        replaceWith: "ace/mode/sass",
    },
    {
        regex: /^lua$/,
        replaceWith: "ace/mode/lua",
    },
    {
        regex: /^php$/,
        replaceWith: "ace/mode/php",
    },
    {
        regex: /^ps1$/,
        replaceWith: "ace/mode/powershell",
    },
    {
        regex: /^svg$/,
        replaceWith: "ace/mode/svg",
    },
    {
        regex: /^sh$/,
        replaceWith: "ace/mode/sh",
    },
    {
        regex: /^xml$/,
        replaceWith: "ace/mode/xml",
    },
    {
        regex: /^ts$/,
        replaceWith: "ace/mode/typescript",
    },
    {
        regex: /^properties$/,
        replaceWith: "ace/mode/properties",
    },
    {
        regex: /^log$/,
        replaceWith: "ace/mode/txt",
    },
    {
        regex: /^toml$/,
        replaceWith: "ace/mode/txt",
    },
    {
        regex: /^bat$/,
        replaceWith: "ace/mode/sh",
    },
];


async function get_file() {
    const token = getCookie("_xsrf");
    path = decodeURIComponent(urlParams.get("file"))
    setFileName(path)
    $("#server_uuid").text(serverId);
    let res = await fetch(`/api/v2/servers/${serverId}/files`, {
        method: "POST",
        headers: {
            "X-XSRFToken": token,
        },
        body: JSON.stringify({ page: "files", path: path }),
    });
    let responseData = await res.json();
    console.log(responseData);
    if (responseData.status === "ok") {
        console.log("Got File Contents From Server");
        $("#editorParent").toggle(true); // show
        $("#fileError").toggle(false); // hide
        editor.session.setValue(responseData.data);
        serverFileContent = responseData.data;
        setSaveStatus(true);
    } else {
        bootbox.alert({
            title: responseData.error,
            message: responseData.error_data
        });
    }
}
$(document).ready(function () {
    console.log("Getting file")
    add_server_name();
    set_editor_font_size(localStorage.getItem("font-size") || 12)
    get_file();
});

function setMode(extension) {
    // if the extension matches with the RegEx it will return the replaceWith
    // property. else it will return the one it has. defaults to the extension.
    // this runs for each element in extensionChanges.
    let aceMode = extensionChanges.reduce((output, element) => {
        return extension.match(element.regex) ? element.replaceWith : output;
    }, extension);

    if (!aceMode.startsWith("ace/mode/")) {
        document.querySelector("#file_warn").innerText =
            "{% raw translate('serverFiles', 'unsupportedLanguage', data['lang']) %}";
    } else {
        document.querySelector("#file_warn").innerText = "";

        console.log(aceMode || "ace/mode/text");
        editor.session.setMode(aceMode || "ace/mode/text");
    }
}
function setFileName(name) {
    let fileName = name || "default.txt";
    $("#editingFile").text(fileName);
    document.title = "Crafty Controller - " + fileName


    if (fileName.match(".")) {
        // The pop method removes and returns the last element.
        setMode(fileName.split(".").pop().replace("ace/mode/", ""));
    } else {
        setMode("txt");
        document.querySelector("#file_warn").innerText =
            "{% raw translate('serverFiles', 'unsupportedLanguage', data['lang']) %}";
    }
}

async function add_server_name() {
    const token = getCookie("_xsrf");
    let res = await fetch(`/api/v2/servers/${serverId}`, {
        method: 'GET',
        headers: {
            'X-XSRFToken': token
        },
    });
    let responseData = await res.json();
    if (responseData.status === "ok") {
        console.log(responseData)
        $("#server-name-nav").text(`${responseData.data['server_name']}`);
    }
}

const setSaveStatus = (saved) => {
    if (saved) {
        $("#saveButton").addClass("btn-outline-success");
        $("#saveButton").removeClass("btn-secondary");
        $("#saveButtonText").text($("#saveButton").data("saved"));
    } else {
        $("#saveButton").addClass("btn-secondary");
        $("#saveButton").removeClass("btn-outline-success");
        $("#saveButtonText").text($("#saveButton").data("changes"));
    }
};
["change", "undo", "redo"].forEach((event) =>
    editor.on(event, (event) =>
        setSaveStatus(serverFileContent === editor.session.getValue())
    )
);

async function save() {
    let text = editor.session.getValue();

    const token = getCookie("_xsrf");
    let res = await fetch(`/api/v2/servers/${serverId}/files`, {
        method: "PATCH",
        headers: {
            "X-XSRFToken": token,
        },
        body: JSON.stringify({ path: path, contents: text }),
    });
    let responseData = await res.json();
    if (responseData.status === "ok") {
        serverFileContent = text;
        setSaveStatus(true);
    } else {
        bootbox.alert({
            title: responseData.error,
            message: responseData.error_data
        });
    }
}

function set_editor_font_size(size) {
    console.log(size.toString() + "px")
    editor.setOptions({
        fontSize: size.toString() + "px"
    });
}

function loadMenuContent() {
    const menu = $("#context-menu");
    menu.empty(); // clear previous content

    const fontSize = localStorage.getItem("font-size") || 12;
    const sizeDiv = $("<div>").addClass("menu-item");
    const br1 = $("<br/>")
    const inputLabel = $("<h6>").html(`<i class="fa-solid fa-text-height"></i>`);

    const input = $("<input>").attr({ type: "range", value: fontSize, min: 8, max: 32, id: "font-size" });
    sizeDiv.append(inputLabel);
    sizeDiv.append(input);
    menu.append(sizeDiv);
    $("#font-size").on("input", function () {
        let font_size = $("#font-size").val();
        localStorage.setItem("font-size", font_size)
        set_editor_font_size(font_size)
    });
}