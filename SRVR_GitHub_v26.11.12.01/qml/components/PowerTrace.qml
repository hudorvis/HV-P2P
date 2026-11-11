import QtQuick 2.15

Canvas {
    id: plot
    objectName: "pdmPowerTrace"
    property var points: []
    property real scaleFactor: 1
    property color traceColor: "#26d5ff"
    property string unit: "V"
    property real axisLow: NaN
    property real axisHigh: NaN
    readonly property real plotLeft: Math.max(38, 54 * scaleFactor)
    readonly property real plotRight: width - 4
    readonly property real plotBottom: height - Math.max(17, 22 * scaleFactor)
    readonly property var hoverSample: pointer.containsMouse ? nearestSample(pointer.mouseX) : null

    function nearestSample(x) {
        if (points.length === 0 || plotRight <= plotLeft || x < plotLeft || x > plotRight)
            return null
        const first = points[0][0]
        const last = points[points.length - 1][0]
        const stamp = first + (x - plotLeft) * Math.max(1, last - first) / (plotRight - plotLeft)
        let left = 0
        let right = points.length - 1
        while (left < right) {
            const middle = Math.floor((left + right) / 2)
            if (points[middle][0] < stamp)
                left = middle + 1
            else
                right = middle
        }
        const after = points[left]
        if (left === 0 || stamp === after[0])
            return Number.isFinite(after[1]) ? after : null
        const before = points[left - 1]
        const nearest = stamp - before[0] <= after[0] - stamp ? before : after
        if (!Number.isFinite(nearest[1]))
            return null
        if (Number.isFinite(before[1]) && Number.isFinite(after[1]))
            return nearest
        const distance = Math.abs(nearest[0] - stamp) * (plotRight - plotLeft) / Math.max(1, last - first)
        return distance <= 5 ? nearest : null
    }

    onPointsChanged: requestPaint()
    onScaleFactorChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onVisibleChanged: if (visible) requestPaint()

    onPaint: {
        const ctx = getContext("2d")
        ctx.reset()
        ctx.clearRect(0, 0, width, height)
        ctx.font = Math.max(9, 11 * scaleFactor) + "px sans-serif"
        ctx.fillStyle = "#aeb4b1"
        let low = Infinity
        let high = -Infinity
        for (const point of points) {
            if (Number.isFinite(point[1])) {
                low = Math.min(low, point[1])
                high = Math.max(high, point[1])
            }
        }
        if (!Number.isFinite(low)) {
            axisLow = NaN
            axisHigh = NaN
            ctx.textAlign = "center"
            ctx.fillText("No readings", width / 2, height / 2)
            return
        }
        const left = plotLeft
        const right = plotRight
        const top = 8
        const bottom = plotBottom
        if (right <= left || bottom <= top)
            return
        const padding = Math.max(0.05, (high - low) * 0.08)
        low -= padding
        high += padding
        axisLow = low
        axisHigh = high
        const first = points[0][0]
        const last = points[points.length - 1][0]
        const range = Math.max(1, last - first)
        const timeFormat = range < 10000 ? "hh:mm:ss.zzz" : range < 120000 ? "hh:mm:ss" : "dd MMM hh:mm"
        ctx.textAlign = "right"
        ctx.textBaseline = "middle"
        ctx.strokeStyle = "#384146"
        for (let tick = 0; tick <= 4; ++tick) {
            const fraction = tick / 4
            const y = top + fraction * (bottom - top)
            ctx.fillText((high - fraction * (high - low)).toFixed(2), left - 5, y)
            ctx.beginPath()
            ctx.moveTo(left, y)
            ctx.lineTo(right, y)
            ctx.stroke()
        }
        ctx.textBaseline = "bottom"
        ctx.textAlign = "left"
        ctx.fillText(Qt.formatDateTime(new Date(first), timeFormat), left, height)
        if (last !== first) {
            ctx.textAlign = "right"
            ctx.fillText(Qt.formatDateTime(new Date(last), timeFormat), right, height)
        }
        ctx.strokeStyle = traceColor
        ctx.fillStyle = traceColor
        ctx.lineWidth = 1.5
        ctx.beginPath()
        let penDown = false
        for (const point of points) {
            if (!Number.isFinite(point[1])) {
                penDown = false
                continue
            }
            const x = left + (point[0] - first) / range * (right - left)
            const y = top + (high - point[1]) / (high - low) * (bottom - top)
            if (penDown) {
                ctx.lineTo(x, y)
            } else {
                ctx.fillRect(x - 1, y - 1, 2, 2)
                ctx.moveTo(x, y)
            }
            penDown = true
        }
        ctx.stroke()
    }

    MouseArea {
        objectName: "monitorTracePointer"
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.NoButton
    }

    Rectangle {
        id: marker
        objectName: "monitorHoverMarker"
        visible: plot.hoverSample !== null && Number.isFinite(plot.axisLow) && plot.plotBottom > 8
        width: 7
        height: width
        radius: width / 2
        color: plot.traceColor
        border.color: "#0f1316"
        x: !visible ? 0 : plot.plotLeft - width / 2 + (plot.hoverSample[0] - plot.points[0][0])
            / Math.max(1, plot.points[plot.points.length - 1][0] - plot.points[0][0])
            * (plot.plotRight - plot.plotLeft)
        y: !visible ? 0 : 8 - height / 2 + (plot.axisHigh - plot.hoverSample[1])
            / (plot.axisHigh - plot.axisLow) * (plot.plotBottom - 8)
    }

    Rectangle {
        visible: marker.visible
        width: readout.implicitWidth + 14
        height: readout.implicitHeight + 8
        radius: 4
        color: "#171c20"
        border.color: "#596064"
        x: Math.max(0, Math.min(plot.width - width, marker.x + 12))
        y: marker.y > height + 4 ? marker.y - height - 4 : marker.y + 12
        Text {
            id: readout
            objectName: "monitorHoverReadout"
            anchors.centerIn: parent
            color: "#f0f2f1"
            font.pixelSize: Math.max(10, 12 * plot.scaleFactor)
            text: plot.hoverSample === null ? "" : Number(plot.hoverSample[1]).toFixed(2) + " " + plot.unit
                + "  •  " + Qt.formatDateTime(new Date(plot.hoverSample[0]), "dd MMM hh:mm:ss.zzz")
        }
    }
}
