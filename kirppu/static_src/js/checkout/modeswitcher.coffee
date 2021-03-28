# Safely set or remove class to/from element.
#
# @param element [$] Element to adjust.
# @param cls [String] CSS Class name to adjust.
# @param enabled [Boolean] Whether the class should exist in the element.
# @return [$] The element.
@setClass = (element, cls, enabled, test=null) ->
  if test != null and not test(element)
    return element
  if element.hasClass(cls) != enabled
    if enabled
      element.addClass(cls)
    else
      element.removeClass(cls)
  return element

# Class for switching CheckoutModes.
class @ModeSwitcher

  # Map of entry point names to CheckoutModes.
  @entryPoints = {}

  # Global autofocus enable/disable.
  @autoFocus = true

  # Register entry point with name.
  #
  # @param name [String] Name of the entry point.
  # @param mode [CheckoutMode] Entry point, CheckoutMode subclass.s
  @registerEntryPoint: (name, mode) ->
    if name of @entryPoints
      console.error("Name '#{ name }' was already registered for '#{ @entryPoints[name].name }' while registering '#{ mode.name }'.")
    else
      @entryPoints[name] = mode

  # @param config [Config, optional] Configuration instance override.
  constructor: (config) ->
    @cfg = if config then config else CheckoutConfig
    @_currentMode = null
    @_bindMenu(ModeSwitcher.entryPoints)
    @_bindForm()

    # Function for regaining focus after dialog closing.
    regainFocus = () =>
      return unless ModeSwitcher.autoFocus && @_currentMode != null && @_currentMode.autoFocus()

      timeoutFocus = () => @cfg.uiRef.codeInput.focus()
      # The actual focusing needs to be done after the event has been processed so that the focus can actually be set.
      setTimeout(timeoutFocus, 0)

    # Regain focus with both, template and help dialog.
    @cfg.uiRef.dialog.on("hidden.bs.modal", regainFocus)
    $("#help_dialog").on("hidden.bs.modal", regainFocus)

    # Regain focus when window is focused.
    $(window).on("focus", regainFocus)

  # Start default mode operation.
  startDefault: (entry="counter_validation") ->
    @switchTo(ModeSwitcher.entryPoints[entry])
    _populateCommandRefs()
    return

  # Switch to new mode. This is called by modes.
  #
  # @param mode [CheckoutMode, class] Class of new mode.
  # @param args... [] Arguments for the mode constructor.
  switchTo: (mode, params...) ->
    if @_currentMode? then @_currentMode.exit()
    @setMenuEnabled(true)

    if params.length == 0
      params.push(null)  # Old behaviour was to pass a single null if no parameters were given.
    params.unshift(null, @, @cfg)  # null is .apply() weirdness.
    @_currentMode = new (mode.bind.apply(mode, params))   # NOTE: Needs ECMAScript 5!

    safeAlertOff()

    @cfg.uiRef.container.removeClass().addClass('container').addClass('color-mode')
    @cfg.uiRef.container.addClass('color-' + @_currentMode.constructor.name)
    @cfg.uiRef.body.empty()
    @updateHead()
    @_currentMode.enter()

    # Restore focus to the input field after mode change.
    @cfg.uiRef.codeInput.focus()
    return

  updateHead: ->
    @cfg.uiRef.glyph.removeClass()
    if @_currentMode.glyph()
      @cfg.uiRef.glyph.addClass("glyphicon glyphicon-" + @_currentMode.glyph())
      @cfg.uiRef.glyph.addClass("hidden-print")
    @cfg.uiRef.stateText.text(@_currentMode.title())
    @cfg.uiRef.subtitleText.text(@_currentMode.subtitle() or "")
    @cfg.uiRef.codeInput.attr("placeholder", @_currentMode.inputPlaceholder())
    @setPrintable(false)
    return

  setPrintable: (printable=true) ->
    btn = @cfg.uiRef.printButton
    if printable
      btn.removeClass("hidden")
    else
      btn.addClass("hidden")

  # Bind functions to HTML elements.
  _bindForm: ->
    form = @cfg.uiRef.codeForm
    form.off("submit")
    form.submit(@_onFormSubmit)

    @cfg.uiRef.printButton.click(-> window.print())
    @cfg.uiRef.codeInput.on("keypress", capsLockDetect((capsOn) =>
      $("#capslock_container")[if capsOn then "removeClass" else "addClass"]("alert-off")
    ))

  _onFormSubmit: (event) =>
    event.preventDefault()
    input = @cfg.uiRef.codeInput.val()
    actions = @_currentMode.actions()

    # List of prefixes that match the input.
    matching = (a for a in actions when input.indexOf(a[0]) == 0)
    # Sort to longest first order.
    matching = matching.sort((a, b) -> b[0].length - a[0].length)

    if matching[0]?
      [prefix, handler] = matching[0]
      if input.trim().length > 0
        safeAlertOff()
      handler(input.slice(prefix.length), prefix)
    else
      console.error("Input not accepted: '#{input}'.")
    @cfg.uiRef.codeInput.val("")
    return

  # Bind mode switching menu items.
  _bindMenu: (entryPoints) ->
    # For all menu-items that have data-entrypoint attribute defined, if the
    # name defined by that attribute is found in entryPoints, add
    # click-handler that will switch mode to the mode defined by the value in
    # entryPoints dictionary.
    menu = @cfg.uiRef.modeMenu
    items = menu.find("[data-entrypoint]")
    for itemDom in items
      item = $(itemDom)
      entryPointName = item.attr("data-entrypoint")
      if entryPointName of entryPoints
        entryPoint = entryPoints[entryPointName]

        # As entryPoint -variable is somehow shared across all iterations of
        # the for-loop, forcing own variable per iteration with extra function
        # wrap that is called immediately with current values.
        ((this_, ep) ->
          item.click(() ->
            console.log("Changing mode from menu to " + ep.name)
            this_.switchTo(ep)
          )
        )(@, entryPoint)
      else
        console.warn("Entry point '#{ entryPointName }' could not be found from registered entry points. Source:")
        console.log(itemDom)
    return

  # Enable or disable mode switching menu.
  #
  # @param enabled [Boolean] If true, menu will be enabled. If false, menu will be disabled.
  setMenuEnabled: (enabled, allowLanguageWhenDisabled=false) ->
    menu = @cfg.uiRef.modeMenu
    setClass(menu, "disabled", not enabled)
    setClass(menu.find("a:first"), "disabled", not enabled)
    setCheckedLinkEnabled(@cfg.uiRef.overseerLink, enabled and not @cfg.uiRef.overseerLink.hasClass("hidden"))
    setCheckedLinkEnabled(@cfg.uiRef.statsLink, enabled and not @cfg.uiRef.statsLink.hasClass("hidden"))
    @cfg.uiRef.languageSelection.prop("disabled", if ((enabled or allowLanguageWhenDisabled)) then "" else "disabled")
    return

  # Enable or disable the link to overseer dashboard
  #
  # @param enabled [Boolean] If true, enable the link. If false, disable
  # the link.
  setOverseerVisible: (enabled) ->
    setClass(@cfg.uiRef.overseerLink, 'hidden', not enabled)
    setCheckedLinkEnabled(@cfg.uiRef.overseerLink, enabled and not @cfg.uiRef.overseerLink.hasClass("disabled"))

  # Enable or disable the link to stats
  #
  # @param enabled [Boolean] If true, enable the link. If false, disable
  # the link.
  setStatsVisible: (enabled) ->
    setClass(@cfg.uiRef.statsLink, 'hidden', not enabled)
    setCheckedLinkEnabled(@cfg.uiRef.statsLink, enabled and not @cfg.uiRef.statsLink.hasClass("disabled"))


# Populate values from commands of Modes for all 'data-command-value' and 'data-command-title' elements in DOM.
_populateCommandRefs = () ->
  codes = {}  # All codes from various modes.
  for modeName, mode of ModeSwitcher.entryPoints
    cmds = mode.prototype.commands()
    for key, value of cmds
      codes[key] = value

  for key, value of codes
    $("[data-command-value='#{ key }']").text(value[0])
    $("[data-command-title='#{ key }']").text(value[1])
