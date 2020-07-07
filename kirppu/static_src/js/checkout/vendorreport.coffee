@ItemState = (Object.freeze ? (x) -> x)(
  advertized: "AD"
  brought: "BR"
  staged: "ST"
  sold: "SO"
  missing: "MI"
  returned: "RE"
  compensated: "CO"
)

class Table
  @create: (opts) ->
    freeze = (Object.freeze ? (x) -> x)
    states = {}
    for state in opts.states
      states[state] = true
    opts.states = freeze states
    opts.untrustedValue ||= false
    opts.hidden ||= false
    opts = freeze opts
    t = new Table(opts)
    t.states = opts.states
    t.hidden = opts.hidden
    t.untrustedValue = opts.untrustedValue
    freeze t

  constructor: (@_opts) ->
  title: -> @_opts.title()
  filter: (list) ->
    if @_opts.filter
      (i for i in list when @_opts.filter(i))
    else
      (i for i in list when @_opts.states[i.state]?)


tables =
  compensable: Table.create
    states: [ItemState.sold]
    untrustedValue: true
    title: -> gettext('Compensable Items')
  returnable: Table.create
    states: [ItemState.brought]
    title: -> gettext('Returnable Items')
  other: Table.create
    states: [ItemState.missing, ItemState.returned, ItemState.compensated, ItemState.staged]
    title: -> gettext('Other Items')
  registered: Table.create
    states: [ItemState.advertized]
    title: -> gettext('Not brought to event')
    hidden: true
    filter: (i) -> @states[i.state]? and not i.hidden
  deleted: Table.create
    states: [ItemState.advertized]
    title: -> gettext('Deleted')
    hidden: true
    filter: (i) -> @states[i.state]? and i.hidden


class @VendorReport extends CheckoutMode
  constructor: (cfg, switcher, vendor) ->
    super(cfg, switcher)
    @vendor = vendor

  title: -> gettext("Item Report")
  inputPlaceholder: -> gettext("Search terms separated by space")

  actions: -> [
    ["", (query) => @switcher.switchTo(VendorFindMode, query)]
    [@commands.logout, @onLogout]
  ]

  enter: ->
    super
    @cfg.uiRef.body.append(Template.vendor_info(vendor: @vendor))
    buttons = Template.vendor_report_buttons(
      onCompensate: @onCompensate,
      onReturn: @onReturn,
      onAbandon: @onAbandon,
      onShowCompensations: @onShowCompensations,
      onCreateMobileCode: @onCreateMobileCode
    )
    $("input", buttons).attr("disabled", "disabled")
    @cfg.uiRef.body.append(buttons)

    Api.item_list(
      vendor: @vendor.id
    ).done((items) =>
      Api.box_list(
        vendor: @vendor.id
      ).done((boxes) =>
        Api.receipt_compensated(
          vendor: @vendor.id
        ).done((compensations) =>
          $("input", buttons).removeAttr("disabled")
          @onGotItems(items, boxes, compensations)
        )
      )
    )

  onGotItems: (items, boxes, compensations) =>
    @switcher.setPrintable()

    @_compensations = compensations

    for table_name, table of tables
      matchingItems = table.filter(items)

      rendered_table = Template.vendor_report_item_table(
         id: table_name
         caption: table.title()
         items: matchingItems
         sum: matchingItems.reduce(((acc, item) -> acc + item.price), 0)
         hidePrint: table.hidden
         isExpectedSum: table.untrustedValue
      )
      @cfg.uiRef.body.append(rendered_table)

    if boxes.length > 0
      sum =
        sold: 0
        compensated: 0
      count =
        brought: 0
        sold: 0
        compensated: 0
        returnable: 0

      for box in boxes
        count.brought += box.items_brought_total
        count.returnable += box.items_returnable
        for unit_price of box.counts
          detail = box.counts[unit_price]

          count.sold += detail.items_sold
          sum.sold += detail.items_sold * unit_price

          count.compensated += detail.items_compensated
          sum.compensated += detail.items_compensated * unit_price

      rendered_table = Template.box_report_table(
        caption: gettext("Boxes")
        items: boxes
        counts: count
        sums: sum
        hideSumInPrint: true
      )

      # Insert box list before Not Brought list.
      @cfg.uiRef.body.find("table#registered").before(rendered_table)
    return

  onCompensate: => @switcher.switchTo(VendorCompensation, @vendor)
  onReturn: =>     @switcher.switchTo(VendorCheckoutMode, @vendor)
  onAbandon: =>
    r = confirm(gettext("1) Have you asked for the vendor's signature AND 2) Are you sure you want to mark all items on display or missing abandoned?"))
    if r
      Api.items_abandon(
        vendor: @vendor.id
      ).done(=> @switcher.switchTo(VendorReport, @vendor))
    return

  onShowCompensations: =>
    dlg = new Dialog()
    dlg.title.text(gettext("Compensation receipts"))

    # TODO: customized Dialog class for listing things?
    table = $ Template.receipt_list_table_compensations(
      items: @_compensations
    )

    dlg.addNegative().text(gettext("Close")).addClass("btn-primary")
    buttonPositive = dlg.addPositive().text(gettext("Show"))

    $("tbody tr", table).click(() ->
      table.find(".success").removeClass("success")
      $(this).addClass("success")
      dlg.setEnabled(buttonPositive)
    )

    buttonPositive.click(() =>
      selected = $("tbody", table).find(".success")
      index = selected.data("index")
      selected_id = selected.data("id")
      receipt_id = @_compensations[index].id
      if receipt_id != selected_id
        throw new "ID mismatch!"
      @switcher.switchTo(CompensationReceipt, @vendor, receipt_id)
    )

    dlg.setEnabled(buttonPositive, false)

    dlg.body.append(table)
    dlg.show()

  onCreateMobileCode: =>
    dlg = new Dialog()
    dlg.title.text(gettext("Mobile code"))

    buttonClose = dlg.addNegative().text(gettext("Close"))
    buttonCreate = dlg.addButton("warning").text(gettext("Create new code"))

    codeDisplay = $("<div>").addClass("short-code-display")
    bodyText = $("<p>").text(gettext("Creating a code will invalidate all old codes."))

    body = $("<div>")
    body.append(bodyText, codeDisplay)

    buttonCreate.click(() =>
      dlg.setEnabled(buttonCreate, false)
      dlg.setEnabled(buttonClose, false)
      Api.vendor_token_create(
        vendor_id: @vendor.id
      ).then(
        (data) =>
          codeDisplay.text(data.code)
          setTimeout(
            () => dlg.setEnabled(buttonClose),
            2000)

        (jqXHR) =>
          dlg.setEnabled(buttonCreate)
          dlg.setEnabled(buttonClose)
          bodyText.text(jqXHR.responseText)
      )
    )

    dlg.body.append(body)
    dlg.show()
