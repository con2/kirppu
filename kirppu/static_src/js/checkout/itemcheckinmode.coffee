class @ItemCheckInMode extends ItemCheckoutMode
  ModeSwitcher.registerEntryPoint("vendor_check_in", @)

  glyph: -> "import"
  title: -> gettext("Vendor Check-In")

  constructor: (args..., query) ->
    super
    @currentVendor = null
    @itemIndex = 1

  actions: -> [
    ['', (code) =>
      return if code.trim() == ""
      code = fixToUppercase(code)
      @_checkinItem(code)
    ]
    [@commands.logout, @onLogout]
  ]

  exit: ->
    @cfg.uiRef.codeFormMessage.text("")
    @cfg.uiRef.codeFormMessage.parent().addClass("hidden")

  _checkinItem: (code) =>
    Api.item_checkin(
      code: code
      vendor: @currentVendor
    ).then(@onResultSuccess, @onResultError)

  onResultSuccess: (data, _, jqXHR) =>
    if data.vendor != @currentVendor
      @currentVendor = data.vendor
      Api.vendor_get(id: @currentVendor).done((vendor) =>
        if vendor.missing_name or !vendor.email or !vendor.phone
          # Insufficient info. Show question.
          # Shall either reset currentVendor or call _checkinItem again.
          @_vendorDialog(data, vendor)
        else
          # All ok. Add new vendor info and item checkin info.
          vendorInfoRow = $('<tr><td colspan="4">')
          $('td', vendorInfoRow).append(Template.vendor_info(vendor: vendor))
          @receipt.body.prepend(vendorInfoRow)
          @_onAddItem(data, jqXHR.status)
      ).fail(@onResultError)
    else
      @_onAddItem(data, jqXHR.status)

  onResultError: (jqXHR) =>
    if jqXHR.status == 404
      safeAlert(gettext("No such item"))
      return
    safeAlert(gettext("Error: %s").replace("%s", jqXHR.responseText))
    return true

  _onAddItem: (data, status, in_box=false) =>
    if status == 200
      if data._item_limit_left?
        @cfg.uiRef.codeFormMessage.parent().removeClass("hidden")
        @cfg.uiRef.codeFormMessage.text(gettext("%s left in item quota").replace("%s", data._item_limit_left))

      if data.box?
        countText = if data.box.bundle_size > 1 then gettext("Box bundle count: %d") else gettext("Box item count: %d")
        row = @createRow(@itemIndex,
          dPrintF(gettext("no. %d"), d: data.box.box_number),
          dPrintF(countText, d: data.box.item_count),
          "")
        @receipt.body.prepend(row)
        row = @createRow(@itemIndex++, data.code, data.box.description,
          dPrintF(gettext("á %s"), s: displayPrice(data.box.item_price)))
        @receipt.body.prepend(row)

      else
        row = @createRow(@itemIndex++, data.code, data.name, data.price)
        @receipt.body.prepend(row)
      @notifySuccess()

    else if status == 202 and not in_box
      @_boxDialog(data)

    else
      safeAlert("Invalid program state: %s".replace("%s", status))


  _boxDialog: (data) =>
    # Accepted, but not done.
    bundle_size = data.box.bundle_size
    body = $ Template.box_check_in_dialog(
      item: data
      text:
        description: gettext("description")
        code: gettext("code")
        count: if bundle_size > 1 then gettext("count of bundles") \
          else pgettext("count of items", "items in the box")
        box_number: gettext("box number")
        pricing: gettext("pricing")
        bundle_size: if bundle_size > 1 then ngettext("%i pc", "%i pcs", bundle_size).replace("%i", bundle_size) \
          else ""
    )

    dlg = new Dialog2(
      titleText: gettext("Mark the box number")
      body: body
      buttons: [
        {text: gettext("Cancel"), classes: "btn-default"},
        {text: gettext("Accept"), classes: "btn-primary", click: =>
          Api.box_checkin(
            code: data.code
            box_info: data.box.box_number
          ).then(
            (data2, _, jqXHR) => @_onAddItem(data2, jqXHR.status, true)
          , @onResultError)
        }
      ]
    )

    dlg.show()

  _vendorDialog: (item, vendor) =>
    # Vendor info problem. Confirm.
    body = $ Template.vendor_info(vendor: vendor)
    item_info = $("<div>").text(item.code + " " + item.name)
    tail = $("<div>")
      .text(gettext("Vendor might not be identifiable from information above."))
      .addClass("alert alert-info")

    dlg = new Dialog2(
      titleText: gettext("Insufficient vendor info")
      body: [body, item_info, tail]
      buttons: [
        {text: gettext("Cancel"), classes: "btn-default", click: => @currentVendor = null},
        {text: gettext("Accept"), classes: "btn-primary", click: => @_checkinItem(item.code)},
      ]
    )

    safeWarning(null, true, true)
    dlg.show()
