class @BadgedSelection
  constructor: (tbody=null) ->
    @currentSelection = null
    @tbody = tbody

  enter: ->
    addEventListener("keydown", @_changeSelection)

  exit: ->
    removeEventListener("keydown", @_changeSelection)

  _changeSelection: =>
    return if @currentSelection == null

    rows = @tbody.find("td.badged_index")
    if event.key == "ArrowDown"
      if @currentSelection + 1 < rows.length
        @setBadge(@currentSelection + 1)
      else
        @setBadge(0)
      event.preventDefault()
    else if event.key == "ArrowUp"
      if @currentSelection > 0
        @setBadge(@currentSelection - 1)
      else
        @setBadge(rows.length - 1)
      event.preventDefault()

  setBadge: (index) ->
    rows = @tbody.find("td.badged_index")
    rows.find("span").each(->
      e = $(this)
      t = e.text()
      e.parent().text(t)
    )
    if index == null
      @currentSelection = null
      return
    if index >= rows.length
      return
    @currentSelection = index

    td = $(rows[index])
    txt = td.text()
    badge = $('<span class="badge">')
    badge.attr("title", gettext("Press Enter to view this entry"))
    badge.text(txt)
    td.empty().append(badge)
