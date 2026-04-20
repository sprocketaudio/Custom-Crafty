const urlParams = new URLSearchParams(globalThis.location.search);
const serverId = urlParams.get("server_id");
const rawFileParam = urlParams.get("file") || "";
let path = rawFileParam;
try {
    path = decodeURIComponent(rawFileParam);
} catch (error) {
    console.warn("Failed to decode file query parameter, using raw value.", error);
}
let modified_epoch = 1.5;
let serverFileContent = "";
let themes = { "dark": "ace/theme/monokai", "light": "ace/theme/chrome", "default": "ace/theme/dracula" }
let theme = themes["default"];
for (const [key, value] of Object.entries(themes)) {
    if ($("html").hasClass(key)) {
        console.log(key)
        theme = value
    }
}
let editor = ace.edit("editor", {
    mode: "ace/mode/javascript",  // or your language
    theme: theme,
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

let is_saved = true;
let editorEncoding = null;
let availableEditorEncodings = [];

function getFileParentDir(filePath) {
    if (!filePath) {
        return "";
    }

    const normalizedPath = filePath.replace(/\\/g, "/").replace(/\/+$/, "");
    const lastSlashIndex = normalizedPath.lastIndexOf("/");
    if (lastSlashIndex <= 0) {
        return "";
    }

    return normalizedPath.substring(0, lastSlashIndex);
}

function buildFilesPanelUrl() {
    if (!serverId) {
        return "";
    }

    let filesUrl = `/panel/server_detail?id=${encodeURIComponent(serverId)}&subpage=files`;
    const parentDir = getFileParentDir(path);
    if (parentDir) {
        filesUrl += `&dir=${encodeURIComponent(parentDir)}`;
    }

    return `${filesUrl}#context-container`;
}

function wireBackToFilesLink() {
    const $backToFilesLink = $("#backToFilesLink");
    if (!$backToFilesLink.length) {
        return;
    }

    const filesUrl = buildFilesPanelUrl();
    if (filesUrl) {
        $backToFilesLink.attr("href", filesUrl);
        return;
    }

    if (!$backToFilesLink.attr("href")) {
        $backToFilesLink.attr("href", "#");
    }
    $backToFilesLink.on("click", (e) => {
        e.preventDefault();
        globalThis.history.back();
    });
}

function applyEditorEncodingMode() {
    if (editorEncoding === "nbt_json") {
        setMode("json");
        return;
    }
    if (editorEncoding === "snbt") {
        setMode("txt");
    }
}

function getAlternateEditorEncoding() {
    if (!Array.isArray(availableEditorEncodings) || !editorEncoding) {
        return null;
    }
    return availableEditorEncodings.find((encoding) => encoding !== editorEncoding) || null;
}

function updateNbtEncodingButton() {
    const $nbtEncodingButton = $("#nbtEncodingButton");
    if (!$nbtEncodingButton.length) {
        return;
    }

    const alternateEncoding = getAlternateEditorEncoding();
    if (!alternateEncoding) {
        $nbtEncodingButton.addClass("d-none");
        $nbtEncodingButton.removeAttr("data-next-encoding");
        return;
    }

    const isSwitchingToSnbt = alternateEncoding === "snbt";
    const label = isSwitchingToSnbt
        ? $("#editor-wrapper").attr("data-switchRawSnbt")
        : $("#editor-wrapper").attr("data-switchEasyJson");

    $nbtEncodingButton
        .text(label || alternateEncoding)
        .attr("data-next-encoding", alternateEncoding)
        .removeClass("d-none");
}

function wireNbtEncodingButton() {
    const $nbtEncodingButton = $("#nbtEncodingButton");
    if (!$nbtEncodingButton.length) {
        return;
    }

    $nbtEncodingButton.off("click").on("click", async function () {
        const nextEncoding = $(this).attr("data-next-encoding");
        if (!nextEncoding) {
            return;
        }
        if (!is_saved) {
            const leaveMsg = $("#saveButton").data("leave") || "You have unsaved changes.";
            if (!globalThis.confirm(leaveMsg)) {
                return;
            }
        }
        await get_file(nextEncoding);
    });
}

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
        regex: /^conf$/,
        replaceWith: "ace/mode/yaml",
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
        regex: /^dat$/,
        replaceWith: "ace/mode/text",
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


async function get_file(requestedEncoding = null) {
    const token = getCookie("_xsrf");
    setFileName(path)
    $("#server_uuid").text(serverId);
    const requestPayload = { page: "files", path: path };
    if (requestedEncoding) {
        requestPayload.editor_encoding = requestedEncoding;
    }
    let res = await fetch(`/api/v2/servers/${serverId}/files`, {
        method: "POST",
        headers: {
            "X-XSRFToken": token,
        },
        body: JSON.stringify(requestPayload),
    });
    let responseData = await res.json();
    console.log(responseData);
    if (responseData.status === "ok") {
        console.log("Got File Contents From Server");
        $("#editorParent").toggle(true); // show
        editor.session.setValue(responseData.data.content);
        serverFileContent = responseData.data.content;
        modified_epoch = responseData.data.attributes.modified_epoch;
        editorEncoding = responseData.data.attributes.editor_encoding || null;
        availableEditorEncodings = responseData.data.attributes.editor_encoding_options || [];
        updateNbtEncodingButton();
        applyEditorEncodingMode();
        setSaveStatus(true);
        $("#file_size_sm").text(responseData.data.attributes.size);
        $("#file_type_sm").text(responseData.data.attributes.mime);
        $("#file_modified_sm").text(responseData.data.attributes.modified);

    } else {
        bootbox.alert({
            title: responseData.error,
            message: responseData.error_data
        });
    }
}
$(document).ready(function () {
    console.log("Getting file")
    wireBackToFilesLink();
    wireNbtEncodingButton();
    add_server_name();
    set_editor_font_size(localStorage.getItem("font-size") || 12)
    setKeybinds(localStorage.getItem("keybind") || "null")
    get_file();
});

function setMode(extension) {
    // if the extension matches with the RegEx it will return the replaceWith
    // property. else it will return the one it has. defaults to the extension.
    // this runs for each element in extensionChanges.
    let aceMode = extensionChanges.reduce((output, element) => {
        return extension.match(element.regex) ? element.replaceWith : output;
    }, extension);

    if (aceMode.startsWith("ace/mode/")) {

        console.log(aceMode || "ace/mode/text");
        editor.session.setMode(aceMode || "ace/mode/text");
    } else {
        $("#warning").removeClass("d-none");
    }
}
function setFileName(fileName = "default.txt") {
    $("#editingFile").text(fileName);
    document.title = "Crafty Controller - " + fileName


    if (/\./.exec(fileName)) {
        // The pop method removes and returns the last element.
        setMode(fileName.split(".").pop().replace("ace/mode/", ""));
    } else {
        setMode("txt");
        bootbox.alert(
            "{% raw translate('serverFiles', 'unsupportedLanguage', data['lang']) %}");
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
        is_saved = true;
    } else {
        $("#saveButton").addClass("btn-secondary");
        $("#saveButton").removeClass("btn-outline-success");
        $("#saveButtonText").text($("#saveButton").data("changes"));
        is_saved = false;
    }
};

let event_types = ["change", "undo", "redo"]
for (let ev of event_types) {
    editor.on(ev, (event) =>
        setSaveStatus(serverFileContent === editor.session.getValue())
    )
}

async function save(overwrite = false) {
    let text = editor.session.getValue();

    const savePayload = {
        path: path,
        contents: text,
        modified_epoch: modified_epoch,
        overwrite: overwrite,
    };
    if (editorEncoding) {
        savePayload.editor_encoding = editorEncoding;
    }

    const token = getCookie("_xsrf");
    let res = await fetch(`/api/v2/servers/${serverId}/files`, {
        method: "PATCH",
        headers: {
            "X-XSRFToken": token,
        },
        body: JSON.stringify(savePayload),
    });
    if (res.status === 409) {
        bootbox.prompt({
            title: `${$("#editor-wrapper").attr("data-changeConflict")}`,
            message: `${$("#editor-wrapper").attr("data-serverModified")}`,
            inputType: 'select',
            inputOptions: [{
                text: `${$("#editor-wrapper").attr("data-overwrite")}`,
                value: 'overwrite'
            },
            {
                text: `${$("#editor-wrapper").attr("data-repull")}`,
                value: 'repull'
            },],
            callback: function (result) {
                if (result === "overwrite") {
                    save(true);
                } else if (result === "repull") {
                    get_file(editorEncoding);
                } else {
                    return;
                }
            }
        });
    }
    let responseData = await res.json();
    if (responseData.status === "ok") {
        serverFileContent = text;
        modified_epoch = responseData.data.attributes.modified_epoch;
        setSaveStatus(true);
        $("#file_size_sm").text(responseData.data.attributes.size);
        $("#file_type_sm").text(responseData.data.attributes.mime);
        $("#file_modified_sm").text(responseData.data.attributes.modified);

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
    load_text_size_control(menu);
    load_keybind_control(menu);
}

function load_text_size_control(menu) {
    const fontSize = localStorage.getItem("font-size") || 12;
    const sizeDiv = $("<div>").addClass("menu-item").addClass("edit-configure");
    const inputLabel = $("<h6>").html(`<i class="ph ph-text-t"></i>`);

    const input = $("<input>").attr({ type: "range", value: fontSize, min: 8, max: 32, id: "font-size" }).addClass("edit-configure");
    sizeDiv.append(inputLabel);
    sizeDiv.append(input);
    menu.append(sizeDiv);
    $("#font-size").on("input", function () {
        let font_size = $("#font-size").val();
        localStorage.setItem("font-size", font_size)
        set_editor_font_size(font_size)
    });
}

function load_keybind_control(menu) {
    const controlContainer = $("<div>").addClass("menu-item").addClass("edit-configure");
    const keyboardOptions = [
        { label: "Default", handler: "null" },
        { label: "Vim", handler: "ace/keyboard/vim" },
        { label: "Emacs", handler: "ace/keyboard/emacs" },
        { label: "Sublime", handler: "ace/keyboard/sublime" },
        { label: "VSCode", handler: "ace/keyboard/vscode" },
    ];
    let cur_selection = localStorage.getItem("keybind") || "null"
    for (let opt of keyboardOptions) {
        const btn = document.createElement("button");
        let className = "btn-outline-info"
        if (cur_selection == opt.handler) {
            className = "btn-outline-success";
        }
        btn.className = `btn ${className}`;
        btn.textContent = opt.label;
        btn.dataset.handlerName = opt.handler;

        btn.addEventListener("click", (e) => {
            e.stopPropagation();

            const clickedBtn = e.currentTarget; // always the button you attached the handler to

            // Reset all buttons in the same container to secondary
            const container = clickedBtn.parentElement; // .menu-item
            const button_elements = container.querySelectorAll("button")
            for (let b of button_elements) {
                b.classList.remove("btn-outline-success");
                b.classList.add("btn-outline-info");
            }

            // Highlight clicked button
            clickedBtn.classList.remove("btn-outline-info");
            clickedBtn.classList.add("btn-outline-success");

            // Call your existing handler
            setKeyboard(clickedBtn);
        });

        controlContainer.append(btn);
        menu.append(controlContainer)
    }
}

function setKeybinds(handlerName) {
    if (handlerName == "null") handlerName = null;
    editor.setKeyboardHandler(handlerName, () => {
        if (handlerName == "ace/keyboard/vim") {
            require("ace/keyboard/vim").Vim.defineEx("write", "w", function () {
                save();
            });
        }
    });
}

function setKeyboard(target) {
    let handlerName = target.dataset.handlerName;
    localStorage.setItem("keybind", handlerName);
    setKeybinds(handlerName);

    const $clickedBtn = $(this);
    const $container = $clickedBtn.closest(".menu-item");

    // Reset all buttons in this container to secondary
    $container.find("button").removeClass("btn-primary").addClass("btn-secondary");

    // Highlight the clicked button
    $clickedBtn.removeClass("btn-secondary").addClass("btn-primary");
}

globalThis.addEventListener('beforeunload', (e) => {
    if (!is_saved) {
        e.preventDefault();
        globalThis.alert('You have unsaved changes. Are you sure you want to leave?');
    }
});
