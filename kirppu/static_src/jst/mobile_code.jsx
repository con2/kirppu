import dialog from "./dialog.jsx";

export default function mobile_code_dialog(onCreate) {
    function formHandler(e) {
        e.preventDefault()
        onCreate()
    }
    return dialog({
        titleText: gettext("Mobile code"),
        body: [
            <p>{gettext("Creating a code will invalidate all old codes.")}</p>,
            <form onsubmit={formHandler}>
                <div className="form-group">
                    <label className="control-label" htmlFor="expiry-time">{gettext("Expiry time (minutes)")}</label>
                    <input className="form-control" type="number" placeholder="10" step="10" value="10" id="expiry-time"/>
                    <div className="help-block">6 h = 360 min, 12 h = 720 min, 1 d = 1440 min, 2 d = 2880 min</div>
                </div>
            </form>,
            <div className="short-code-display"></div>
        ],
        buttons: [
            {text: gettext("Create new code"), classes: "btn-warning", dismiss: false, click: onCreate},
            {text: gettext("Close"), classes: "btn-default"},
        ]
    })
}
