class @AccountsMode extends CheckoutMode
  ModeSwitcher.registerEntryPoint("accounts", @)

  constructor: ->
    super

  enter: ->
    super
    @getAccounts()

  glyph: -> "briefcase"
  title: -> gettext("Accounts")

  getAccounts: =>
    Api.list_accounts().done(@onAccounts)

  onAccounts: (data) =>
    @form = Template.account_transfer_form(data)
    $(@form).on("submit", @onVerify)
    @cfg.uiRef.body.append(@form)
    @getTransfers()

  getTransfers: =>
    Api.list_transfers().done(@onTransfers)

  onTransfers: (data) =>
    transfers = Template.account_transfers(data, @getTransfers)

    previous = $("#account_transfers", @cfg.uiRef.body)
    if previous.length
      previous.replaceWith(transfers)
    else
      @cfg.uiRef.body.append(transfers)

  onVerify: (e) =>
    e.preventDefault()
    if !@form.reportValidity()
      return

    f = $(@form)
    data =
      src_id: f.find("#src_account").val()
      dst_id: f.find("#dst_account").val()
      amount: f.find("#amount").val()
      note: f.find("#note").val()
      auth: f.find("#authentication").val()
      commit: false
    Api.transfer_money(data).done((receipt) =>

      dlg = $(Template.account_transfer_verify(receipt, () => @onCommit(data)))
      dlg.on("hidden.bs.modal", () => dlg.remove())

      @cfg.uiRef.body.append(dlg)

      dlg.modal()

    ).fail((jqXHR) =>
      alert(jqXHR.responseText)
    )

    return

  onCommit: (data) =>
    data.commit = true
    Api.transfer_money(data).done((receipt) =>
      @form.reset()
      @getTransfers()
    ).fail((jqXHR) =>
      alert(jqXHR.responseText)
    )
