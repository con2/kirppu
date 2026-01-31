import ResultTable from "./result_table.jsx";

export function vendor_list() {
    return (
        <div>
        <p>Specifiers: <code>id:###</code> <code>email:###</code> <code>box:###</code></p>
        <ResultTable head={
            <tr>
                <th className="badged_index">#</th>
                <th className="receipt_username">{gettext("username")}</th>
                <th className="receipt_vendor_id">{gettext("id")}</th>
                <th className="receipt_name">{gettext("name")}</th>
                <th className="receipt_email">{gettext("email")}</th>
                <th className="receipt_phone">{gettext("phone")}</th>
            </tr>
        }/>
        </div>
    )
}

function formatVendor(vendor) {
    if (vendor["username"]) {
        return vendor["username"]
    } else if (vendor["owner"]) {
        return pgettext("Behalf of someone", "(via %s)").replace("%s", vendor["owner"])
    }
}

export function vendor_list_item({vendor, index, action}) {
    const cols = [
        <td className="badged_index">{index}</td>,
        <td>{formatVendor(vendor)}</td>
    ]
    for (const a of ['id', 'name', 'email', 'phone']) {
        cols.push(<td>{vendor[a]}</td>)
    }
    return (
        <tr className="receipt_tr_clickable" onclick={action}>
            {cols}
        </tr>
    )
}
