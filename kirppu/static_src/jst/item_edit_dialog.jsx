import {Options, PriceField} from './form_fields.jsx';
import VendorInfo from './vendor_info.jsx';

function Header() {
    return (
        <div className="modal-header">
            <button className="close" data-dismiss="modal" aria-label={gettext("Close")}>
                <span aria-hidden="true">&times;</span>
            </button>
            <h4 className="modal-title">{gettext("Edit Item")}</h4>
        </div>
    )
}

function PriceList({itemPrices}) {
    if (itemPrices.length === 0 || itemPrices[0].state === "AD") {
        return <div/>
    }
    const unsold = itemPrices.filter((e) => e.state === "BR")
    const sold = itemPrices.filter((e) => e.state === "ST" || e.state === "SO" || e.state === "CO")
    const groups = unsold.concat(sold)
    const names = {
        BR: gettext("Unsold"),
        ST: gettext("Sold"),
        SO: gettext("Sold"),
        CO: gettext("Sold"),
    }
    return (
        <div>
            <label className="col-sm-2 control-label">{gettext("Price details")}</label>
            <div className="col-sm-8">
                <table className="table table-condensed">
                    <thead><tr><th>{gettext("State")}</th><th>{gettext("Count")}</th><th>{gettext("Price")}</th></tr></thead>
                    <tbody>{
                        groups.map((e) => <tr><td>{names[e.state]}</td><td>{e.count}</td><td>{displayPrice(e.price)}</td></tr>)
                    }</tbody>
                </table>
            </div>
        </div>
    )
}

function Form({CURRENCY, item_types, item_states, item}) {
    return (
        <form className="form-horizontal">
            <div className="form-group">
                <label htmlFor="item-edit-name-input"
                       className="col-sm-2 control-label">
                    {gettext("Name")}
                </label>
                <div className="col-sm-10">
                    <input id="item-edit-name-input"
                           type="text"
                           className="form-control"
                           value={item.name}
                           readOnly/>
                </div>
            </div>
            <div className="form-group">
                <label htmlFor="item-edit-code-input"
                       className="col-sm-2 control-label">
                    {gettext("Code")}
                </label>
                <div className="col-sm-3">
                    <input id="item-edit-code-input"
                           type="text"
                           className="form-control receipt-code"
                           value={item.code}
                           readOnly/>
                </div>
                {item.box && [
                    <label htmlFor="item-edit-boxnumber"
                           className="col-sm-3 control-label">
                        {gettext("Box number")}
                    </label>,
                    <div className="col-sm-2">
                        <input id="item-edit-boxnumber"
                               type="number"
                               className="form-control"
                               value={item.box.box_number}
                               readOnly/>
                    </div>
                ]}
            </div>
            <div className="form-group">
                <label className="col-sm-2 control-label">{gettext("Vendor")}</label>
                <div className="col-sm-10">
                    <VendorInfo vendor={item.vendor} title={false} />
                </div>
            </div>
            <div className="form-group">
                <div className="col-sm-10 col-sm-offset-2">
                    <div className="checkbox">
                        <label htmlFor="item-edit-price-confirm">
                            <input id="item-edit-price-confirm"
                                   type="checkbox"/>
                            {gettext("Vendor has requested a price change.") +
                            (item.box ? " " + gettext("Change will only affect unsold items.") : "")}
                        </label>
                    </div>
                </div>
            </div>
            <div className="form-group">
                <label htmlFor="item-edit-price-input"
                       className="col-sm-2 control-label">
                    {gettext("Price")}
                </label>
                <div className="col-sm-4">
                    <PriceField inputId="item-edit-price-input"
                        price_step="0.5" CURRENCY={CURRENCY} readOnly="true"/>
                </div>
            </div>
            {item.box && <PriceList className="form-group" itemPrices={item.box.item_prices} />}
            <div className="form-group">
                <label htmlFor="item-edit-type-input"
                       className="col-sm-2 control-label">
                    {gettext("Type")}
                </label>
                <div className="col-sm-10">
                    <Options id="item-edit-type-input"
                             className="form-control"
                             disabled
                             list={item_types}
                             selection={item.itemtype}
                    />
                </div>
            </div>
            <div className="form-group">
                <label htmlFor="item-edit-state-input"
                       className="col-sm-2 control-label">
                    State
                </label>
                <div className="col-sm-10">
                    <Options id="item-edit-state-input"
                             className="form-control"
                             disabled={item.box}
                             list={item_states}
                             selection={item.state}
                    />
                </div>
            </div>
            <div className="form-group">
                <label htmlFor="item-edit-abandoned-input"
                       className="col-sm-2 control-label">
                    {gettext("Abandoned")}
                </label>
                <div className="col-sm-10">
                    <label htmlFor="item-edit-abandoned-yes"
                           className="radio-inline">
                        <input id="item-edit-abandoned-yes"
                               name="item-edit-abandoned-input"
                               type="radio"
                               value="true"
                               checked={item.abandoned}
                               disabled/>
                        {gettext("Yes")}
                    </label>
                    <label htmlFor="item-edit-abandoned-no"
                           className="radio-inline">
                        <input id="item-edit-abandoned-no"
                               name="item-edit-abandoned-input"
                               type="radio"
                               value="false"
                               checked={!item.abandoned}
                               disabled/>
                        {gettext("No")}
                    </label>
                </div>
            </div>
        </form>
    )
}

function PrintFrame() {
    return (
        <iframe name="item-edit-print-frame" width="100%" height="100%" frameBorder="0" className="visible-print-block"
                srcDoc="
              <!doctype html>
              <html>
                <head>
                  <style>
                    button {
                      display: none !important;
                    }
                  </style>
                </head>
                <body>
                  <div id=&quot;body&quot; class=&quot;container&quot;>
                    <div id=&quot;items&quot;></div>
                  </div>
                </body>
              </html>
            "/>
    )
}


export function item_edit_dialog_modal() {
    return (
        <div className="modal fade">
            <div className="modal-dialog"/>
        </div>
    )
}

export function item_edit_dialog_content({CURRENCY, item_types, item_states, item, onPrint}) {
    return (
        <div className="modal-content">
            <Header/>
            <div className="modal-body">
                <div className="container-fluid">
                    <Form CURRENCY={CURRENCY} item_types={item_types} item_states={item_states} item={item}/>
                    <PrintFrame/>
                </div>
            </div>
            <div id="item-edit-error"
                 role="alert"
                 className="alert alert-danger alert-off"/>
            <div className="modal-footer">
                <button className="btn btn-default btn-minwidth"
                        data-dismiss="modal">
                    {gettext("Cancel")}
                </button>
                <button id="item-edit-print-button"
                        className="btn btn-primary btn-minwidth"
                        onclick={() => onPrint()}>
                    {gettext("Print")}
                </button>
                <button id="item-edit-save-button"
                        className="btn btn-primary btn-minwidth"
                        disabled>
                    {gettext("Save")}
                </button>
            </div>
        </div>
    )
}
