/**
 * @typedef {Object} OptionsListItem
 * @property {String} name
 * @property {String} description
 */

/**
 * @param {Object} obj
 * @param {OptionsListItem[]} obj.list Options to show.
 * @param {boolean} obj.multiple Allow multiple selections?
 * @param {String} obj.selection Currently selected `.name`.
 **/
export function Options({list, multiple, selection}) {
    // multiple must be set here, otherwise the control will half-select first item by default.
    return (
        <select multiple={multiple} className="form-control">{
            list.map(t => {
                return <option value={t.name} selected={t.name === selection}>{t.description}</option>
            })
        }</select>
    )
}


export function PriceField({inputId, price_step, CURRENCY, readOnly, placeholder}) {
    // If overridden, className must contain input-group
    return (
        <div className="input-group">
            {CURRENCY[0] && <span className="input-group-addon">{CURRENCY[0]}</span>}
            <input type="number" step={price_step} min="0" id={inputId} className="form-control" readOnly={readOnly} placeholder={placeholder}/>
            {CURRENCY[1] && <span className="input-group-addon">{CURRENCY[1]}</span>}
        </div>
    )
}
