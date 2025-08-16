# Encode give Utf-8 string to base64.
#
# @param str [String] String to encode.
# @return [String] Base64 encoded string.
utf8_to_b64 = (str) ->
    return window.btoa(encodeURIComponent(escape( str )))

# Decode base64 string to Utf-8 string.
#
# @param str [String] Base64 to decode.
# @return [String] Utf-8 string.
b64_to_utf8 = (str) ->
    return unescape(decodeURIComponent(window.atob( str )))

class @CounterValidationMode extends CheckoutMode
  ModeSwitcher.registerEntryPoint("counter_validation", @)

  @COOKIE = "mCV"

  title: -> gettext("Locked")
  subtitle: -> gettext("Need to validate counter.")
  inputPlaceholder: -> gettext("Counter identifier")

  enter: ->
    super
    @switcher.setMenuEnabled(false, true)

    # If we have values for Counter in cookie storage, use them and
    # immediately switch to clerk login.
    code = Cookies.get(@constructor.COOKIE)
    if code?
      data = JSON.parse(b64_to_utf8(code))
      @reValidate(data["counter"])

  actions: -> [[
    @cfg.settings.counterPrefix, @validate
  ], [
    "", @list
  ]]

  validate: (code) =>
    Api.counter_validate(
      code: code
    ).then(@onResultSuccess, @onResultError)

  reValidate: (key) =>
    Api.counter_validate(
      key: key
    ).then(@onResultSuccess, @onResultError)

  list: (code) =>
    @cfg.uiRef.body.empty()
    if code.length < 8 or code.length > 64
      return
    Api.counter_list(
      code: code
    ).done((counters) =>
      @cfg.uiRef.body.append(Template.counter_list(counters: counters))
    )

  onResultSuccess: (data) =>
    code = data["key"]
    name = data["name"]
    expires = data["expires"]
    path = data["path"]
    @cfg.settings.counterCode = code
    @cfg.settings.counterName = name
    console.log("Validated as #{name}.")

    # Store values for next time so the mode can be skipped.
    Cookies.set(@constructor.COOKIE, utf8_to_b64(JSON.stringify(
      counter: code
    )),
      expires: expires
      path: path
    )
    @switcher.switchTo(ClerkLoginMode)

  onResultError: (jqXHR) =>
    if jqXHR.status == 419
      console.log("Invalid counter code supplied.")
      CounterValidationMode.clearStore()
      return
    alert("Error:" + jqXHR.responseText)
    return true

  @clearStore: ->
    Cookies.remove(@COOKIE)
