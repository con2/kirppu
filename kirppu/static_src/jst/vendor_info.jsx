import {dateTime} from "./helpers";

function Row({title, value, classes}) {
    return (
        <div className={"row " + (classes || "")}>
            <div className="col-xs-3 vendor-info-key">{title}</div>
            <div className="col-xs-9">{value}</div>
        </div>
    )
}

export default function render({vendor, title=true}) {
    return (
        <div className="vendor-info-box">
            {title && <h3 className="hidden-print">{gettext("Vendor")}</h3>}
            <Row title={gettext("name")} value={vendor.name}/>
            <Row title={gettext("email")} value={vendor.email} classes="hidden-print"/>
            <Row title={gettext("phone")} value={vendor.phone} classes="hidden-print"/>
            <Row title={gettext("id")} value={vendor.id}/>
            <Row title={gettext("terms accepted?")} value={
                vendor.terms_accepted ? dateTime(vendor.terms_accepted) : ""
            }/>
        </div>
    )
}
