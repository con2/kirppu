(function() {
    // Signup link
    $("#copylink").on("click", function(e) {
        e.preventDefault();
    })

    // People management
    const config = JSON.parse(document.getElementById("config").innerText);
    const data = JSON.parse(document.getElementById("data").innerText);
    const availableClerks = JSON.parse(document.getElementById("available").innerText)
        .sort((a, b) => {
            return a.localeCompare(b)
        });

    const persons = document.getElementById("person-infos")
    $(persons).empty();

    const tbody = Template.person_info_table(data, false)
    const body = document.getElementById("content-body");
    $(body).empty().append(tbody);

    const edits = document.getElementsByClassName("row-edit");

    const actions = {
        show: null,
        save: null,
        edit: null,
    };
    actions.show = function() {
        const row = $(this).parents("tr");
        const idx = row.data("index");
        const e = Template.PersonRow({info: data[idx], index: idx, edit: false});
        $("button", e).on("click", actions.edit);
        row.replaceWith(e);
    };

    actions.save = function() {
        const row = $(this).parents("tr");
        const idx = row.data("index");
        const id = row.data("id");

        const originalValues = data[idx];
        const changeValues = {};
        row.find("input[type=checkbox]").each((_, el) => {
            changeValues[el.name] = el.checked;
            el.disabled = true;
        });
        changeValues["clerk_code"] = row.find("select[name=has_clerk_code]").val();

        const status = $("<span>").text(gettext("Saving"));
        const buttonContainer = $(".button-cell", row);
        const orgButtons = buttonContainer.children();
        buttonContainer.empty().append(status);


        const changePayload = {
            id: id,
            action: "update",
            expect: originalValues,
            values: changeValues
        };
        const changeBlob = new Blob([JSON.stringify(changePayload)], {type: "application/json"})

        fetch(config.postUrl, {
            method: "POST",
            body: changeBlob,
            headers: {
                "X-CSRFToken": config.csrfToken,
            }
        }).then((response) => {
            if (response.ok) {
                response.json().then((newData) => {
                    data[idx] = newData;

                    // Remove clerk code from available array.
                    const newClerkCode = newData["clerk_code"];
                    const inAvailable = availableClerks.findIndex((e) => { return e === newClerkCode; });
                    if (inAvailable >= 0) {
                        availableClerks.splice(inAvailable, 1);
                    }

                    document.getElementById("data").innerText = JSON.stringify(data);
                    document.getElementById("available").innerText = JSON.stringify(availableClerks);
                    // Assign status as `this` to fake button location, as the button has been replaced.
                    actions.show.bind(status)();
                })
            } else {
                console.log(response);
                row.find("input").each((_, el) => {
                    el.disabled = false;
                });
                buttonContainer.empty().append(orgButtons);
                $("button[data-action=save]", buttonContainer).on("click", actions.save);
                $("button[data-action=cancel]", buttonContainer).on("click", actions.show);
                alert("Save failed.");
            }
        });
    }

    actions.edit = function() {
        const row = $(this).parents("tr");
        const idx = row.data("index");
        const e = Template.PersonRow({
            info: data[idx],
            index: idx,
            edit: true,
            availableClerks: availableClerks,
        });
        $("button[data-action=save]", e).on("click", actions.save);
        $("button[data-action=cancel]", e).on("click", actions.show);
        row.replaceWith(e);
    };

    // default bind
    for (let idx in edits) {
        let btn = edits[idx];
        btn.onclick = actions.edit;
    }
})();

(function() {
    const config = JSON.parse(document.getElementById("config").innerText);
    const body = document.getElementById("signup-body");
    const signupData = JSON.parse(document.getElementById("signups").innerText);

    const actions = {
        showDialog: null,
        sendSignupResolution: null,
    };

    actions.showDialog = (info) => {
        const dlg = $(Template.accept_person_dialog(info, signupData.cols))
        const selections = {
            accept: null,
        };
        const buttons = dlg.find("button[data-action]");
        buttons.on("click", function() {
            const action = $(this).data("action");
            if (action === "accept") {
                actions.sendSignupResolution(dlg, {
                    action: "accept",
                    username: info.username,
                    accept: selections.accept,
                })
            } else if (action === "reject") {
                actions.sendSignupResolution(dlg, {
                    action: "reject",
                    username: info.username,
                })
            }
            // ignore "close"
        });
        const accept = buttons.filter("[data-action=accept]");

        dlg.find("#accept-no").on("click", () => {
            accept.attr("disabled", "disabled");
            selections.accept = "no";
        }).click()  // Default selection.
        dlg.find("#accept-clerk").on("click", () => {
            accept.removeAttr("disabled");
            selections.accept = "clerk";
        })
        dlg.find("#accept-perm").on("click", () => {
            accept.removeAttr("disabled");
            selections.accept = "permissions";
        })

        $("#body").append(dlg);
        dlg.on("hidden.bs.modal", () => {
            dlg.remove();
        });
        dlg.modal()
    }

    const signupTable = $(Template.signup_table(
        signupData.cols,
        signupData.data,
        actions.showDialog,
    ))

    actions.sendSignupResolution = (dlg, changePayload) => {
        const changeBlob = new Blob([JSON.stringify(changePayload)], {type: "application/json"})

        fetch(config.postUrl, {
            method: "POST",
            body: changeBlob,
            headers: {
                "X-CSRFToken": config.csrfToken,
            }
        }).then((response) => {
            if (response.ok) {
                dlg.modal("hide");
                response.json().then((newData) => {
                    // Update the signup row.
                    const signupData = newData.signup;
                    const newRow = Template.signup_row(signupData, actions.showDialog)
                    const oldRow = $("tbody > tr", signupTable).filter(function() {
                        const u = $(this).data("username");
                        console.log(u);
                        return u === signupData.username;
                    }).first();
                    oldRow.replaceWith(newRow);
                    // TODO: Maybe update the json content.
                });
                // TODO: Add row to persons
                // TODO: Remove from top?
            } else {
                console.log(response);
                alert("Accept failed")
            }
        })
    }

    $(body).append(signupTable);
})();
