class @CounterMode extends ItemCheckoutMode
  ModeSwitcher.registerEntryPoint("customer_checkout", @)

  constructor: (args..., modeArgs) ->
    super(args...)
    @_receipt = new ReceiptData()
    @receiptSum = new ReceiptSum()
    if modeArgs?
      @restoreReceipt(modeArgs)
    @receipt.body.attr("id", "counter_receipt")

  glyph: -> "euro"
  title: -> gettext("Checkout")
  commands: ->
    abort: ["abort", gettext("Abort receipt")]
    suspend: ["suspend", gettext("Suspend active receipt")]
    print: ["print", gettext("Print receipt / return")]

  actions: -> [
    [@commands.abort,                 @onAbortReceipt]
    [@commands.suspend,               @onSuspendReceipt]
    [@commands.print,                 @onPrintReceipt]
    [@commands.logout,                @onLogout]
    [@cfg.settings.payPrefix,         @onPayReceipt]
    [@cfg.settings.removeItemPrefix,  @onRemoveItem]
    ["",                              @onAddItem]
  ]

  _box_exp: /^(?:(\d+)\s*[*x.]\s*)?box\s*(\d+)$/

  _match_box_exp: (code) ->
    box_match = @_box_exp.exec(code)
    if box_match
      box_item_count = if box_match[1]? then Number.parseInt(box_match[1]) else null
      box_number = Number.parseInt(box_match[2])
      if Number.isNaN(box_item_count) or Number.isNaN(box_number)
        throw new Error("NaN")
      return (
        number: box_number
        item_count: box_item_count
        input: code
      )
    return null

  _create_box_arg: (box) ->
    r = box_number: box.number
    if box.item_count?
      r.box_item_count = box.item_count
    return r

  enter: ->
    @cfg.uiRef.body.append(@receiptSum.render())
    super
    @_setSum()

  addRow: (code, item, price, rounded=false) ->
    if code?
      @_receipt.rowCount++
      index = @_receipt.rowCount
      if price? and price < 0 then index = -index
    else
      code = ""
      index = ""

    row = @createRow(index, code, item, price, rounded)
    @receipt.body.prepend(row)
    if @_receipt.isActive()
      @_setSum(@_receipt.total)
    return row

  onAddItem: (code) =>
    code = code.trim()
    if code == "" then return

    box = @_match_box_exp(code)
    if box
      op = new BoxReservationOperation((result, args) =>
        if result == "ok"
          if not @_receipt.isActive()
            @startReceipt(null, args.requestBox)
          else
            @reserveItem(null, args.requestBox)
        else if result == "error"
          @_onInitialItemFailed(args.jqXHR, null, args.requestBox)
        else console.error("Invalid result code " + result + ": " + args)
      )
      op.start(box)

    else

      code = fixToUppercase(code)
      if not @_receipt.isActive()
        Api.item_find(code: code, available: true).then(
          () => @startReceipt(code)
          (jqXHR) => @_onInitialItemFailed(jqXHR, code)
        )
      else
        @reserveItem(code)

  showError: (status, text, code, box) =>
    switch status
      when 0 then errorMsg = gettext("Network disconnected!")
      when 404 then errorMsg =
        if code? then gettext("Item is not registered.") else gettext("Invalid box number.")
      when 409 then errorMsg = text
      when 423 then errorMsg = text
      else errorMsg = gettext("Error %s.").replace("%s", status)

    data = if code? then code else box.input
    safeAlert(errorMsg + ' ' + data)

  restoreReceipt: (receipt) ->
    @switcher.setMenuEnabled(false)
    Api.receipt_activate(id: receipt.id).then(
      (data) => @_startOldReceipt(data)
      () =>
        alert(gettext("Could not restore receipt!"))
        @switcher.setMenuEnabled(true)
    )

  _startOldReceipt: (data) ->
    throw "Still active receipt!" if @_receipt.isActive()

    @_receipt.start(data)
    @_receipt.total = data.total

    @receipt.body.empty()
    for item in data.items
      price = if item.action == "DEL" then -item.price else item.price
      remove = if item.action == "DEL" then true else false
      @_addRow(item, remove)
    @_setSum(@_receipt.total)

  _onInitialItemFailed: (jqXHR, code, box=null) =>   # TODO
    if jqXHR.status == 423
      # Locked. Is it suspended?
      if jqXHR.responseJSON? and jqXHR.responseJSON.receipt?
        receipt = jqXHR.responseJSON.receipt
        dialog = new Dialog()
        dialog.title.text(gettext("Continue suspended receipt?"))
        table = Template.receipt_info(receipt: receipt)
        dialog.body.append(table)
        dialog.addPositive().text(gettext("Continue")).click(() =>
          console.log("Continuing receipt #{receipt.id}")
          Api.receipt_continue(code: code).then((data) =>
            @_startOldReceipt(data)
          )
        )
        dialog.addNegative().text(gettext("Cancel"))
        dialog.show(
          keyboard: false
          backdrop: "static"
        )
        return
    # else:
    @showError(jqXHR.status, jqXHR.responseText, code, box)

  startReceipt: (code, box=null) ->
    @_receipt.start()

    # Changes to other modes now would result in fatal errors.
    @switcher.setMenuEnabled(false)

    Api.receipt_start().then(
      (data) =>
        @_receipt.data = data
        @receipt.body.empty()
        @_setSum()
        @reserveItem(code, box)

      (jqHXR) =>
        safeAlert("Could not start receipt! " + jqHXR.responseText)
        # Rollback.
        @_receipt.end()
        @switcher.setMenuEnabled(true)
        return true
    )

  _setSum: (sum=0, ret=null) ->
    sum_fmt = CURRENCY.raw[0] + (sum).formatCents() + CURRENCY.raw[1]
    if ret?
      text = dPrintF(gettext("Total: %t / Return: %r"),
        t: sum_fmt
        r: CURRENCY.raw[0] + (ret).formatCents() + CURRENCY.raw[1]
      )
    else
      text = gettext("Total: %t").replace("%t", sum_fmt)

    @receiptSum.set(text)
    @receiptSum.setEnabled(@_receipt.isActive())

  reserveItem: (code, box) ->
    if (!code? and !box?) or (code? and box?)
      throw Error("Invalid arguments")

    if code?
      Api.item_reserve(code: code).then(
        (data) =>
          if data._message?
            safeWarning(data._message)
          @_receipt.total += data.price

          if Math.abs(data.total - @_receipt.total) >= 1
            console.error("Inconsistency: " + @_receipt.total + " != " + data.total)

          @_addRow(data)
          @notifySuccess()

        (jqXHR) =>
          @showError(jqXHR.status, jqXHR.responseText, code)
          return true
      )

    else
      Api.box_item_reserve(
        @_create_box_arg(box)
      ).then(
        (data) =>
          @_receipt.total += data.items.reduce(
            (acc, cur) => acc + cur.price,
            0
          )

          if Math.abs(data.total - @_receipt.total) >= 1
            console.error("Inconsistency: " + @_receipt.total + " != " + data.total)

          for item in data.items
            box_item =
              box_number: data.box_number
              description: data.description
              price: item.price
            @_addRow(box_item)
          @notifySuccess()

        (jqXHR) =>
          @showError(jqXHR.status, jqXHR.responseText, code, box)
          return true
      )

  _addRow: (data, remove=false) =>
    price_multiplier = if remove then -1 else 1
    if data.box_number?
      @addRow("#" + data.box_number, data.description, data.price * price_multiplier)
    else
      @addRow(data.code, data.name, data.price * price_multiplier)

  onRemoveItem: (code) =>
    unless @_receipt.isActive() then return

    box = @_match_box_exp(code)
    if !box?

      code = fixToUppercase(code)
      Api.item_release(code: code).then(
        (data) =>
          @_receipt.total -= data.price

          if Math.abs(data.total - @_receipt.total) >= 1
            console.error("Inconsistency: " + @_receipt.total + " != " + data.total)

          @_addRow(data, true)
          @notifySuccess()

        (jqXHR) =>
          if jqXHR.status == 404
            safeAlert(gettext("Item not found on receipt: %s").replace("%s", code))
          else
            safeAlert(jqXHR.responseText)
          return true
      )

    else

      Api.box_item_release(
        @_create_box_arg(box)
      ).then(
        (data) =>
          @_receipt.total -= data.items.reduce(
            (acc, cur) => acc + cur.price,
            0
          )

          if Math.abs(data.total - @_receipt.total) >= 1
            console.error("Inconsistency: " + @_receipt.total + " != " + data.total)

          for item in data.items
            box_item =
              box_number: data.box_number
              description: data.description
              price: item.price
            @_addRow(box_item, true)
          @notifySuccess()

        (jqXHR) =>
          if jqXHR.status == 404
            safeAlert(gettext("Item not found on receipt: %s").replace("%s", code))
          else
            safeAlert(jqXHR.responseText)
          return true
      )


  onPayReceipt: (input) =>
    unless Number.isConvertible(input)
      unless input == @cfg.settings.quickPayExtra
        safeWarning("Number not understood. The format must be like: #{@cfg.settings.payPrefix}0.00")
        return
      else
        # Quick pay.
        input = @_receipt.total

    else
      # If decimal separator is supplied, ensure dot and expect euros.
      input = input.replace(",", ".")
      input = (input - 0) * 100

      # Round the number to integer just to be sure it is whole cents (and no parts of it).
      # This should differ maximum of epsilon from previous line.
      input = Math.round(input)

    if input < @_receipt.total
      safeAlert(gettext("Not enough given money!"))
      return

    if @cfg.settings.purchaseMax > 0 and input > @cfg.settings.purchaseMax * 100
      safeAlert(gettext("Not accepting THAT much money!"))
      return

    # Convert previous payment calculations from success -> info,muted
    @receipt.body.children(".receipt-ending").removeClass("success").addClass("info text-muted")

    # Add (new) payment calculation rows.
    return_amount = input - @_receipt.total
    row.addClass("success receipt-ending") for row in [
      @addRow(null, gettext("Subtotal"), @_receipt.total, true),
      @addRow(null, gettext("Cash"), input),
      @addRow(null, gettext("Return"), return_amount, true),
    ]

    # Also display the return amount in the top.
    @_setSum(@_receipt.total, return_amount.round5())

    # End receipt only if it has not been ended.
    unless @_receipt.isActive() then return
    Api.receipt_finish(id: @_receipt.data.id).then(
      (data) =>
        @_receipt.end(data)
        console.log(@_receipt)

        # Mode switching is safe to use again.
        @switcher.setMenuEnabled(true)
        @receiptSum.setEnabled(false)

      (jqXHR) =>
        safeAlert("Error ending receipt! " + jqXHR.responseText)
        return true
    )

  onAbortReceipt: =>
    unless @_receipt.isActive() then return

    Api.receipt_abort(id: @_receipt.data.id).then(
      (data) =>
        @_receipt.end(data)
        console.log(@_receipt)

        @addRow(null, gettext("Aborted"), null).addClass("danger")
        # Mode switching is safe to use again.
        @switcher.setMenuEnabled(true)
        @receiptSum.setEnabled(false)
        @notifySuccess()

      (jqXHR) =>
        safeAlert("Error ending receipt! " + jqXHR.responseText)
        return true
    )

  onSuspendReceipt: =>
    unless @_receipt.isActive() then return

    dialog = new Dialog()
    dialog.title.text(gettext("Suspend receipt?"))
    form = Template.receipt_suspend_form()
    dialog.body.append(form)

    success = dialog.addButton("success")
    success.text(gettext("Suspend")).click(() =>
      success.attr("disabled", "disabled")
      Api.receipt_suspend(note: $("#suspend_note", dialog.body).val()).then(
        (receipt) =>
          dialog.dismiss()
          @_receipt.end(receipt)

          @addRow(null, gettext("Suspended"), null).addClass("warning")
          @switcher.setMenuEnabled(true)
          @receiptSum.setEnabled(false)
          @notifySuccess()

        () =>
          success.removeAttr("disabled")
          safeAlert("Error suspending receipt!")
      )
    )
    dialog.addNegative().text(gettext("Cancel"))
    dialog.show()

  onPrintReceipt: =>
    unless @_receipt.data?
      safeAlert(gettext("No receipt to print!"))
      return
    else if @_receipt.isActive()
      safeAlert(gettext("Cannot print while receipt is active!"))
      return
    else unless @_receipt.isFinished()
      safeAlert(gettext("Cannot print. The receipt is not in finished state!"))
      return

    Api.receipt_get(id: @_receipt.data.id).then(
      (receipt) =>
        @switcher.switchTo( ReceiptPrintMode, receipt )

      () =>
        safeAlert(gettext("Error printing receipt!"))
        return true
    )

  onLogout: =>
    if @_receipt.isActive()
      safeAlert(gettext("Cannot logout while receipt is active!"))
      return

    super


