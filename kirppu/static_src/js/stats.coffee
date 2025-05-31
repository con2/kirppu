
# Produce normal distribution values.
#
# @param x [Array[Number]] X values to get "Y" values for.
# @param mean [Number] Mean value of data.
# @param std [Number] Standard deviation of data.
# @return [Array[Number]] Normal distribution Y values (0..1) matching x values.
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
      frequency[Math.floor(e / stepSize)] += e
  else
    for e in data
      frequency[Math.floor(e / stepSize)] += 1

  return {
    frequency: frequency
    buckets: buckets
    min: 0
    max: lastBucket
  }


# Return mean value of given data set.
mean = (data) ->
  if data.length == 0
    throw new Error("Mean cannot be calculated for empty array")
  sum = 0
  for e in data
    sum += e
  return sum / data.length


# Return population standard deviation of given data set.
pstdev = (data, avg) ->
  count = data.length
  if count == 0
    throw new Error("Standard deviation of population cannot be calculated for empty array")
  sum = 0
  for e in data
    sum += Math.pow(e - avg, 2) / count
  return Math.sqrt(sum)


median = (data) ->
  data = numSort(data)
  n = data.length
  if n == 0
    throw new Error("Median cannot be calculated for empty array")

  i = Math.floor(n / 2)
  if n % 2 == 1
    return data[i]
  else
    return (data[i - 1] + data[i]) / 2


# Round a value to given number of decimals.
roundTo = (value, decimals) ->
  d = Math.pow(10, decimals)
  return Math.round(value * d) / d


# Calculate percentile A from a sorted data set.
percentile = (sorted_data, A) ->
  len = sorted_data.length
  if len == 1
    return sorted_data[0]
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
  # The grouped data and statistics
  grouped = groupData(input, options)
  avg = mean(input)
  dev = pstdev(input, avg)

  # Grouped data does usually have enough data points to give nice normal distribution graph.
  # Create virtual graph with smaller buckets so that the distribution is represented more correctly.
  denseBuckets = options.denseBuckets ? 200
  denseBucket = (grouped.max - grouped.min) / denseBuckets
  denseBucketArr = new Array(denseBuckets + 1)
  denseAcc = 0
  for i in [0..denseBuckets]
    denseBucketArr[i] = denseAcc
    denseAcc += denseBucket
  denseDist = normalDist(denseBucketArr, avg, dev)

  mul = maxArr(grouped.frequency) / maxArr(denseDist) / 2
  denseLen = denseDist.length
  denseResult = []
  for i in [0...denseLen]
    denseResult.push(
      [denseBucketArr[i], denseDist[i] * mul]
    )

  len = grouped.buckets.length
  to_dense_mul = (denseDist.length - 1) / (len - 1)
  result = []
  for i in [0...len]
    # Lookup the value from the dense graph so that actually displayed data points are more or less with correct values
    # and in correct position.
    dense_pos = to_dense_mul * i
    floor = Math.floor(dense_pos)
    if floor == dense_pos or Math.ceil(dense_pos) >= denseLen
      dense_value = denseResult[floor][1]
#      console.log(i, floor, dense_pos, dense_value)
    else
      # Use linear interpolation for the value to ensure the custom-rendered graph and DG data point match.
      v1 = denseResult[floor][1]
      v2 = denseResult[Math.ceil(dense_pos)][1]
      prop = dense_pos - floor
      dense_value = v1 * (1 - prop) + v2 * prop
#      console.log(i, floor, dense_pos, v1, v2, dense_value)

    result.push(
      [grouped.buckets[i], grouped.frequency[i], dense_value]
    )

  return {
      data: result
      avg: avg
      pstdev: dev
      denseNormDist: denseResult
      median: median(input)
  }


