const urlParams = new URLSearchParams(window.location.search);
const serverId = urlParams.get("server_id");

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