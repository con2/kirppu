function btn({text, classes, dismiss, click}) {
    if (dismiss === undefined || dismiss === null) {
        dismiss = true
    }
    return <button type="button" className={"btn " + classes} data-dismiss={dismiss ? "modal" : ""} onclick={click}>{text}</button>
}

/**
 * @typedef DialogButton
 * @type {object}
 * @property {String} text
 * @property {String} classes
 * @property {Boolean} [dismiss]
 * @property {Function, null} [click]
 */

/**
 * @param {Object} params
 * @param {String} params.titleText
 * @param {DialogButton[]} params.buttons
 */
export default function render({titleText, body, buttons}) {
    return (
        <div className="modal fade" tabIndex="-1" role="dialog" aria-labelledby="dialog_label">
            <div className="modal-dialog">
                <div className="modal-content">
                    <div className="modal-header">
                        <button type="button" className="close" data-dismiss="modal"><span
                            aria-hidden="true">&times;</span><span className="sr-only">{gettext("Close")}</span></button>
                        <h4 className="modal-title" id="dialog_label">{titleText}</h4>
                    </div>
                    <div className="modal-body">{body}</div>
                    <div className="modal-footer">
                        {buttons.map((e) => btn(e))}
                    </div>
                </div>
            </div>
        </div>
    )
}
