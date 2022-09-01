import {Options} from "./form_fields.jsx";
import Dialog from "./dialog.jsx";

export function account_transfer_form(accounts) {
    const currency = CURRENCY.raw
    const options = accounts.map((e) => {
        return {
            name: e.id,
            description: `${e.name} (${currency[0]}${e.balance_cents.formatCents()}${currency[1]})`,
        }
    });
    options.unshift({name: null, description: gettext("Select…")})

    return (
        <form className="form-horizontal" id="account_transfer_form">
            <div className="form-group">
                <label htmlFor="src_account" className="col-sm-2 control-label">
                    {gettext("Source")}
                </label>
                <div className="col-sm-10">
                    <Options id="src_account"
                             className="form-control"
                             list={options}
                    />
                </div>
            </div>
            <div className="form-group">
                <label htmlFor="dst_account" className="col-sm-2 control-label">
                    {gettext("Destination")}
                </label>
                <div className="col-sm-10">
                    <Options id="dst_account"
                             className="form-control"
                             list={options}
                    />
                </div>
            </div>
            <div className="form-group">
                <label htmlFor="amount" className="col-sm-2 control-label">
                    {gettext("Amount")}
                </label>
                <div className="col-sm-10">
                    <div className="input-group">
                        {currency[0] &&
                            <div className="input-group-addon">{currency[0]}</div>
                        }
                        <input id="amount" type="text" required pattern="\d+([,.]\d*)?" placeholder="0.00"
                               className="form-control"/>
                        {currency[1] &&
                            <div className="input-group-addon">{currency[1]}</div>
                        }
                    </div>
                </div>
            </div>
            <div className="form-group">
                <label htmlFor="note" className="col-sm-2 control-label">
                    {gettext("Reason")}
                </label>
                <div className="col-sm-10">
                    <input id="note" type="text" required className="form-control"/>
                </div>
            </div>
            <div className="form-group">
                <label htmlFor="authentication" className="col-sm-2 control-label">
                    {gettext("Clerk code")}
                </label>
                <div className="col-sm-10">
                    <input id="authentication" type="password" required className="form-control"/>
                </div>
            </div>
            <div className="form-group">
                <div className="col-sm-4 col-sm-offset-2">
                    <button className="btn btn-primary" type="submit">{gettext("Verify…")}</button>
                    {" "}
                    <button className="btn btn-default" type="reset">{gettext("Reset")}</button>
                </div>
            </div>
        </form>
    )
}

function VerifyRow({head, value}) {
    return (
        <div className="row">
            <div className="col-sm-2">{head}</div>
            <div className="col-sm-10">{value}</div>
        </div>
    )
}

export function account_transfer_verify(data, onAccept) {
    const currency = CURRENCY.raw
    return Dialog({
        titleText: gettext("Verify transfer"),
        body: [
            <VerifyRow head={gettext("Source")} value={data.src_account_balance}/>,
            <VerifyRow head={gettext("Destination")} value={data.dst_account_balance}/>,
            <VerifyRow head={gettext("Amount")} value={currency[0] + data.total.formatCents() + currency[1]}/>,
            <VerifyRow head={gettext("Note")} value={data.note.text}/>,
            <VerifyRow head={gettext("Signature")} value={data.clerk.print + " @ " + data.counter}/>,
        ],
        buttons: [
            {text: gettext("Accept"), classes: "btn-success", click: onAccept},
            {text: gettext("Cancel"), classes: "btn-warning"},
        ]
    })
}

function transferRow(data) {
    const currency = CURRENCY.raw
    return (
        <tr>
            <td>{DateTimeFormatter.datetime(data.end_time)}</td>
            <td>{data.src_account}</td>
            <td>{data.dst_account}</td>
            <td className="stretch">{data.note.text}</td>
            <td>{currency[0] + data.total.formatCents() + currency[1]}</td>
            <td>{data.clerk.print + " @ " + data.counter}</td>
        </tr>
    )
}

export function account_transfers(data, onRefresh, title) {
    const refresh = (<button type="button" className="btn btn-default btn-xs" onclick={onRefresh}>
        <span className="glyphicon glyphicon-refresh">{" "}</span>
    </button>)
    let caption
    if (title === null) {
        caption = <caption>{refresh}</caption>
    } else {
        title = title === undefined ? gettext("Transfers") : title
        caption = (<caption>
            {title}
            {" "}
            {refresh}
        </caption>)
    }

    return (
        <table className="table table-condensed table-striped stretchy" id="account_transfers">
            <style>{`
table.stretchy :where(th, td):not(.stretch) {
  width: 0;
  white-space: nowrap;
}`}</style>
            {caption}
            <thead>
            <tr>
                <th>{gettext("Time")}</th>
                <th>{pgettext("From account", "From" )}</th>
                <th>{pgettext("To account", "To")}</th>
                <th className="stretch">{gettext("Note")}</th>
                <th>{gettext("Amount")}</th>
                <th>{gettext("Signature")}</th>
            </tr>
            </thead>
            <tbody>{
                data.map((e) => transferRow(e))
            }</tbody>
        </table>
    )
}
