"""Visual calibration; screenshots stay in memory and never leave the computer."""
import mss
from PySide6.QtCore import Qt, QRectF, Signal, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel,
                              QMessageBox, QPushButton, QVBoxLayout, QWidget)

REGIONS = [("capture_region", "Server / queue text", "#d9ef61", "0,0.65,1,1"),
           ("team_region", "Faction icon", "#fb7598", "0.960,0.925,0.990,0.965"),
           ("score_region", "Scoreboard", "#68c8ff", "0.0169,0.9139,0.1497,0.9514")]


class CaptureCanvas(QWidget):
    changed = Signal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings, self.selected, self.pixmap, self.anchor = settings, 0, None, None
        self.setMinimumSize(640, 360)
        self.setMouseTracking(True)

    def image_rect(self):
        if self.pixmap is None:
            return QRectF()
        size = self.pixmap.size().scaled(self.size(), Qt.KeepAspectRatio)
        return QRectF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2,
                      size.width(), size.height())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0d1117"))
        if self.pixmap is None:
            painter.setPen(QColor("#aab5c5"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Capture your game screen to adjust the boxes")
            return
        box = self.image_rect()
        painter.drawPixmap(box.toRect(), self.pixmap)
        for index, (key, label, color, _) in enumerate(REGIONS):
            left, top, right, bottom = map(float, getattr(self.settings, key).split(","))
            rect = QRectF(box.x() + left * box.width(), box.y() + top * box.height(),
                          (right - left) * box.width(), (bottom - top) * box.height())
            painter.setPen(QPen(QColor(color), 3 if index == self.selected else 1))
            painter.drawRect(rect)
            painter.drawText(rect.x(), max(box.y() + 15, rect.y() - 5), label)

    def point(self, event):
        box = self.image_rect()
        return (max(0, min(1, (event.position().x() - box.x()) / box.width())),
                max(0, min(1, (event.position().y() - box.y()) / box.height())))

    def mousePressEvent(self, event):
        if self.pixmap is not None and event.button() == Qt.LeftButton and self.image_rect().contains(event.position()):
            self.anchor = self.point(event)

    def mouseReleaseEvent(self, event):
        if self.anchor is None:
            return
        x, y = self.point(event)
        left, right = sorted((x, self.anchor[0]))
        top, bottom = sorted((y, self.anchor[1]))
        self.anchor = None
        if (right - left) * self.image_rect().width() < 6 or (bottom - top) * self.image_rect().height() < 6:
            return
        value = f"{left:.5f},{top:.5f},{right:.5f},{bottom:.5f}"
        setattr(self.settings, REGIONS[self.selected][0], value)
        self.changed.emit(value)
        self.update()


class CaptureDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibrate game capture")
        self.resize(1000, 700)
        self.settings = settings
        layout = QVBoxLayout(self)
        label = QLabel("Select a box, then drag over the matching game text or icon.\n"
                       "Capture in 5 seconds gives you time to switch to WARDOGS. Screenshots stay on this PC.")
        label.setWordWrap(True)
        layout.addWidget(label)
        row = QHBoxLayout()
        self.selector = QComboBox()
        self.selector.addItems([r[1] for r in REGIONS])
        row.addWidget(self.selector)
        self.capture_button = QPushButton("Capture in 5 seconds")
        self.capture_button.clicked.connect(self.countdown)
        row.addWidget(self.capture_button)
        reset = QPushButton("Reset selected box")
        reset.clicked.connect(self.reset)
        row.addWidget(reset)
        layout.addLayout(row)
        self.canvas = CaptureCanvas(settings)
        self.selector.currentIndexChanged.connect(self.select)
        layout.addWidget(self.canvas, 1)
        self.hint = QLabel("Open the pause menu during a match to capture server details.")
        layout.addWidget(self.hint)
        done = QPushButton("Done")
        done.clicked.connect(self.accept)
        layout.addWidget(done)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.capture)

    def select(self, index):
        self.canvas.selected = index
        self.canvas.update()

    def reset(self):
        key, _, _, default = REGIONS[self.selector.currentIndex()]
        setattr(self.settings, key, default)
        self.canvas.update()

    def countdown(self):
        self.capture_button.setEnabled(False)
        self.hint.setText("Switch to your game now. Capturing in 5 seconds…")
        self.timer.start(5000)

    def capture(self):
        try:
            with mss.MSS() as capture:
                shot = capture.grab(capture.monitors[self.settings.monitor])
                image = QImage(shot.rgb, shot.width, shot.height, shot.width * 3, QImage.Format_RGB888).copy()
            self.canvas.pixmap = QPixmap.fromImage(image)
            self.canvas.update()
            self.hint.setText("Select a box above, then click and drag to replace it. Click Done and Save settings.")
            self.raise_()
            self.activateWindow()
        except Exception as error:
            QMessageBox.warning(self, "Capture failed", str(error))
        finally:
            self.capture_button.setEnabled(True)

    def done(self, result):
        self.timer.stop()
        super().done(result)
