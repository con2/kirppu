export function account_table(initialData, currency) {
    return (
        <table className="table table-striped">
            <thead>
            <tr>
                <th>{gettext("Account")}</th>
                <th>{gettext("Balance")}</th>
            </tr>
            </thead>
            <tbody>
            {initialData.map((e) => {
                return (
                    <tr id={"id_" + e.id}>
                        <td>{e.name}</td>
                        <td className="balance">{currency(e.balance_cents)}</td>
                    </tr>
                )
            })}
            </tbody>
        </table>
    )
}
