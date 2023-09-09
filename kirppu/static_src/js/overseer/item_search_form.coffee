class @ItemSearchForm

  # Written from outside.
  @itemtypes = []
  @itemstates = []

  constructor: (action) ->
    @action = action
    price_step = 0.5

    form = Template.item_search_form(
      CURRENCY: CURRENCY.raw
      price_step: price_step
      item_types: ItemSearchForm.itemtypes
      item_states: ItemSearchForm.itemstates
    )
    @form = $(form)
    @searchInput = $("#item_search_input", @form)

    @form.off('submit')
    @form.submit(@onSubmit)

  render: -> @form

  onSubmit: (event) =>
    do event.preventDefault
    args = ($("#" + i, @form).val() for i in [
      "item_search_input",
      "item_code_search_input",
      "box_number_input",
      "vendor_search_input",
      "item_search_min_price",
      "item_search_max_price",
      "item_search_type",
      "item_search_state"
    ])
    args.push($("input[name=is_box]:checked").prop("value"))
    args.push($("#show_hidden_items", @form).prop("checked"))
    @action.apply(@, args)

