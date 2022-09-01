export default function render({
    onCompensate,
    onReturn,
    onAbandon,
    onShowCompensations,
    onCreateMobileCode
}) {
    return (
        <form className="hidden-print" id="vendor_report_buttons">
            <input type="button" className="btn btn-primary"
                   value={gettext('Balance Reconciliation…')}
                   onclick={onCompensate}
            />
            {" "}
            <input type="button" className="btn btn-primary"
                   value={gettext('Return Items…')}
                   onclick={onReturn}
            />
            {" "}
            <input type="button" className="btn btn-primary"
                   value={gettext('Abandon All Items Currently On Display…')}
                   onclick={onAbandon}
            />
            {" "}
            <input type="button" className="btn btn-default"
                   value={gettext('Compensation receipts…')}
                   onclick={onShowCompensations}
            />
            {" "}
            <input type="button" className="btn btn-default"
                   value={gettext('Mobile code…')}
                   onclick={onCreateMobileCode}
            />
        </form>
    )
}
