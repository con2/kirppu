function handleModeMenu(event) {
    const menu = $("#modeMenu > a");
    const wasExpanded = menu.attr("aria-expanded") === "true";
    let handled = false;
    if (event.code === "F2") {
        menu.click();
        if (wasExpanded) $("#code_input").focus();
        handled = true;
    } else if (wasExpanded && /^Digit\d$/.exec(event.code)) {
        const digit = Number.parseInt(event.code[5]);
        const options = $("#modeMenu li");
        if (digit >= 1 && digit <= options.length) {
            $(options.get(digit - 1)).find("a").click();
            handled = true;
        }
    }
    return handled
}
