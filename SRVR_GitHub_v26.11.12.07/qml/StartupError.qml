import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "components"

ApplicationWindow {
    id: window
    required property var startup
    objectName: "startupErrorWindow"
    visible: true
    width: 540
    height: layout.implicitHeight + 44
    minimumWidth: 420
    minimumHeight: layout.implicitHeight + 44
    title: "HV P2P SRVR"
    color: "#0f1316"
    font.family: "Helvetica Neue"

    ColumnLayout {
        id: layout
        anchors.fill: parent
        anchors.margins: 22
        spacing: 12

        Label {
            text: "SRVR could not start"
            color: "#f0f2f1"
            font.pixelSize: 22
        }
        TextEdit {
            Layout.fillWidth: true
            text: window.startup.detail
            textFormat: TextEdit.PlainText
            readOnly: true
            selectByMouse: true
            wrapMode: TextEdit.Wrap
            color: "#ef5757"
            font.pixelSize: 14
        }
        Label {
            Layout.fillWidth: true
            text: window.startup.instructions
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: "#aeb4b1"
            font.pixelSize: 14
        }
        Item { Layout.fillHeight: true }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            spacing: 8
            HVButton { text: "Quit"; onClicked: window.close() }
            HVButton {
                objectName: "startupRetry"
                text: "Retry"
                selected: true
                onClicked: window.startup.retry()
            }
        }
    }
}
