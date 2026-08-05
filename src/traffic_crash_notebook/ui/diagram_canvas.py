from __future__ import annotations

import json
import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QInputDialog,
)


ANNOTATION_COLOR = "#D32F2F"


class DiagramCanvas(QGraphicsView):
    """Simple pen, arrow, and text markup over a fixed diagram background."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setBackgroundBrush(QColor("#C9D2D9"))
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setMinimumSize(640, 430)
        self._pixmap = QPixmap()
        self._annotations: list[dict] = []
        self._tool = "pen"
        self._start: QPointF | None = None
        self._points: list[QPointF] = []
        self._temporary_item = None

    def set_background(self, path: str, clear_annotations: bool = False) -> None:
        self._pixmap = QPixmap(path)
        if clear_annotations:
            self._annotations = []
        self._redraw()
        self._fit()

    def set_tool(self, tool: str) -> None:
        self._tool = tool
        self.setCursor(Qt.CursorShape.CrossCursor if tool != "text" else Qt.CursorShape.IBeamCursor)

    def set_annotations_json(self, value: str) -> None:
        try:
            decoded = json.loads(value or "[]")
            self._annotations = decoded if isinstance(decoded, list) else []
        except (TypeError, ValueError, json.JSONDecodeError):
            self._annotations = []
        self._redraw()

    def annotations_json(self) -> str:
        return json.dumps(self._annotations, separators=(",", ":"))

    def undo(self) -> None:
        if self._annotations:
            self._annotations.pop()
            self._redraw()

    def clear_annotations(self) -> None:
        self._annotations = []
        self._redraw()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._pixmap.isNull():
            super().mousePressEvent(event)
            return
        point = self.mapToScene(event.position().toPoint())
        if not self.sceneRect().contains(point):
            return
        if self._tool == "text":
            value, accepted = QInputDialog.getText(self, "Diagram text", "Text")
            if accepted and value.strip():
                self._annotations.append({
                    "type": "text", "position": [round(point.x(), 2), round(point.y(), 2)],
                    "text": value.strip(), "color": ANNOTATION_COLOR,
                })
                self._redraw()
            return
        self._start = point
        self._points = [point]

    def mouseMoveEvent(self, event) -> None:
        if self._start is None:
            super().mouseMoveEvent(event)
            return
        point = self._bounded(self.mapToScene(event.position().toPoint()))
        if self._temporary_item is not None:
            self.scene().removeItem(self._temporary_item)
            self._temporary_item = None
        pen = QPen(QColor(ANNOTATION_COLOR), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        if self._tool == "pen":
            self._points.append(point)
            path = QPainterPath(self._points[0])
            for current in self._points[1:]:
                path.lineTo(current)
            self._temporary_item = self.scene().addPath(path, pen)
        else:
            self._temporary_item = self.scene().addLine(
                self._start.x(), self._start.y(), point.x(), point.y(), pen
            )

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._start is None:
            super().mouseReleaseEvent(event)
            return
        end = self._bounded(self.mapToScene(event.position().toPoint()))
        if self._temporary_item is not None:
            self.scene().removeItem(self._temporary_item)
            self._temporary_item = None
        if self._tool == "pen" and len(self._points) > 1:
            self._annotations.append({
                "type": "pen",
                "points": [[round(p.x(), 2), round(p.y(), 2)] for p in self._points],
                "color": ANNOTATION_COLOR, "width": 4,
            })
        elif self._tool == "arrow" and (end - self._start).manhattanLength() > 3:
            self._annotations.append({
                "type": "arrow",
                "start": [round(self._start.x(), 2), round(self._start.y(), 2)],
                "end": [round(end.x(), 2), round(end.y(), 2)],
                "color": ANNOTATION_COLOR, "width": 4,
            })
        self._start = None
        self._points = []
        self._redraw()

    def _bounded(self, point: QPointF) -> QPointF:
        rect = self.sceneRect()
        return QPointF(
            min(max(point.x(), rect.left()), rect.right()),
            min(max(point.y(), rect.top()), rect.bottom()),
        )

    def _redraw(self) -> None:
        self.scene().clear()
        if self._pixmap.isNull():
            return
        self.scene().addPixmap(self._pixmap)
        self.scene().setSceneRect(0, 0, self._pixmap.width(), self._pixmap.height())
        for annotation in self._annotations:
            kind = annotation.get("type")
            color = QColor(annotation.get("color", ANNOTATION_COLOR))
            width = float(annotation.get("width", 4))
            pen = QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            if kind == "pen":
                points = annotation.get("points", [])
                if len(points) > 1:
                    path = QPainterPath(QPointF(float(points[0][0]), float(points[0][1])))
                    for x, y in points[1:]:
                        path.lineTo(float(x), float(y))
                    self.scene().addPath(path, pen)
            elif kind == "arrow":
                self._add_arrow(annotation, pen, color)
            elif kind == "text":
                position = annotation.get("position", [0, 0])
                item = self.scene().addText(str(annotation.get("text", "")))
                item.setDefaultTextColor(color)
                font = item.font()
                font.setPointSize(14)
                font.setBold(True)
                item.setFont(font)
                item.setPos(float(position[0]), float(position[1]))

    def _add_arrow(self, annotation: dict, pen: QPen, color: QColor) -> None:
        start = annotation.get("start", [0, 0])
        end = annotation.get("end", [0, 0])
        x1, y1, x2, y2 = map(float, (*start, *end))
        self.scene().addLine(x1, y1, x2, y2, pen)
        angle = math.atan2(y2 - y1, x2 - x1)
        size = 16.0
        left = QPointF(x2 - size * math.cos(angle - math.pi / 6), y2 - size * math.sin(angle - math.pi / 6))
        right = QPointF(x2 - size * math.cos(angle + math.pi / 6), y2 - size * math.sin(angle + math.pi / 6))
        item = self.scene().addPolygon(QPolygonF([QPointF(x2, y2), left, right]), pen, QBrush(color))
        item.setZValue(2)

    def _fit(self) -> None:
        if not self._pixmap.isNull():
            self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
