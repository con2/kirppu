const termsApp = (function (termsUrl) {
    const cb = $("#terms-accepted");
    const btn = $("#terms-accept");

    cb.change(function () {
        if ($(this).prop("checked")) {
            btn.prop("disabled", "");
        } else {
            btn.prop("disabled", "disabled");
        }
    });
    btn.click(function () {
        cb.prop("disabled", "disabled");
        btn.prop("disabled", "disabled");

        $.post(termsUrl
        ).done(function (data) {
            if (data.result == "ok") {
                btn.addClass("hidden");
                const tpl = $("#terms-template").removeClass("hidden");
                tpl.text(tpl.text().replace("%s", data.time));
                $("#terms-style").text("");
            } else {
                $("#terms-message").text("error 1");
                console.error(data);
            }
        }).fail(function (jqXHR) {
            let text;
            if (jqXHR.responseJSON) {
                text = jqXHR.responseJSON.message || "error 2";
            } else {
                text = "error 3";
            }
            $("#terms-message").text(text);
        });
    });
    $("#terms-form").removeClass("hidden");
});