class Graph
  constructor: (@id, @legend, @options = {}) ->
    @_graph = null
    @_lines = null
    @_denseNormDist = null

  _init: (dataFn, options) ->
    if not @_graph?
      series = {}
      series[gettext("Frequency")] =
        plotter: smoothPlotter
      series[gettext("Normal distribution")] =
        plotter: () ->

      options = Object.assign(
        underlayCallback: (c, g, a) => @_underlay(c, g, a)
        series: series
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

  setDenseNormDist: (denseNormDist = null) -> @_denseNormDist = denseNormDist

  setLines: (lines = null) -> @_lines = lines

  _underlay: (canvas, area, g) ->
    @_linePlot(canvas, area, g)
    if @_denseNormDist
      @_normPlot(canvas, area, g)
    return

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

  _normPlot: (canvas, area, g) ->

    canvas.strokeStyle = g.colors_[1]  # fixme: constant
    canvas.lineWidth = 1.0

    prev_x = null
    prev_y = null
    for i in @_denseNormDist
      x = i[0]
      y = i[1]

      if prev_x?
        c_x = g.toDomXCoord(x)
        c_y = g.toDomYCoord(y)
        canvas.beginPath()
        canvas.moveTo(prev_x, prev_y)
        canvas.lineTo(c_x, c_y)
        canvas.stroke()
        prev_x = c_x
        prev_y = c_y
      else
        prev_x = g.toDomXCoord(x)
        prev_y = g.toDomYCoord(y)

    return


initBucketGraph = (id, cfg, valueFormatter) ->
  return new Graph(id, cfg.legend,
    labels: [gettext("Sum"), gettext("Frequency"), gettext("Normal distribution")]
    labelsDiv: cfg.legend
    legend: 'always'
    ylabel: gettext("n")
    xlabel: if cfg.xlabel? then cfg.xlabel else gettext("euros")
    axes:
      x:
        valueFormatter: (i) -> return valueFormatter(i) + " – " + valueFormatter(i + cfg.bucket)
        axisLabelFormatter: (i) -> return valueFormatter(i)
  )

createCurrencyFormatter = (fmt) ->
  return (value) -> fmt[0] + value + fmt[1]


genStatsForData = (data, graph, options) ->
  bucketGraph = bucketedNormDist(data, options)
  ts = three_sigma(data)
  graph.setLines(ts)
  graph.setDenseNormDist(bucketGraph.denseNormDist)
  graph.update(bucketGraph.data)
  bucketGraph.perc68 = ts[0][0]
  bucketGraph.perc95 = ts[1][0]
  bucketGraph.perc997 = ts[2][0]
  return bucketGraph


getJson = (id) ->
  candidate = $("[data-id=#{id}]").get(0)
  if candidate?
    return JSON.parse(candidate.text)
  return null


initGeneralStats = (options) ->
  currencyFormatter = createCurrencyFormatter(options.CURRENCY)
  for _, cfg of options.graphs
    data = getJson(cfg.content)

    if cfg.unit?
      valueFormatter = (v) -> "" + v + " " + cfg.unit
    else
      valueFormatter = currencyFormatter

    if not data? or data.length == 0
      $("#" + cfg.graph).text(gettext("No data"))
      continue

    graph = initBucketGraph(cfg.graph, cfg, valueFormatter)

    stats = genStatsForData(data, graph,
      stepSize: cfg.bucket
    )

    numbers = $("#" + cfg.numbers)
    $(".graph_avg", numbers).text(valueFormatter(roundTo(stats.avg, 3)))
    $(".graph_stdev", numbers).text(valueFormatter(roundTo(stats.pstdev, 3)))
    $(".graph_median", numbers).text(valueFormatter(roundTo(stats.median, 3)))
    $(".graph_perc68", numbers).text(valueFormatter(stats.perc68))
    $(".graph_perc95", numbers).text(valueFormatter(stats.perc95))
    $(".graph_perc997", numbers).text(valueFormatter(stats.perc997))


$(document).ready () ->
  setupAjax()

  config = getJson("config")
  if config?
    if config.stats == "general"
      initGeneralStats(config)
