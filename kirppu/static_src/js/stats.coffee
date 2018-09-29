
# Produce normal distribution values.
#
# @param x [Array[Number]] X values to get "Y" values for.
# @param mean [Number] Mean value of data.
# @param std [Number] Standard deviation of data.
# @return [Array[Number]] Normal distribution Y values (0..1) matching x values.
normalDist = (x, mean, std) ->
  normDist = []
  if x.length >= 2 and std != 0

    c1 = 1 / (std * Math.sqrt(2 * Math.PI))
    c2 = (std * std) * 2

    for b in x
        d1 = b - mean
        v = c1 * Math.pow(Math.E, -(d1 * d1) / c2)
        normDist.push(v)
  else if x.length > 0
    # x has values, but std is zero.
    found = false
    # may produce slightly off peak, but if x is long enough, it doesn't matter.
    for b in x
      if not found and b >= mean
        normDist.push(1)
        found = true
      else
        normDist.push(0)

  return normDist


# Calculate maximum of array.
# @param data [Array[Number]]
# @return [Number] Maximum of the array.
maxArr = (data) -> Math.max.apply(null, data)


# Group data by their values.
# @param data [Array[Number]] Array of non-negative numbers.
# @param options [Object, optional] Options:
#        - stepSize, or how wide one bucket is,
#        - sumValues: if true, the result will have sum of the bucket values instead of count of values.
# @return [Object]
#        - frequency: The bucket values, or y-axle.
#        - buckets: The bucket (excluding) start value, or x-axle. The (including) end value is start + stepSize.
groupData = (data, options) ->
  options = Object.assign(
    stepSize: 50
    sumValues: false
    , options
  )
  stepSize = options.stepSize

  max = maxArr(data)
  lastBucket = (Math.ceil(max / stepSize) + 1) * stepSize
  currentBucket = 0
  frequency = []
  buckets = []
  while currentBucket <= lastBucket
    frequency.push(0)
    buckets.push(currentBucket)
    currentBucket += stepSize

  if options.sumValues
    for e in data
      frequency[Math.ceil(e / stepSize)] += e
  else
    for e in data
      frequency[Math.ceil(e / stepSize)] += 1

  return {
    frequency: frequency
    buckets: buckets
  }


# Return mean value of given data set.
mean = (data) ->
  sum = 0
  for e in data
    sum += e
  return sum / data.length


# Return population standard deviation of given data set.
pstdev = (data, avg) ->
  count = data.length
  sum = 0
  for e in data
    sum += Math.pow(e - avg, 2) / count
  return Math.sqrt(sum)


# Round a value to given number of decimals.
roundTo = (value, decimals) ->
  d = Math.pow(10, decimals)
  return Math.round(value * d) / d


# Calculate percentile A from a sorted data set.
percentile = (sorted_data, A) ->
  len = sorted_data.length
  rank = (A / 100) * (len - 1)
  pos = Math.floor(rank)
  rem = rank - pos
  val_at_pos = sorted_data[pos]
  value = val_at_pos + rem * (sorted_data[pos + 1] - val_at_pos)
  return value


# Perform a numerical sort for data. The input is not modified.
numSort = (data) ->
  return Array.from(data).sort (a, b) -> a - b


percentileObj = (sortedData, A) ->
  return [roundTo(percentile(sortedData, A), 2), "" + A + "%"]


three_sigma = (sortedData) ->
  # remember implicit return?
  for A in [68, 95, 99.7]
    percentileObj(sortedData, A)


bucketedNormDist = (input, options) ->
  grouped = groupData(input, options)
  avg = mean(input)
  dev = pstdev(input, avg)
  dist = normalDist(grouped.buckets, avg, dev)

  len = dist.length
  mul = maxArr(grouped.frequency) / maxArr(dist) / 2
  result = []
  for i in [0...len]
    result.push(
      [grouped.buckets[i], grouped.frequency[i], roundTo(dist[i] * mul, 2)]
    )

  return {
      data: result
      avg: avg
      pstdev: pstdev
  }


class Graph
  constructor: (@id, @legend, @options = {}) ->
    @_graph = null
    @_lines = null

  _init: (dataFn, options) ->
    if not @_graph?
      options = Object.assign(
        plotter: smoothPlotter
        underlayCallback: (c, g, a) => @_linePlot(c, g, a)
        labelsDiv: @legend
        , @options
        , options
      )

      @_graph = new Dygraph(
        document.getElementById(@id),
        dataFn,
        options
      )
      return false
    return true

  update: (dataFn, options = {}) ->
    if @_init(dataFn, options)
      options = Object.assign(
        file: dataFn
        , options
      )
      @_graph.updateOptions(options, false)
    return

  setLines: (lines = null) -> @_lines = lines

  _linePlot: (canvas, area, g) ->
    if not @_lines?
      return

    min_data_x = g.getValue(0, 0)
    max_data_x = g.getValue(g.numRows() - 1, 0)

    canvas.strokeStyle = "rgb(102, 128, 0)"
    canvas.fillStyle = "rgb(10, 13, 0)"
    canvas.lineWidth = 2.0
    canvas.font = "12px"

    for l in @_lines
      label = null
      if Array.isArray(l)
        [l, label] = l

      if l >= min_data_x and l <= max_data_x
        x = (l - min_data_x)
        c_x = g.toDomXCoord(x)
        canvas.beginPath()
        canvas.moveTo(c_x, area.y)
        canvas.lineTo(c_x, area.y + area.h)
        canvas.stroke()
        if label?
          # TODO: Maybe replace these constants with something other?
          canvas.fillText(label, c_x + 5, area.y + 15)
          canvas.fillText(l, c_x + 5, area.y + 25)

    return


initBucketGraph = (id, legend, currencyFormatter, bucket) ->
  return new Graph(id, legend,
    labels: [gettext("Sum"), gettext("Frequency"), gettext("Normal distribution")]
    labelsDiv: legend
    legend: 'always'
    ylabel: gettext("n")
    xlabel: gettext("euros")
    axes:
      x:
        valueFormatter: (i) -> return currencyFormatter(i) + " – " + currencyFormatter(i + bucket)
        axisLabelFormatter: (i) -> return currencyFormatter(i)
  )

createCurrencyFormatter = (fmt) ->
  return (value) -> fmt[0] + value + fmt[1]


genStatsForData = (data, graph, options) ->
  bucketGraph = bucketedNormDist(data, options)
  ts = three_sigma(data)
  graph.setLines(ts)
  graph.update(bucketGraph.data)


getJson = (id) ->
  candidate = $("[data-id=#{id}]").get(0)
  if candidate?
    return JSON.parse(candidate.text)
  return null


initGeneralStats = (options) ->
  currencyFormatter = createCurrencyFormatter(options.CURRENCY)
  for _, cfg of options.graphs
    data = getJson(cfg.content)
    graph = initBucketGraph(cfg.graph, cfg.legend, currencyFormatter, cfg.bucket)

    genStatsForData(data, graph,
      stepSize: cfg.bucket
    )


$(document).ready () ->
  setupAjax()

  config = getJson("config")
  if config?
    if config.stats == "general"
      initGeneralStats(config)
