class @ClerkLoginMode extends CheckoutMode
  ModeSwitcher.registerEntryPoint("clerk_login", @)

  @autoClerk = null

  title: -> gettext("Locked")
  subtitle: -> gettext("Login...")

  enter: ->
    super
    @switcher.setMenuEnabled(false, true)
    if @constructor.autoClerk?
      @cfg.uiRef.codeInput.val(@constructor.autoClerk)

  actions: -> [[
    "",
    (code) =>
      code = code.replace("\u00AD", "")
      Api.clerk_login(
        code: code
        counter: @cfg.settings.counterCode
      ).then(@onResultSuccess, @onResultError)
  ]]

  onResultSuccess: (data) =>
    @notifySuccess()
    username = data["user"]
    @cfg.settings.clerkName = username
    console.log("Logged in as #{username}.")
    @switcher.setOverseerVisible(data["overseer_enabled"])
    @switcher.setStatsVisible(data["stats_enabled"])
    if data["receipts"]?
      @multipleReceipts(data["receipts"])
    else if data["receipt"]?
      @activateReceipt(data["receipt"])
    else
      @switcher.switchTo(CounterMode)

  onResultError: (jqXHR) =>
    if jqXHR.status == 419
      console.log("Login failed: " + jqXHR.responseText)
      return
    safeAlert("Error:" + jqXHR.responseText)
    return true

  activateReceipt: (receipt) ->
    @switcher.switchTo(CounterMode, receipt)

  multipleReceipts: (receipts) ->
    dialog = new Dialog()
    icon = '<span class="glyphicon glyphicon-warning-sign text-warning"></span>'
    dialog.title.html(pgettext("%s is a warning icon, leave a space after it.",
      "%s Multiple receipts active").replace("%s", icon))

    info = $("<div>").text(gettext("Please select receipt, which you want to continue."))
    table = $ Template.receipt_list_table_simple(
      items: receipts
    )

    buttonPositive = dialog.addPositive().text(gettext("Select"))

    # This may not use => version of function, as `this` of the row is needed.
    $("tbody tr", table).click(() ->
      table.find(".success").removeClass("success")
      $(this).addClass("success")
      dialog.setEnabled(buttonPositive)
    )

    dialog.body.append(info, table)

    buttonPositive.click(() =>
      index = $("tbody", table).find(".success").data("index")
      if index?
        console.log("Selected #{ 1 + index }: " + receipts[index].start_time)
        @switcher.switchTo(CounterMode, receipts[index])
    )
    dialog.setEnabled(buttonPositive, false)
    dialog.addNegative().text("Cancel").click(() -> console.log("Cancelled receipt selection"))

    # Don't close with keyboard ESC, or by clicking outside dialog.
    dialog.show(
      keyboard: false
      backdrop: "static"
    )
