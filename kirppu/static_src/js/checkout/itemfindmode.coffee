class @ItemFindMode extends CheckoutMode
  ModeSwitcher.registerEntryPoint("item_find", @)

  constructor: ->
    super
    @itemList = new ItemFindList()
    @searchForm = new ItemSearchForm(@doSearch)

  enter: ->
    super
    @cfg.uiRef.body.empty()
    @cfg.uiRef.body.append(@searchForm.render())
    @cfg.uiRef.body.append(@itemList.render())

  glyph: -> "search"
  title: -> "Item Search"

  doSearch: (query, min_price, max_price, type) =>
    Api.item_search(
      query: query
      min_price: min_price
      max_price: max_price
      item_type: if type? then type.join(' ') else ''
    ).done(@onItemsFound)

  onItemsFound: (items) =>
    @itemList.body.empty()
    for item_, index_ in items
      ((item, index) =>
        @itemList.append(
          item,
          index + 1,
        )
      )(item_, index_)

