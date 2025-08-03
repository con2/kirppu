import VendorInfo from "./vendor_info.jsx";

export function AddVendorNote({withButton, withConfirm}) {
    if (withConfirm === undefined || withConfirm === null) {
        withConfirm = true
    }
    const noteInput = <input type="text" className="form-control" id="note" disabled={withConfirm} aria-describedby="note_help"
                             placeholder={gettext("Note")}/>
    function toggle() {
        noteInput.disabled = !this.checked
    }
    return (
        <form onsubmit={() => false}>
            {withConfirm && <div className="checkbox" style="min-width: 8em;">
                <label>
                    <input type="checkbox" id="enable_note" onchange={toggle}/>
                    {gettext("Add a note?")}
                </label>
            </div>}
            <div className="form-group">
                {noteInput}
                <span id="note_help" className="help-block">{gettext("Please note, that the vendor has a right to see notes attached to them on request.")}</span>
            </div>
            {withButton && <div className="form-group">
                <button className="btn btn-primary" type="button">{gettext("Add")}</button>
            </div>}
        </form>
    )
}

export function insufficient_vendor_info(vendor, item) {
    return [
        <VendorInfo vendor={vendor} />,
        <div>{item.code + " " + item.name}</div>,
        <div className="alert alert-info">
            {gettext("Vendor might not be identifiable from information above.")}
        </div>,
        <AddVendorNote withButton={false}/>,
    ]
}

function Note({text, erased, pk, markNote}) {
    return (
        <tr>
            <td className={erased ? "erased" : ""}>
                {text}
                {erased ? <span className="glyphicon glyphicon-ok text-success"/> : ""}
            </td>
            <td className="min-width"><button type="button" className="btn btn-link btn-xs" onclick={() => markNote(pk)}>
                <span className="glyphicon glyphicon-check">{" "}</span>
            </button></td>
        </tr>
    )
}

export function vendor_note_list(items, onAddNote, onComplete) {
    return (
        <div className="hidden-print" id="vendor_note_list">
            <h3 className="text-muted">
                {gettext("Notes")}
                {" "}
                <button type="button" className="btn btn-primary btn-xs" onclick={onAddNote}>
                    <span className="glyphicon glyphicon-plus">{" "}</span>
                </button>
            </h3>
            <table className="table table-condensed">
            <tbody>
                {items.map((e) => <Note text={e.text} erased={e.erased} pk={e.id} markNote={onComplete}/>)}
            </tbody>
            </table>
        </div>
    )
}
