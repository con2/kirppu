class @ReceiptPrintMode extends CheckoutMode
  ModeSwitcher.registerEntryPoint("reports", @)

  @strTotal: gettext("Total")
  @strTitle: gettext("Receipt")
  @strTitleFind: gettext("Find receipt")
  @strSell: pgettext("%d is date and time of the receipt, %e is event name, %i is receipt id", "%d, receipt %i, %e")

  constructor: (cfg, switcher, receiptData) ->
    super
    @hasReceipt = receiptData?
    @receipt = new PrintReceiptTable()
    @initialReceipt = receiptData

  enter: ->
    super
    @cfg.uiRef.body.append(@receipt.table)
    if @initialReceipt?
      @renderReceipt(@initialReceipt)
      window.print()
    return

  glyph: -> "list-alt"
  title: -> if not @hasReceipt then @constructor.strTitleFind else @constructor.strTitle
  subtitle: -> ""
  commands: ->
    print: ["print", gettext("Print receipt / return")]

  actions: -> [
    ["", @findReceipt]
    [@commands.logout, @onLogout]
    [@commands.print, @onReturnToCounter]
  ]

  findReceipt: (code) =>
    Api.receipt_get(item: code).then(
      (data) =>
        @renderReceipt(data)
        @switcher.setPrintable()
        @notifySuccess()
      () =>
        @receipt.body.empty()
        @switcher.setPrintable(false)
        safeAlert("Item not found in receipt!")
    )

  renderReceipt: (receiptData) ->
    @receipt.body.empty()
    for item in receiptData.items
      if item.action != "ADD"
        continue
      if item.box_number?
        code = "#" + item.box_number
      else
        code = item.code
      row = PrintReceiptTable.createRow(item.vendor, code, item.name, item.price, false)
      @receipt.body.append(row)

    sellStr = dPrintF(@constructor.strSell,
      d: DateTimeFormatter.datetime(receiptData.end_time)
      e: receiptData.event
      i: receiptData.id
    )

    @receipt.body.append(row) for row in [
      PrintReceiptTable.joinedLine()
      PrintReceiptTable.createRow("", "", @constructor.strTotal, receiptData.total, true)
      PrintReceiptTable.joinedLine(sellStr)
    ]
    @receipt.body.append(PrintReceiptTable.joinedLine(row)) for row in receiptData.tail

    @hasReceipt = true
    @switcher.updateHead()
    return


  onReturnToCounter: =>
    @switcher.switchTo(CounterMode)
