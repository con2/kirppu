
export function receipt_table({caption}) {
    return (
        <table className="table table-striped table-hover table-condensed">
            {caption && <caption className="h3">{caption}</caption>}
            <thead>
            <tr>
                <th className="receipt_vendor_id">{gettext("vendor")}</th>
                <th className="receipt_code">{gettext("code")}</th>
                <th className="receipt_item">{gettext("item")}</th>
                <th className="receipt_price">{gettext("price")}</th>
            </tr>
            </thead>
            <tbody/>
        </table>
    )
}

export function receipt_table_row({joined, vendor, code, name, price, text}) {
    if (joined) {
        return <tr><td colSpan="4">{text}</td></tr>
    }
    return (
        <tr id={code}>
            <td className="receipt_vendor_id numeric">{vendor}</td>
            <td className="receipt_code">{code}</td>
            <td className="receipt_item">{name}</td>
            <td className="receipt_price numeric">{price}</td>
        </tr>
    )
}
