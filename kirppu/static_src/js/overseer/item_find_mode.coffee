class @ItemFindMode extends CheckoutMode
  ModeSwitcher.registerEntryPoint("item_find", @)

  constructor: ->
    super
    @itemTable = Template.item_find_table()
    @itemList = $(@itemTable.querySelector("tbody"))
    @searchForm = new ItemSearchForm(@doSearch)
    @search = null

    @_focusInSearch = false
    @searchForm.searchInput.on("focus", () => @_focusInSearch = true)
    @searchForm.searchInput.on("blur", () => @_focusInSearch = false)

  enter: ->
    super
    @cfg.uiRef.body.empty()
    @cfg.uiRef.body.append(@searchForm.render())
    @cfg.uiRef.body.append(@itemTable)
    @searchForm.searchInput.focus()

  glyph: -> "search"
  title: -> gettext("Item Search")

  doSearch: (query, code, box_number, vendor, min_price, max_price, type, state, is_box, show_hidden) =>
    @search =
      query: query
      code: code.toUpperCase()
      box_number: box_number
      vendor: vendor
      min_price: min_price
      max_price: max_price
      item_type: if type? then type.join(' ') else ''
      item_state: if state? then state.join(' ') else ''
      show_hidden: show_hidden
      is_box: is_box
    Api.item_search(@search).done(@onItemsFound)

  onItemsFound: (items) =>
    @itemList.empty()
    for item_, index_ in items
      ((item, index) =>
        @itemList.append(Template.item_find_table_item(
          item: item
          index: index + 1
          onClick: @onItemClick
        ))
      )(item_, index_)
    if items.length == 0
      @itemList.append(Template.item_find_table_no_results())
    if @_focusInSearch
      @searchForm.searchInput.select()
    return

  onItemClick: (item) =>
    do new ItemEditDialog(item, @onItemSaved).show

  onItemSaved: (item, dialog) =>
    Api.item_edit(item).done((editedItem) =>
      dialog.setItem(editedItem)
      if @search?
        Api.item_search(@search).done(@onItemsFound)
    ).fail((jqXHR) =>
      msg = "Item edit failed (#{jqXHR.status}): #{jqXHR.responseText}"
      dialog.displayError(msg)
    )
