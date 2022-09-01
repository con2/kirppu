@CURRENCY =
  css: ["", ""]
  html: ["", ""]
  raw: ["", ""]

@displayPrice = (price, rounded=false) ->
  if price?
    if Number.isInteger(price)
      price_str = CURRENCY.raw[0] + price.formatCents() + CURRENCY.raw[1]
    else
      price_str = price
      rounded = false
  else
    price_str = ""
    rounded = false

  if rounded and price.round5() != price
    rounded_str = CURRENCY.raw[0] + price.round5().formatCents() + CURRENCY.raw[1]
    price_str = "#{ rounded_str } (#{ price_str })"

  return price_str

@displayState = (state) ->
  {
    SO: gettext('sold')
    BR: gettext('on display')
    ST: gettext('about to be sold')
    MI: gettext('missing')
    RE: gettext('returned to the vendor')
    CO: gettext('sold and compensated to the vendor')
    AD: gettext('not brought to the event')
  }[state]

# Round the number to closest modulo 5.
#
# @return Integer rounded to closest 5.
Number.prototype.round5 = ->
  modulo = this % 5

  # 2.5 == split-point, i.e. half of 5.
  if modulo >= 2.5
    return this + (5 - modulo)
  else
    return this - modulo

# Internal flag to ensure that blinking is finished before the error text can be removed.
stillBlinking = false

# Instance of the sound used for barcode errors.
@UtilSound =
  error: null
  success: null
  question: null

# Display safe alert error message.
#
# @param message [String] Message to display.
# @param blink [Boolean, optional] If true (default), container is blinked.
@safeAlert = (message, blink = true) ->
  if UtilSound.error?
    UtilSound.error.play()
  safeDisplay(CheckoutConfig.uiRef.errorText, message, if blink then "alert-error-blink")


# Display safe alert warning message.
#
# @param message [String] Message to display.
# @param blink [Boolean, optional] If true (default), container is blinked.
@safeWarning = (message, blink = false, sound = false) ->
  if sound and UtilSound.question?
    UtilSound.question.play()
  safeDisplay(CheckoutConfig.uiRef.warningText, message, if blink then "alert-warn-blink")


@fixToUppercase = (code) ->
  # XXX: Convert lowercase code to uppercase... Expecting uppercase codes.
  codeUC = code.toUpperCase()
  if codeUC != code
    code = codeUC
  return code


# Display the alert message.
#
# @param textRef [jQuery] Div reference for the message.
# @param message [String] The message.
# @param blink [String] If truthy, container is blinked with this class.
safeDisplay = (textRef, message, blink) ->
  body = CheckoutConfig.uiRef.container
  text = textRef

  if message
    if message instanceof $
      text.html(message)
    else
      text.text(message)
    text.removeClass("alert-off")
  return if !blink

  listener = () ->
    body.removeClass(blink)
    stillBlinking = false
    return
  body.one("animationend", listener)

  stillBlinking = true
  body.addClass(blink)
  return

# Remove safe alert message, if the alert has been completed.
@safeAlertOff = ->
  return if stillBlinking

  CheckoutConfig.uiRef.errorText.addClass("alert-off")
  CheckoutConfig.uiRef.warningText.addClass("alert-off")
  return


class @RefreshButton
  constructor: (func, title=gettext("Refresh")) ->
    @refresh = func
    @title = title

  render: ->
    $('<button class="btn btn-default hidden-print">').append(
      $('<span class="glyphicon glyphicon-refresh">')
    ).on(
      "click", @refresh
    ).attr(
      "title", @title
    )


@addEnableCheck = () ->
  $(".check_enabled a").each((index, element) ->
    # Replace href of the 'a' element with dummy.
    target = element.href
    element.href = "javascript:void(0)"
    $(element).data("link-target", target)
  )

@setCheckedLinkEnabled = (link, enabled) ->
  container = $(link)
  setClass(container, "disabled", not enabled)

  theLink = container.find("a")
  if enabled
    theLink.attr("href", theLink.data("link-target"))
  else
    theLink.attr("href", "javascript:void(0)")


# PrintF-style formatter that actually formats just replacements.
# Placeholders not found in args are assumed empty. Double-percent is converted to single percent sign.
#
# @param format [String] The format string. Placeholders start with percent sign (%) and must be exactly one character long.
# @param args [Object, optional] Placeholder-to-values map. Keys must be exactly one character long.
# @return [String] Formatted string.
@dPrintF = (format, args={}) ->
  if not Object.keys(args).every((key) -> key.length == 1)
    throw Error("Key must be exactly one character long.")

  replacer = (s) ->
    val = s[1]
    if val of args
      return args[val]
    else if val == "%"
      return val
    else
      return ""

  replaceExp = new RegExp("%.", 'g')
  return format.replace(replaceExp, replacer)


@mPrintF = (format, args={}) ->
  replacer = (m, val) ->
    if val of args
      return args[val]
    else
      return ""

  replaceExp = new RegExp("{(\\w+)}", "g")
  return format.replace(replaceExp, replacer)
