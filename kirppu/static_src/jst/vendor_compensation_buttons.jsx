export default function render({onConfirm, onAbort, onContinue, continueWarn, onRetry, abortPrimary}) {
    const btns = [
        onConfirm &&
        <input type="button" className={"btn " + (continueWarn ? "btn-warning" : "btn-success")}
               value={gettext('Confirm cash')}
               onclick={onConfirm}
               id="vendor-compensation-confirm"
               disabled
        />

        , onAbort &&
        <input type="button" className={"btn " + (abortPrimary ? "btn-primary" : "btn-default")}
               value={gettext('Cancel')}
               onclick={onAbort}
        />

        , onRetry &&
        <input type="button" className="btn btn-primary"
               value={gettext('Retry')}
               onclick={onRetry}
        />

        , onContinue &&
        <input type="button" className={"btn " + (continueWarn ? "btn-warning" : "btn-primary")}
               value={gettext('Continue')}
               onclick={onContinue}
        />
    ]
    if (onConfirm) {
        setTimeout(function () {
            $("#vendor-compensation-confirm").removeAttr("disabled")
        }, 3000)
    }
    return (
        <div>
            {btns.reduce(
                (prev, cur) => {
                    if (cur) {
                        if (prev.length) prev.push(" ")
                        prev.push(cur)
                    }
                    return prev
                },
                []
            )}
        </div>
    )
}
