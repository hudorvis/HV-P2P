import QtQuick 2.15
Rectangle {
    property bool active: false
    width: 15; height: 15; radius: 8
    color: active ? "#63d84e" : "#ed5454"
}
