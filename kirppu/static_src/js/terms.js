const termsApp = (function (termsUrl, bankInfo) {
    const eall = $("#__all__-error");
    const cb = $("#terms-accepted");
    const btn = $("#terms-accept");
    const with_account = $(".bank_with_account");
    const biban = $("#bank_iban");
    const eiban = $("#bank_iban-error");
    const liban = $("#label_iban");
    const bbic = $("#bank_bic");
    const ebic = $("#bank_bic-error");
    const reason = $("#bank_reason");
    const ereason = $("#bank_reason-error");
    const lreason = $("#label_reason");

    function getError(value) {
        if (value) {
            let o = "";
            for (let i in value) {
                const v = value[i];
                if (v.message) {
                    o += "\n- " + v.message;
                }
            }
            return o.trim();
        } else {
            return "";
        }
    }

    function updateErrors(errs) {
        eall.text(getError(errs["__all__"]));
        eiban.text(getError(errs["iban"]));
        ebic.text(getError(errs["bic"]));
        ereason.text(getError(errs["reason"]));
    }

    function updateDisabled() {
        if (with_account.prop("checked")) {
            biban.prop("disabled", "");
            bbic.prop("disabled", "");
            reason.prop("disabled", "disabled");
            liban.addClass("required");
            lreason.removeClass("required");
        } else {
            biban.prop("disabled", "disabled");
            bbic.prop("disabled", "disabled");
            reason.prop("disabled", "");
            liban.removeClass("required");
            lreason.addClass("required");
        }
    }

    with_account.change(updateDisabled);
    updateDisabled();

    cb.change(function () {
        if ($(this).prop("checked")) {
            btn.prop("disabled", "");
        } else {
            btn.prop("disabled", "disabled");
        }
    });
    btn.click(function () {
        updateErrors({})
        cb.prop("disabled", "disabled");
        btn.prop("disabled", "disabled");
        const isSelected = cb.prop("checked");

        let data = {
            "terms-accepted": isSelected ? "true" : "false",
        }
        if (bankInfo) {
            data["with_account"] = with_account[0].checked;
            data["iban"] = biban.val();
            data["bic"] = bbic.val();
            data["reason"] = reason.val();
        }

        $.post(termsUrl, data
        ).done(function (data) {
            if (data.result === "ok") {
                if (data.time) {
                    cb.attr("checked", "checked");
                }
                if (data.iban !== undefined) {
                    biban.val(data.iban);
                    biban.attr("value", data.iban);
                }
                if (data.bic !== undefined) {
                    bbic.val(data.bic);
                    bbic.attr("value", data.bic);
                }
                if (data.reason !== undefined) {
                    reason.val(data.reason);
                    reason.attr("value", data.reason);
                }
                if (data.with_account !== undefined) {
                    if (data.with_account) {
                        $(with_account[1]).removeAttr("checked");
                        $(with_account[0]).attr("checked", "checked");
                    } else {
                        $(with_account[0]).removeAttr("checked");
                        $(with_account[1]).attr("checked", "checked");
                    }
                }
                if (bankInfo) {
                    btn.text(gettext("Update"));
                    btn.prop("disabled", "");
                } else {
                    btn.addClass("hidden");
                }

                const tpl = $("#terms-template").removeClass("hidden");
                tpl.text(tpl.text().replace("%s", data.time));
                $("#terms-style").text("");
                $("#terms-form")[0].reset();
            } else {
                $("#terms-message").text("error 1");
                console.error(data);
            }
        }).fail(function (jqXHR) {
            let text;
            if (jqXHR.responseJSON) {
                updateErrors(jqXHR.responseJSON["errors"])
                if (!jqXHR.responseJSON["time"]) {
                    cb.prop("disabled", "");
                }
                btn.prop("disabled", "");
            } else {
                text = "error 3";
            }
            $("#terms-message").text(text);
        });
    });
    $("#terms-form").removeClass("hidden");
});
