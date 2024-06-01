
class BoxesConfig
  url_args:
    # This is used to move urls with arguments from django to JS.
    # It has to satisfy the regexp of the url in django.
    box_id: ''

  urls:
    roller: ''
    box_add: ''
    box_content: ''
    box_hide: ''
    box_print: ''

  enabled: true
  price_min: 0
  price_max: 400

  constructor: ->

  box_content_url: (box_id) ->
    url = @urls.box_content
    return url.replace(@url_args.box_id, box_id)

  box_hide_url: (box_id) ->
    url = @urls.box_hide
    return url.replace(@url_args.box_id, box_id)

  box_print_url: (box_id) ->
    url = @urls.box_print
    return url.replace(@url_args.box_id, box_id)

C = new BoxesConfig


# Add a box with name and price set to form contents.
addBox = ->
  onSuccess = (box) ->
    $('#form-errors').empty()
    box = $(box)
    $('#box-add-form')[0].reset();
    $('#boxes').prepend(box)
    bindBoxEvents($(box))

  onError = (jqXHR, textStatus, errorThrown) ->
    $('#form-errors').empty()
    if jqXHR.responseText
      $('<p>').text(jqXHR.responseText).appendTo($('#form-errors'))

  content =
    description: $("#box-add-description").val()
    name: $("#box-add-itemtitle").val()
    count: $("#box-add-count").val()
    price: $("#box-add-price").val()
    item_type: $("#box-add-itemtype").val()
    adult: $("input[name=box-add-adult]:checked").val()
    bundle_size: $("#box-add-bundleSize").val()

  $.ajax(
    url: C.urls.box_add
    type: 'POST'
    data: content
    success: onSuccess
    error: onError
  )


hideBox = (box, box_id) ->
  $.ajax(
    url: C.box_hide_url(box_id)
    type: 'POST'
    success: ->
      $(box).remove()
    error: ->
      $(box).show('slow')
  )


printBox = (box, box_id) ->
  printFunc = () ->
    window.open( C.box_content_url(box_id), '_blank' )
    $.ajax(
      url: C.box_print_url(box_id)
      type: 'POST'
      success: ->
        $( '#print_box', box).removeClass("btn-success");
    )

  # Display warning if already printed.
  if isPrinted(box)
    warnAlreadyPrinted( printFunc )
  else
    printFunc();


warnAlreadyPrinted = (print) ->
    result = confirm( gettext( 'This box has been already printed. Are you sure you want to print it again?' ) );
    if result
      print();


isPrinted = (box) ->
  return ! $( '#print_box', box ).hasClass("btn-success");


onPriceChange = ->
  input = $(this)

  # Replace ',' with '.' in order to accept numbers with ',' as the period.
  value = input.val().replace(',', '.')
  if value > C.price_max or value < C.price_min or not Number.isConvertible(value)
    input.addClass('has-error')
  else
    input.removeClass('has-error')

  return


parsePositiveInt = (input) ->
  s = input.val()
  v = Number.parseInt(s)
  ni = input.data("nonInitial") ? false
  min = Number.parseInt(input.attr("min") or "1")

  if Number.isNaN(v) or v < min
    if ni or s != (input.attr("value") ? "")
      input.addClass("has-error")
    null
  else
    input.data("nonInitial", true)
    input.removeClass("has-error")
    v

bindFormEvents = ->
  $('#box-add-form').bind('submit', ->
    addBox();
    return false;
  )

  price = $("#box-add-price")
  price.change(onPriceChange)

  # Bundle- and count-related validation logic.
  bundleSize = $("#box-add-bundleSize")  # input
  count = $('#box-add-count')  # input
  total = $('#box-total-item-count')  # p
  countHeader = $("#box-add-count-label")  # label
  countLabelItems = countHeader.data("tl-items")
  countLabelBundles = countHeader.data("tl-bundles")

  bundleSizeLabel = $("#box-add-bundleSize-postfix")
  initialBundleSize = bundleSize.attr("value") ? 1

  totalItems = () ->
    bs = parsePositiveInt(bundleSize)
    c = parsePositiveInt(count)
    if bs? and c?
      t = bs * c
      total.text(ngettext("= %d item", "= %d items", t).replace("%d", t))
      total.removeClass("isInvalid")
    else
      total.addClass("isInvalid")

    if bs?
      isBundle = bs > 1
      prevIsBundle = countHeader.data("isBundle")
      if not prevIsBundle? or isBundle != prevIsBundle
        if isBundle
          countHeader.text(countLabelBundles)
          countHeader.data("isBundle", true)
        else
          countHeader.text(countLabelItems)
          countHeader.data("isBundle", false)

      bundleSizeLabel.text(ngettext("pc /", "pcs /", bs))

    return

  bundleSize.on("input", totalItems)
  count.on("input", totalItems)

  # Add initial value, as it is not set in the template.
  bundleSizeLabel.text(ngettext("pc /", "pcs /", initialBundleSize))

  $("#box-add-form").on("reset", () ->
    bundleSize.data("nonInitial", false)
    bundleSize.removeClass("has-error")
    count.data("nonInitial", false)
    count.removeClass("has-error")
    countHeader.text(countLabelItems)
    countHeader.data("isBundle", false)
    total.text("")
    price.removeClass("has-error")
    bundleSizeLabel.text(ngettext("pc /", "pcs /", initialBundleSize))
    return
  )

  return


bindBoxEvents = (boxes) ->
  boxes.each((index, box) ->
    box = $(box)
    box_id = box.attr('id')

    bindBoxHideEvents(box, box_id)
    bindBoxPrintEvents(box, box_id)

    return
  )
  return


bindBoxHideEvents = (box, box_id) ->
  $('.box_button_hide', box).click( ->
    $(box).hide('slow', -> hideBox(box, box_id))
  )

bindBoxPrintEvents = (box, box_id) ->
  $('#print_box', box).click( ->
    printBox(box, box_id)
  )

window.boxesConfig = C
window.addBox = addBox
window.printBox = printBox
window.bindBoxEvents = bindBoxEvents
window.bindFormEvents = bindFormEvents
