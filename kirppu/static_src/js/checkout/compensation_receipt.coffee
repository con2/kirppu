class @CompensationReceipt extends CheckoutMode

  constructor: (cfg, switcher, vendor, receipt_id, from_compensation=false) ->
    super(cfg, switcher)
    @vendor = vendor
    @receipt_id = receipt_id
    @_from_compensation = from_compensation
    if typeof(receipt_id) != "number"
      throw new TypeError

  title: -> if @_from_compensation then gettext("Vendor Compensation") else gettext("Compensation Receipt")

  enter: ->
    super
    @cfg.uiRef.codeForm.hide()
    @cfg.uiRef.body.append(Template.vendor_info(vendor: @vendor))

    @buttonForm = $('<form class="hidden-print">').append(@continueButton())
    @cfg.uiRef.body.append(@buttonForm)

    @itemDiv = $('<div>')
    @cfg.uiRef.body.append(@itemDiv)

    Api.receipt_get(
      id: @receipt_id
      type: "compensation"
    ).done(@onGotReceipt)

  continueButton: (type="primary") =>
    $('<input type="button" class="btn btn-' + type + '">')
      .attr('value', gettext('Continue'))
      .click(@onDone)

  exit: ->
    @cfg.uiRef.codeForm.show()
    @switcher.setMenuEnabled(true)
    super

  onGotReceipt: (receipt) =>
    @switcher.setPrintable()

    # TODO: Add subtotal if receipt.extras

    table = Template.item_report_table(
      caption: gettext("Compensated Items")
      items: receipt.items
      sum: receipt.total
      hide_status: true
      time: receipt.end_time
    )
    @itemDiv.empty().append(table)

  onDone: =>
    @switcher.switchTo(VendorReport, @vendor)
