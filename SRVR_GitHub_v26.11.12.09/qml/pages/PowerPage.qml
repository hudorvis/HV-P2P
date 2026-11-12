pragma ComponentBehavior: Bound

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../components"

Item {
    id: page
    objectName: "powerPage"
    required property var powerDevice
    required property var windDevice
    property bool windSelected: false
    readonly property var monitor: windSelected ? windDevice : powerDevice
    readonly property string node: windSelected ? "WSI" : "PDM"
    readonly property string unit: windSelected ? "m/s" : "V"
    onVisibleChanged: if (!visible) {
        logSettings.close()
        channelSettings.close()
    }
    onWindSelectedChanged: {
        logSettings.close()
        channelSettings.close()
    }
    property real scaleFactor: 1
    readonly property var summary: monitor.summary
    readonly property color cyan: "#26d5ff"
    readonly property color muted: "#aeb4b1"

    function px(size) { return Math.max(1, size * scaleFactor) }
    function valueText(value) {
        return (Number.isFinite(value) ? value.toFixed(2) : "—") + " " + unit
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: page.px(8)

        RowLayout {
            spacing: page.px(6)
            HVButton { text: "PDM"; selected: !page.windSelected; onClicked: page.windSelected = false }
            HVButton { text: "WSI"; selected: page.windSelected; onClicked: page.windSelected = true }
        }

        Panel {
            Layout.fillWidth: true
            implicitHeight: statusRows.implicitHeight + page.px(20)

            ColumnLayout {
                id: statusRows
                anchors.fill: parent
                anchors.margins: page.px(10)
                spacing: page.px(6)

                RowLayout {
                    spacing: page.px(12)
                    Text {
                        text: page.windSelected ? "Wind Speed Indicator" : "Power Distribution Module"
                        color: page.cyan
                        font.pixelSize: page.px(19)
                        font.weight: Font.Medium
                    }
                    Text {
                        text: page.summary.connection
                        color: text === "Live" ? "#63d84e" : text === "Stale data" ? "#e7c94a" : page.muted
                        font.pixelSize: page.px(14)
                    }
                    Item { Layout.fillWidth: true }
                    Text { visible: page.windSelected; text: "WSI address"; color: page.muted; font.pixelSize: page.px(13) }
                    TextField {
                        id: windAddressField
                        objectName: "wsiAddressField"
                        visible: page.windSelected
                        Layout.preferredWidth: page.px(148)
                        implicitHeight: page.px(30)
                        text: page.windDevice.address
                        maximumLength: 15
                        selectByMouse: true
                        color: "#f0f2f1"
                        font.pixelSize: page.px(14)
                        background: Rectangle {
                            color: "#101518"
                            radius: 4
                            border.color: windAddressField.activeFocus ? page.cyan : "#4a4f52"
                        }
                        onAccepted: applyWindAddress.clicked()
                    }
                    HVButton {
                        id: applyWindAddress
                        visible: page.windSelected
                        text: "Apply"
                        implicitHeight: page.px(30)
                        implicitWidth: page.px(72)
                        font.pixelSize: page.px(14)
                        onClicked: {
                            const address = windAddressField.text.trim()
                            addressError.text = address && address === page.powerDevice.address
                                ? "Enter a separate address for each device"
                                : page.windDevice.saveAddress(address)
                        }
                    }
                    RowLayout {
                        layoutDirection: page.windSelected ? Qt.RightToLeft : Qt.LeftToRight
                        spacing: page.px(12)
                        HVButton {
                            objectName: "monitorOpenWeb"
                            text: page.windSelected ? "Open WSI Web UI" : "Web UI"
                            enabled: page.monitor.address.length > 0
                            implicitHeight: page.px(30)
                            implicitWidth: page.px(page.windSelected ? 178 : 84)
                            font.pixelSize: page.px(14)
                            onClicked: page.monitor.openWeb()
                        }
                        HVButton {
                            objectName: "monitorLogButton"
                            text: page.windSelected ? "Log Settings" : "Settings"
                            implicitHeight: page.px(30)
                            implicitWidth: page.px(page.windSelected ? 112 : 84)
                            font.pixelSize: page.px(14)
                            enabled: !page.monitor.logBusy && (!page.windSelected || page.summary.online)
                            onClicked: logSettings.open()
                        }
                    }
                }

                RowLayout {
                    spacing: page.px(12)
                    Text {
                        objectName: "monitorFirmware"
                        text: {
                            const update = page.summary.update
                            const showUpdate = page.summary.online && update && update !== "—"
                                            && (page.windSelected || update !== "Looking for SRVR")
                            return "Firmware " + page.summary.version + (showUpdate ? "  •  " + update : "")
                        }
                        textFormat: Text.PlainText
                        color: page.muted
                        font.pixelSize: page.px(13)
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    ProgressBar {
                        visible: page.summary.online && page.summary.progress > 0
                        value: Math.min(100, Math.max(0, page.summary.progress)) / 100
                        Layout.preferredWidth: page.px(110)
                    }
                    Text {
                        visible: page.summary.online && page.summary.progress > 0
                        text: page.summary.progress + "%"
                        color: page.cyan
                        font.pixelSize: page.px(13)
                    }
                    Text {
                        text: page.summary.when
                            ? "Last sample " + Qt.formatDateTime(new Date(page.summary.when), "dd MMM hh:mm:ss")
                              + (page.summary.estimated ? " (estimated)" : "")
                            : "Waiting for samples"
                        color: page.muted
                        font.pixelSize: page.px(13)
                    }
                }
                Text {
                    id: addressError
                    Layout.fillWidth: true
                    visible: page.windSelected && text.length > 0
                    color: "#ef5757"
                    font.pixelSize: page.px(13)
                }
                Text {
                    Layout.fillWidth: true
                    visible: text.length > 0
                    text: page.monitor.bundleNote
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    color: "#e7c94a"
                    font.pixelSize: page.px(13)
                }
            }
        }

        GridLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            columns: page.windSelected ? 1 : 2
            columnSpacing: page.px(8)
            rowSpacing: page.px(8)

            Repeater {
                model: page.windSelected ? 1 : 4

                Panel {
                    id: channel
                    required property int index
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: 1
                    Layout.preferredHeight: 1
                    readonly property var volts: page.summary.voltages[index]
                    readonly property string alarm: page.summary.alarms[index] || ""
                    readonly property var extrema: (page.summary.extrema || [])[index] || {}

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: page.px(12)
                        spacing: page.px(4)

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 3
                            columnSpacing: page.px(8)
                            rowSpacing: page.px(4)
                            Text {
                                objectName: "monitorChannelName" + channel.index
                                Layout.row: 0
                                Layout.column: 0
                                Layout.fillWidth: true
                                text: page.summary.labels[channel.index] || ""
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
                                color: page.cyan
                                font.pixelSize: page.px(18)
                                font.weight: Font.Medium
                                MouseArea {
                                    anchors.fill: parent
                                    enabled: !page.windSelected && page.summary.online && !page.monitor.logBusy
                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onClicked: channelSettings.openChannel(channel.index + 1, true)
                                }
                            }
                            HVButton {
                                objectName: "monitorChannelSettings" + channel.index
                                Layout.row: 0
                                Layout.column: 1
                                Layout.columnSpan: 2
                                Layout.alignment: Qt.AlignRight
                                visible: !page.windSelected
                                text: "Settings"
                                enabled: page.summary.online && !page.monitor.logBusy
                                implicitHeight: page.px(27)
                                implicitWidth: page.px(80)
                                font.pixelSize: page.px(13)
                                onClicked: channelSettings.openChannel(channel.index + 1, false)
                            }
                            Text {
                                objectName: "monitorChannelExtrema" + channel.index
                                Layout.row: 1
                                Layout.column: 0
                                Layout.fillWidth: true
                                visible: !page.windSelected
                                text: "Min " + page.valueText(channel.extrema.min)
                                      + "  •  Max " + page.valueText(channel.extrema.max)
                                color: page.muted
                                font.pixelSize: page.px(13)
                            }
                            Text {
                                objectName: "monitorChannelAlarm" + channel.index
                                Layout.row: page.windSelected ? 0 : 1
                                Layout.column: 1
                                Layout.alignment: Qt.AlignRight
                                text: channel.alarm
                                textFormat: Text.PlainText
                                visible: (text === "LOW" || text === "HIGH") && page.summary.connection === "Live"
                                color: page.windSelected ? "#e7c94a" : "#ef5757"
                                font.pixelSize: page.px(13)
                            }
                            Text {
                                objectName: "monitorChannelLive" + channel.index
                                Layout.row: page.windSelected ? 0 : 1
                                Layout.column: 2
                                Layout.alignment: Qt.AlignRight
                                text: channel.volts === null || channel.volts === undefined || page.summary.connection !== "Live"
                                      ? "Live " + page.valueText(null) : "Live " + page.valueText(channel.volts)
                                color: "#f0f2f1"
                                font.pixelSize: page.px(18)
                                font.weight: Font.Medium
                            }
                        }

                        PowerTrace {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            points: page.monitor.graphs[channel.index] || []
                            scaleFactor: page.scaleFactor
                            traceColor: page.cyan
                            unit: page.unit
                        }
                    }
                }
            }
        }

        Text {
            Layout.fillWidth: true
            text: page.summary.history + "  •  " + page.summary.hours + " h  •  "
                  + page.summary.samples.toLocaleString(Qt.locale(), "f", 0) + " samples"
                  + (page.summary.online ? ("  •  " + page.node + (page.summary.logging ? " logging" : " logging unavailable")) : "")
            color: page.muted
            font.pixelSize: page.px(13)
        }
    }

    Connections {
        target: page.monitor
        function onSummaryChanged() {
            logSettings.loadIfOnline()
        }
        function onCalibrationFinished(ok, channel, result, error) {
            if (!channelSettings.visible || channel !== channelSettings.channel)
                return
            if (!ok) {
                if (typeof result.name === "string") {
                    channelSettings.savedName = result.name
                    channelName.text = result.name
                }
                channelSettings.saving = false
                channelError.text = error
                return
            }
            if (channelSettings.saving) {
                channelSettings.close()
                return
            }
            channelSettings.savedName = result.name
            channelSettings.savedLow = result.low
            channelSettings.savedHigh = result.high
            channelName.text = result.name
            lowAlarm.text = String(result.low)
            highAlarm.text = String(result.high)
            const live = page.summary.connection === "Live" ? page.summary.voltages[channel - 1] : null
            const measured = result.actual ?? live
            actualVoltage.text = Number.isFinite(measured) ? measured.toFixed(2) : ""
            channelSettings.loaded = true
            if (channelSettings.focusName) {
                channelName.forceActiveFocus()
                channelName.selectAll()
            }
        }
        function onLogSettingsFinished(ok, hours, period, error) {
            if (!logSettings.visible)
                return
            if (!ok) {
                logSettings.saving = false
                logError.text = error
                return
            }
            if (logSettings.saving) {
                logSettings.close()
                return
            }
            duration.currentIndex = hours - 1
            interval.currentIndex = logSettings.periods.indexOf(period)
            logSettings.loaded = true
        }
    }

    Dialog {
        id: channelSettings
        objectName: "monitorCalibrationDialog"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: page.px(400)
        padding: page.px(16)
        modal: true
        closePolicy: Popup.NoAutoClose
        background: Panel {}
        property int channel: 1
        property bool loaded: false
        property bool saving: false
        property bool actualEdited: false
        property bool focusName: false
        property string savedName: ""
        property real savedLow: 0
        property real savedHigh: 0
        function openChannel(index, editName) {
            channel = index
            focusName = editName
            open()
        }
        onOpened: {
            loaded = false
            saving = false
            actualEdited = false
            channelName.clear()
            lowAlarm.clear()
            highAlarm.clear()
            actualVoltage.clear()
            channelError.text = ""
            if (!page.powerDevice.loadCalibration(channel))
                channelError.text = "Unable to read channel settings"
        }
        contentItem: ColumnLayout {
            spacing: page.px(10)
            Text {
                Layout.fillWidth: true
                text: (page.summary.labels[channelSettings.channel - 1] || "Channel " + channelSettings.channel)
                      + " Settings"
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: page.cyan
                font.pixelSize: page.px(19)
            }
            GridLayout {
                columns: 2
                enabled: channelSettings.loaded && !page.powerDevice.logBusy
                rowSpacing: page.px(8)
                columnSpacing: page.px(12)
                Text { Layout.fillWidth: true; text: "Channel Name"; color: page.muted }
                TextField {
                    id: channelName
                    objectName: "monitorCalibrationName"
                    Layout.preferredWidth: page.px(190)
                    selectByMouse: true
                }
                Text { Layout.fillWidth: true; text: "Low Voltage Alarm"; color: page.muted }
                TextField {
                    id: lowAlarm
                    objectName: "monitorCalibrationLow"
                    Layout.preferredWidth: page.px(115)
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    selectByMouse: true
                }
                Text { text: "High Voltage Alarm"; color: page.muted }
                TextField {
                    id: highAlarm
                    objectName: "monitorCalibrationHigh"
                    Layout.preferredWidth: page.px(115)
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    selectByMouse: true
                }
                Text { text: "Actual Voltage"; color: page.muted }
                TextField {
                    id: actualVoltage
                    objectName: "monitorCalibrationActual"
                    Layout.preferredWidth: page.px(115)
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    selectByMouse: true
                    onTextEdited: channelSettings.actualEdited = true
                }
            }
            Text {
                Layout.fillWidth: true
                text: "Enter the voltage measured at this channel. Clear Actual Voltage to reset its calibration."
                wrapMode: Text.WordWrap
                color: page.muted
            }
            Text {
                id: channelError
                Layout.fillWidth: true
                visible: text.length > 0
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
                color: "#ef5757"
            }
            Text {
                visible: page.powerDevice.logBusy
                text: channelSettings.saving ? "Saving settings…" : "Reading settings…"
                color: page.muted
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                HVButton {
                    objectName: "monitorCalibrationApply"
                    text: "Apply"
                    enabled: channelSettings.loaded && !page.powerDevice.logBusy
                    onClicked: {
                        const low = lowAlarm.text.trim()
                        const high = highAlarm.text.trim()
                        if (!low || !high || !Number.isFinite(Number(low)) || !Number.isFinite(Number(high))) {
                            channelError.text = "Enter valid low and high alarm voltages"
                            return
                        }
                        channelError.text = page.powerDevice.saveChannelSettings(channelSettings.channel,
                            channelName.text, channelName.text !== channelSettings.savedName,
                            Number(low), Number(high), channelSettings.actualEdited, actualVoltage.text,
                            Number(low) !== channelSettings.savedLow || Number(high) !== channelSettings.savedHigh)
                        channelSettings.saving = channelError.text === ""
                    }
                }
                HVButton {
                    objectName: "monitorCalibrationCancel"
                    text: "Cancel"
                    enabled: !page.powerDevice.logBusy
                    onClicked: channelSettings.close()
                }
            }
        }
    }

    Dialog {
        id: logSettings
        objectName: "monitorLogSettings"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: page.px(380)
        padding: page.px(16)
        modal: true
        closePolicy: Popup.NoAutoClose
        property bool loaded: false
        property bool loadRequested: false
        property bool saving: false
        readonly property bool addressEdited: !page.windSelected && pdmAddressField.text.trim() !== page.powerDevice.address
        readonly property bool canEditLog: loaded && page.summary.online && !page.monitor.logBusy && !addressEdited
        readonly property var periods: [250, 500, 1000, 2000]
        background: Panel {}
        function loadIfOnline() {
            if (opened && !loadRequested && page.summary.online && !page.monitor.logBusy) {
                loadRequested = page.monitor.loadLogSettings()
                if (!loadRequested)
                    logError.text = "Unable to read settings"
            }
        }
        onOpened: {
            loaded = false
            loadRequested = false
            saving = false
            logError.text = ""
            pdmAddressField.text = page.powerDevice.address
            interval.currentIndex = -1
            duration.currentIndex = -1
            loadIfOnline()
        }
        contentItem: ColumnLayout {
            spacing: page.px(10)
            Text {
                objectName: "monitorSettingsTitle"
                text: page.windSelected ? "WSI Log Settings" : "Settings"
                color: page.cyan
                font.pixelSize: page.px(19)
            }
            RowLayout {
                visible: !page.windSelected
                Text {
                    objectName: "monitorPdmAddressLabel"
                    Layout.fillWidth: true
                    text: "IP Address"
                    color: page.muted
                }
                TextField {
                    id: pdmAddressField
                    objectName: "pdmAddressField"
                    Layout.preferredWidth: page.px(148)
                    implicitHeight: page.px(34)
                    maximumLength: 15
                    selectByMouse: true
                    enabled: !logSettings.saving
                    color: "#f0f2f1"
                    font.pixelSize: page.px(14)
                    background: Rectangle {
                        color: "#101518"
                        radius: 4
                        border.color: pdmAddressField.activeFocus ? page.cyan : "#4a4f52"
                    }
                    onAccepted: if (logApply.enabled) logApply.clicked()
                }
            }
            RowLayout {
                enabled: logSettings.canEditLog
                Text { Layout.fillWidth: true; text: "Log Interval"; color: page.muted }
                ComboBox { id: interval; objectName: "monitorLogInterval"; Layout.preferredWidth: page.px(120); model: ["0.25 s", "0.5 s", "1.0 s", "2.0 s"] }
            }
            RowLayout {
                enabled: logSettings.canEditLog
                Text { Layout.fillWidth: true; text: "Log Duration"; color: page.muted }
                ComboBox {
                    id: duration
                    objectName: "monitorLogDuration"
                    Layout.preferredWidth: page.px(120)
                    model: Array.from({length: 12}, (_, i) => (i + 1) + " h")
                }
            }
            Text {
                Layout.fillWidth: true
                visible: logSettings.addressEdited
                text: "Apply the address to connect before editing log settings."
                wrapMode: Text.WordWrap
                color: page.muted
            }
            Text {
                id: logError
                objectName: "monitorLogError"
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
                color: "#ef5757"
                visible: text.length > 0
            }
            Text {
                text: logSettings.saving ? "Saving settings…" : "Reading settings…"
                visible: page.monitor.logBusy
                color: page.muted
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                layoutDirection: page.windSelected ? Qt.RightToLeft : Qt.LeftToRight
                HVButton {
                    id: logApply
                    objectName: "monitorLogApply"
                    text: "Apply"
                    enabled: !page.monitor.logBusy && (logSettings.addressEdited || logSettings.canEditLog)
                    onClicked: {
                        if (logSettings.addressEdited) {
                            const address = pdmAddressField.text.trim()
                            logError.text = address && address === page.windDevice.address
                                ? "Enter a separate address for each device"
                                : page.powerDevice.saveAddress(address)
                            if (logError.text === "")
                                logSettings.close()
                            return
                        }
                        logError.text = ""
                        logSettings.saving = page.monitor.saveLogSettings(duration.currentIndex + 1,
                            logSettings.periods[interval.currentIndex])
                        if (!logSettings.saving)
                            logError.text = "Unable to save settings"
                    }
                }
                HVButton {
                    objectName: "monitorLogCancel"
                    text: "Cancel"
                    enabled: !page.monitor.logBusy
                    onClicked: logSettings.close()
                }
            }
        }
    }
}
