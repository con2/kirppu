import {html} from './helpers';
import {Options, PriceField} from './form_fields.jsx';

export default function render({item_types, item_states, price_step, CURRENCY}) {
    return (
        <form role="form" className="form-horizontal item-search-form">
            <style>
                {"form.item-search-form select { height: 9.5em; }"}
            </style>
            <div className="form-group">
                <label htmlFor="item_search_input" className="control-label col-sm-2">{gettext("Name / Bar code")}</label>
                <div className="input-group col-sm-10">
                    <input type="text" id="item_search_input" className="form-control"/>
                </div>
            </div>
            <div className="form-group">
                <label htmlFor="item_code_search_input"
                       className="control-label col-sm-2">{gettext("Bar code part")}</label>
                <div className="input-group col-sm-10">
                    <input type="text" id="item_code_search_input" className="form-control"/>
                </div>
            </div>
            <div className="form-group">
                <label htmlFor="vendor_search_input" className="control-label col-sm-2">{gettext("Vendor ID")}</label>
                <div className="input-group col-sm-2">
                    <input type="number" step="1" min="1" id="vendor_search_input" className="form-control"/>
                </div>
            </div>
            <div className="form-group form-inline">
                <label htmlFor="item_search_min_price"
                       className="control-label col-sm-2">{gettext("Price")}</label>
                <PriceField inputId="item_search_min_price" className="input-group col-sm-2" price_step={price_step} CURRENCY={CURRENCY} placeholder={gettext("Min")}/>
                {" - "}
                <PriceField inputId="item_search_max_price" className="input-group col-sm-2" price_step={price_step} CURRENCY={CURRENCY} placeholder={gettext("Max")}/>
            </div>
            <div className="form-group">
                <label htmlFor="item_search_type" className="control-label col-sm-2">{gettext("Type")}</label>
                <div className="input-group col-sm-10">
                    <Options multiple id="item_search_type" list={item_types}/>
                    <span
                        className="help-block">{html(gettext("To select/deselect multiple values, press <kbd>Ctrl</kbd>, <kbd>Command</kbd> or <kbd>Shift</kbd> keys while clicking items."))}</span>
                </div>
            </div>
            <div className="form-group">
                <label htmlFor="item_search_state" className="control-label col-sm-2">{gettext("State")}</label>
                <div className="input-group col-sm-10">
                    <Options multiple id="item_search_state" list={item_states}/>
                    <span
                        className="help-block">{html(gettext("To select/deselect multiple values, press <kbd>Ctrl</kbd>, <kbd>Command</kbd> or <kbd>Shift</kbd> keys while clicking items."))}</span>
                </div>
            </div>
            <div className="form-group">
                <label className="control-label col-sm-2">{gettext("Is a box?")}</label>
                <label className="radio-inline">
                    <input type="radio" id="show_box_na" name="is_box" value="" checked="checked"/>{gettext("Don't care")}
                </label>
                <label className="radio-inline">
                    <input type="radio" name="is_box" value="yes"/>{gettext("Is a box")}
                </label>
                <label className="radio-inline">
                    <input type="radio" name="is_box" value="no"/>{gettext("Is a regular item")}
                </label>
            </div>
            <div className="form-group">
                <div className="input-group col-sm-offset-2 col-sm-10">
                    <div className="checkbox">
                        <label>
                            <input type="checkbox" id="show_hidden_items"/>
                            {gettext("Show hidden items")}
                        </label>
                    </div>
                </div>
            </div>
            <div className="col-sm-offset-2">
                <button type="submit" className="btn btn-primary btn-minwidth">{gettext("Search")}</button>
                {" "}
                <button type="reset" className="btn btn-default btn-minwidth">{gettext("Reset")}</button>
            </div>
        </form>
    )
}
