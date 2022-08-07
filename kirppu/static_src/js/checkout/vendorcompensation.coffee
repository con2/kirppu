class @VendorCompensation extends CheckoutMode

  constructor: (cfg, switcher, vendor) ->
    super(cfg, switcher)
    @vendor = vendor

  title: -> gettext("Vendor Compensation")

  enter: ->
    super
    @cfg.uiRef.codeForm.hide()
    @switcher.setMenuEnabled(false)
    @cfg.uiRef.body.append(Template.vendor_info(vendor: @vendor))

    @buttonForm = $('<form class="hidden-print">').append(@buttons(abort: true))
    @cfg.uiRef.body.append(@buttonForm)

    @itemDiv = $('<div>')
    @cfg.uiRef.body.append(@itemDiv)

    Api.compensable_items(vendor: @vendor.id)
      .done(@onGotItems)
      .fail((jqXHR) =>
        safeAlert("Request error: #{jqXHR.status}: #{jqXHR.responseText}")
      )

  exit: ->
    @cfg.uiRef.codeForm.show()
    @switcher.setMenuEnabled(true)
    super

  buttons: (cfg) ->
    t = @
    cbs =
      onConfirm: if cfg.confirm then t.onConfirm
      onAbort: if cfg.abort then t.onCancel
      onContinue: if cfg.continue then t.onCancel else (if cfg.skip then t.onSkipFailed)
      continueWarn: if cfg.skip or cfg.warn then true
      onRetry: if cfg.retry then t.onRetryFailed
    Template.vendor_compensation_buttons(cbs)

  onGotItems: (items) =>
    @compensableItems = items.items
    @compensableExtras = items.extras

    rows = @compensableItems.slice()
    compensableSum = @compensableItems.reduce(((acc, item) -> acc + item.price), 0)
    @provisionAmount = 0
    if @compensableExtras?
      rows.push(
        action: "EXTRA"
        type: "SUB"
        type_display: gettext("Subtotal")
        value: compensableSum
      )
      rows = rows.concat(@compensableExtras)
      for i in @compensableExtras
        @provisionAmount += i.value


    if rows.length > 0
      total = compensableSum + @provisionAmount
      table = Template.item_report_table(
        caption: if total >= 0 then gettext("Sold Items") else gettext("Balance Reconciliation")
        items: rows
        sum: total
        extra_col: true
      )
      @itemDiv.empty().append(table)
      @buttonForm.empty().append(@buttons(confirm: true, abort: true, warn: total < 0))

    else
      @itemDiv.empty().append($('<em>').text(gettext('No compensable items')))
      @buttonForm.empty().append(@buttons(continue: true))

  onCancel: => @switcher.switchTo(VendorReport, @vendor)

  onConfirm: =>
    nItems = @compensableItems.length
    if nItems == 0 and @provisionAmount == 0
      console.error("What? Nothing to compensate?")
      return
    @_createProgress(Math.max(nItems, 1))

    # Add table row indices for items (needed to point to the rows at UI).
    for i, index in @compensableItems
      i.row_index = index + 1

    Api.item_compensate_start(vendor: @vendor.id)
      .done(=>
        @_loopResult = []
        if nItems > 0
          @_loopBack(@compensableItems)
        else
          @_setProgress(1)
          @_onLoopDone()
      )
      .fail((jqXHR) =>
        safeAlert("Failed to start compensation: #{jqXHR.status}: #{jqXHR.responseText}")
      )


  _createProgress: (max) ->
    @buttonForm.empty().append(Template.progress_bar({
      max: max
    }))
    @_progressMax = max
    @_progress = @buttonForm.find(".progress-bar")

  _setProgress: (progress) ->
    @_progress[0].style.width = Math.round(progress * 100 / @_progressMax) + "%"
    @_progress.attr("aria-valuenow", progress)

  _addFailedItem: (jqXHR, item) =>
    item.error =
      status: jqXHR.status
      text: jqXHR.responseText
    @_loopResult.push(item)

  # Compensate items by looping over the list of items.
  # Failed items are added to @_loopResult thus it must be set to empty Array before calling this.
  # The failed items can then be tried again with this function. Note, that @_loopResult must be
  # cleared for retry also!
  #
  # @param list [Array] List of Items to compensate.
  # @param index [Integer, optional] Current index. Must be 0 when calling from outside this function.
  _loopBack: (list, index=0) =>
    item = list[index]
    status = $(".table_row_#{item.row_index} > .receipt_extra_col", @itemDiv)
    status.html('<span class="glyphicon glyphicon-repeat spinner text-info"></span>')

    cb = (glyph, color) => () =>
      status.html("<span class=\"glyphicon glyphicon-#{glyph} text-#{color}\"></span>")
      @_setProgress(index + 1)
      if index + 1 < list.length
        @_loopBack(list, index + 1)
      else
        @_onLoopDone()

    # Compensate an item. When successful, set the item state. If failure, add it to list of failed items.
    if item.code
      req = Api.item_compensate(code: item.code)
    else
      req = Api.box_item_compensate(
        pk: item.pk
        box_code: item.box_code
      )
    req
      .done(() => item.state = ItemState.compensated)
      .done(cb("ok", "success"))
      .fail((jqXHR) => @_addFailedItem(jqXHR, item))
      .fail(cb("remove", "danger"))

  # Looping done, choose next action.
  _onLoopDone: () =>
    if @_loopResult.length > 0
      # Some items failed. Give options to retry or continue/skip.
      @buttonForm.append(@buttons(retry: true, skip: true))
      errorList = $("<ul>")
      for item in @_loopResult
        text = item.error.text
        text = text.substr(0, 99) + if (text.length >= 100) then "…" else ""
        item = $("<li>").text("Row #{item.row_index} - #{item.code}: HTTP #{item.error.status}: #{text}")
        errorList.append(item)
      safeAlert(errorList)
    else
      # All success. Continue to compensation view.
      safeAlertOff()
      setTimeout((=> @onCompensated()), 1000)

  # Start new compensation loop over failed items.
  onRetryFailed: =>
    nItems = @_loopResult.length
    if nItems == 0
      console.error("What? Nothing to retry?")
      return
    @_createProgress(nItems)

    list = @_loopResult
    @_loopResult = []
    @_loopBack(list)

  # Skip failed items and proceed to compensation with only the successful items.
  onSkipFailed: =>
    r = confirm(gettext("Failed items will not be compensated. Check report for updated sum. Are you sure to skip failed items?"))
    if r
      safeAlertOff()
      @onCompensated()

  onCompensated: ->
    @switcher.setPrintable()

    # Create list of succeeded i.e. compensated items.
    items = []
    for item in @compensableItems
      if item.state == ItemState.compensated
        items.push(item)

    if @compensableExtras
      adjust = @compensableExtras.reduce(((acc, item) -> acc + item.value), 0)
    else
      adjust = 0
    @compensableItems = []

    sum = items.reduce(((acc, item) -> acc + item.price), 0) + adjust

    Api.item_compensate_end()
      .done((receiptCopy) =>
        if receiptCopy.total != sum
          safeAlert("Totals do not match: server said #{displayPrice(receiptCopy.total)}, below is #{displayPrice(sum)}")
          @buttonForm.empty().append(@buttons(continue: true))
        else
          @switcher.switchTo(CompensationReceipt, @vendor, receiptCopy.id, true)
      )
      .fail((jqXHR) =>
        safeAlert("Receipt ending failed! #{jqXHR.status}: #{jqXHR.responseText}")
      )
