function app() {
    const config = JSON.parse(document.getElementById("config").innerText)
    const state = {
        timerId: null,
        rowIds: null,
    }

    const container = document.getElementById("accounts")
    const transfers = document.getElementById("transfers")
    const time = document.getElementById("time")
    const error = $("#error")
    const btnPlay =$("#play")
    const btnPause = $("#pause")
    window.CURRENCY = {raw: config.CURRENCY}

    $(document.getElementById("control")).removeClass("invisible")
    btnPlay.addClass("hidden")

    btnPlay.on("click", () => {
        if (state.timerId !== null) {
            clearTimeout(state.timerId)
        }
        state.timerId = setTimeout(doAccountsFetch, 1)
        btnPause.removeClass("hidden")
        btnPlay.addClass("hidden")
    })
    btnPause.on("click", () => {
        if (state.timerId !== null) {
            clearTimeout(state.timerId)
        }
        btnPlay.removeClass("hidden")
        btnPause.addClass("hidden")
    })

    function currency(value) {
        return `${config.CURRENCY[0]}${value.formatCents()}${config.CURRENCY[1]}`
    }

    function updateError(msg) {
        if (!msg) {
            error.addClass("hidden")
        } else {
            error.removeClass("hidden")
            error.attr("title", msg)
        }
    }

    function doAccountsFetch() {
        fetch(config.getUrl, {
            method: "GET",
            headers: {
                "Accept": "application/json",
                "X-CSRFToken": config.csrfToken,
            }
        }).then((response) => {
            if (response.ok) {
                response.json().then((newData) => {
                    time.innerText = DateTimeFormatter.datetime(new Date())
                    updateError(null)

                    if (state.rowIds === null) {
                        const tbl = Template.account_table(newData, currency);

                        state.rowIds = {}
                        $("tr", tbl).each(function () {
                            const e = $(this)
                            const id = e.attr("id")
                            if (id) {
                                state.rowIds[id] = e
                            }
                        })

                        $(container).append(tbl);
                    } else {
                        newData.forEach((e) => {
                            const row = state.rowIds["id_" + e.id]
                            if (row) {
                                row.find(".balance").text(currency(e.balance_cents))
                            }
                        })
                    }
                }).catch((exc) => {
                    console.log(exc)
                    updateError("Data update error")
                })
            } else {
                console.log(response.statusText)
                updateError("Fetch error")
            }
            state.timerId = setTimeout(doAccountsFetch, config.updateMs)
        }).catch((exc) => {
            console.log(exc)
            updateError("Network error")
            state.timerId = setTimeout(doAccountsFetch, config.updateMs)
        })
    }

    function doTransfersFetch() {
        fetch(config.transfersUrl, {
            method: "GET",
            headers: {
                "Accept": "application/json",
                "X-CSRFToken": config.csrfToken,
            }
        }).then((response) => {
            if (response.ok) {
                response.json().then((data) => {
                    const date = DateTimeFormatter.datetime(new Date())
                    const tbl = Template.account_transfers(data, doTransfersFetch, date)
                    const prev = $("table", transfers)
                    if (prev.length) {
                        prev.replaceWith(tbl)
                    } else {
                        $(transfers).append(tbl)
                    }
                })
            }
        })
    }

    state.timerId = setTimeout(doAccountsFetch, 1)
    setTimeout(doTransfersFetch, 2)
}

$(window).on("load", () => app())
