import ResultTable from "./result_table.jsx";

export default function counter_list({counters}) {
    return (
        <ResultTable
            heading={gettext("Available counters")}
            body={counters.map((e) => <tr><td>{e}</td></tr>)}
            />
    )
}
