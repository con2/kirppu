class @ItemEditDialog

  @priceTagCss = []

  constructor: (item, action) ->
    @item = item
    @action = action

    @dialog = $(Template.item_edit_dialog_modal())
    @dialog.on('shown.bs.modal', => do @onShown)
    @dialog.on('hidden.bs.modal', => do @onHidden)
    @setItem(item)

  setItem: (item) =>
    dialog = $(Template.item_edit_dialog_content(
      CURRENCY: CURRENCY.raw
      item_types: ItemSearchForm.itemtypes
      item_states: ItemSearchForm.itemstates
      item: item
      onPrint: @onPrint
    ))
    @dialog.find(".modal-dialog").empty().append(dialog)

    @form = dialog.find("form")[0]
    @priceInput = dialog.find('#item-edit-price-input')
    @priceConfirm = dialog.find('#item-edit-price-confirm')
    @errorDiv = dialog.find('#item-edit-error')
    @saveButton = dialog.find('#item-edit-save-button')

    @priceConfirm.change(=>
      if @priceConfirm.prop('checked')
        @priceInput.prop('readonly', false)
      else
        @priceInput.val(@item.price.formatCents())
        @priceInput.prop('readonly', true)
    )

    dialog.find('input').change(@onChange).on("keyup", @onChange)
    dialog.find('select').change(@onChange)

    @priceTag = $('.item_template').clone()
      .removeClass('item_template')
      .addClass('item_short')

    @saveButton.click(@onSave)

    @item = item

    do @updatePriceTag

    @priceInput.val(item.price.formatCents())

    @priceConfirm.prop('checked', false)
    @priceConfirm.change()
    @saveButton.prop('disabled', true)

    # Ensure we have any value for all required fields.
    @getFormState()
    return

  updatePriceTag: =>
    item = @item
    tag = @priceTag
    tag.find('.item_name').text(item.name)
    tag.find('.item_price').text(item.price.formatCents())
    tag.find('.item_head_price').text(item.price.formatCents())
    tag.find('.item_adult_tag').text(if item.adult then 'K-18' else '')
    tag.find('.item_vendor_id').text(item.vendor.id)
    tag.find('.item_extra_code').text(item.code)
    Api.get_barcodes(codes: JSON.stringify(item.code)).done((codes) ->
      tag.find('.barcode_container > img').attr('src', codes[0])
    )

  show: => @dialog.modal(keyboard: false)

  hide: => @dialog.modal('hide')

  _keyHandle: (e) =>
    if e.keyCode == 27 # = ESC
      e.preventDefault()
      @hide()

  onShown: =>
    doc = window.frames['item-edit-print-frame'].document
    $(doc.head).append(
      for css in ItemEditDialog.priceTagCss
        $('<link>').attr({rel: 'stylesheet', 'href': css})
    )
    console.log(ItemEditDialog.priceTagCss)
    $(doc.body).find('#items').empty().append(@priceTag)

    # A bit excessive, as any form events will also go here, but looks like the dialog cannot be focused and
    # thus not handle ESC keyboard event.
    $(document).on("keydown", @_keyHandle)

  onHidden: =>
    @dialog.remove()
    $(document).off("keydown", @_keyHandle)

  displayError: (msg) =>
    if msg?
      @errorDiv.text(msg)
      @errorDiv.removeClass('alert-off')
    else
      @errorDiv.text('')
      @errorDiv.addClass('alert-off')

  onChange: =>
    # Enable or disable save button depending on whether any values have been changed.
    if do @hasChanged
      @saveButton.prop('disabled', false)
    else
      @saveButton.prop('disabled', true)
    return

  hasChanged: =>
    state = do @getFormState
    if state.price == ""
      # Not-a-number, detected by browser.
      @priceInput.parent().addClass("has-error")
      return false
    @priceInput.parent().removeClass("has-error")
    if Math.round((state.price - 0) * 100) != @item.price
      return true
    for attr in ['name', 'itemtype', 'state', 'abandoned']
      if state[attr] != @item[attr]
        return true
    return false

  onSave: =>
    @displayError(null)
    @action(do @getFormState, @)

  onPrint: =>
    frame = window.frames['item-edit-print-frame']
    do frame.window.focus
    do frame.window.print

  getFromForm: (id) =>
    for i in @form.elements
      if i.id == id
        return i
    return null

  getFormState: =>
    code: @item.code

    name: @getFromForm("item-edit-name-input").value
    price: @getFromForm("item-edit-price-input").value
    itemtype: @getFromForm("item-edit-type-input").value
    state: @getFromForm("item-edit-state-input").value
    abandoned: @getFromForm("item-edit-abandoned-yes").checked
