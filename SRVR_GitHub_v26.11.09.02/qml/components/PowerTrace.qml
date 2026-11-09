import QtQuick 2.15

Canvas {
    id: plot
    objectName: "pdmPowerTrace"
    property var points: []
    property real scaleFactor: 1
    property color traceColor: "#26d5ff"
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
            ctx.textAlign = "center"
            ctx.fillText("No readings", width / 2, height / 2)
            return
        }
        const left = Math.max(38, 54 * scaleFactor)
        const right = width - 4
        const top = 8
        const bottom = height - Math.max(17, 22 * scaleFactor)
        if (right <= left || bottom <= top)
            return
        const padding = Math.max(0.05, (high - low) * 0.08)
        low -= padding
        high += padding
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
}