# Class for holding in some some of receipt information.
# @private
class ReceiptData
  constructor: ->
    @start(null)
    @active = false

  isActive: -> @active
  isFinished: -> if @data? then @data.status == "FINI" else false
  start: (data=null) ->
    @active = true
    @rowCount = 0
    @total = 0
    @data = data

  end: (data=null) ->
    @active = false
    @data = data


class BoxReservationOperation
  constructor: (@listener) ->

  start: (requestBox) ->
    Api.box_find(box_number: requestBox.number).then(
      (box) => @_checkBoxSize(box, requestBox)
      (jqXHR) => @listener("error",
        jqXHR: jqXHR
        requestBox: requestBox
      )
    )

  _checkBoxSize: (box, requestBox) =>
    if box.bundle_size == 1
      @listener("ok",
        requestBox: requestBox
        box: box
      )
      return

    hasRequestCount = requestBox.item_count?
    requestCount = requestBox.item_count ? 1

    itemCount1 = box.bundle_size * requestCount
    if box.available < itemCount1
      warning1 = @_warningSignHtml
      bClass1 = "danger"
      title1 = gettext("No that many available items left.")
    else
      warning1 = ""
      bClass1 = "warning"
      title1 = ngettext("%i bundle", "%i bundles", requestCount).replace("%i", requestCount)

    itemCount2 = requestCount
    bundleCount = requestCount/box.bundle_size
    isBundleCountRounded = false
    if bundleCount != Math.round(bundleCount)
      warning2 = @_warningSignHtml
      bundleCount = Math.round(bundleCount * 100)/100  # TODO: use roundTo
      bClass2 = "danger"
      title2 = gettext("Incorrect amount of items to sell as bundle")
      isBundleCountRounded = true
    else if box.available < bundleCount
      warning2 = @_warningSignHtml
      bClass2 = "danger"
      title2 = gettext("No that many available items left.")
    else
      warning2 = ""
      bClass2 = "warning"
      title2 = ngettext("%i item", "%i items", requestCount).replace("%i", requestCount)

    dialog = new Dialog()
    dialog.title.text(gettext("Confirm box allocation"))
    table = Template.box_sell_allocation_dialog(
      item: box
      request: requestBox
      text:
        description: gettext("description")
        pricing: gettext("pricing")
        box_number: gettext("box number")
        bundle_size: ngettext("%i pc", "%i pcs", box.bundle_size).replace("%i", box.bundle_size)
    )
    dialog.body.append(table)

    btn1 = dialog.addDismissButton(bClass1).html(mPrintF(gettext("{warningIcon} <u>{bundles}</u> = {items} = {price}"),
      warningIcon: warning1
      bundles: ngettext("%i bundle", "%i bundles", requestCount).replace("%i", requestCount)
      items: ngettext("%i item", "%i items", itemCount1).replace("%i", itemCount1)
      price: displayPrice(requestCount * box.item_price)
    ).trim())
    btn1.attr("title", title1)
    if warning1
      btn1.attr("disabled", "disabled")
    else
      btn1.click(() =>
        @listener("ok",
          requestBox: requestBox
          box: box
        )
      )

    if hasRequestCount
      btn2 = dialog.addDismissButton(bClass2).html(mPrintF(gettext("{warningIcon} {bundles} = <u>{items}</u> = {price}"),
        warningIcon: warning2
        bundles: ngettext("%f bundle", "%f bundles", bundleCount).replace("%f", bundleCount)
        items: ngettext("%i item", "%i items", itemCount2).replace("%i", itemCount2)
        price: if isBundleCountRounded then "?" else displayPrice(bundleCount * box.item_price)
      ).trim())
      btn2.attr("title", title2)
      if warning2
        btn2.attr("disabled", "disabled")
      else
        btn2.click(() =>
          alteredBox = Object.assign({}, requestBox,
            item_count: bundleCount
          )
          @listener("ok",
            requestBox: alteredBox
            box: box
          )
        )

    dialog.addNegative().text(gettext("Cancel"))

    dialog.show(
      keyboard: false
      backdrop: "static"
    )

  _warningSignHtml: '<span class="glyphicon glyphicon-warning-sign"> </span>'
