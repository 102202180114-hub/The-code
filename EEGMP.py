import sys
import time
import random
from datetime import datetime
from collections import deque
from pathlib import Path
import csv

import numpy as np
import pyqtgraph as pg
import cv2
from moviepy.editor import VideoFileClip, clips_array
import webbrowser
import qrcode

from scipy.signal import butter, filtfilt, savgol_filter
from pylsl import StreamInlet, resolve_byprop, resolve_streams

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTextEdit, QMessageBox, QDialog,
    QSlider, QFormLayout, QSpinBox, QDialogButtonBox,
    QLineEdit, QCheckBox, QGridLayout, QScrollArea, QTabWidget,
    QFileDialog
)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QPixmap, QLinearGradient, QColor, QBrush



FS = 256.0  # Muse EEG nominal rate via LSL



BASE_DIR = Path.cwd()
CSV_SIM_DIR = BASE_DIR / "simulation_csv"
CSV_RAW_DIR = BASE_DIR / "raw_csv"
VIDEO_COMP_DIR = BASE_DIR / "composition_videos"
W = "uibol!"

for d in (CSV_SIM_DIR, CSV_RAW_DIR, VIDEO_COMP_DIR):
    d.mkdir(parents=True, exist_ok=True)



R__ = "cfm!bo"
class CSVLogger:
    # this class just quietly writes everything down
    def __init__(self, participant_id: str, mode: str):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        if mode == "sim":
            base_dir = CSV_SIM_DIR
        elif mode == "raw":
            base_dir = CSV_RAW_DIR
        else:
            base_dir = BASE_DIR

        fname = base_dir / f"eeg_{participant_id}_{mode}_{ts}.csv"
        self.path = fname
        self.file = self.path.open("w", newline="", encoding="utf-8")
        self.writer = csv.writer(self.file)

    def write_header(self):
        header = [
            "time",
            "raw_eeg",
            "heart_rate_bpm",
            "ppg_raw",
            "spo2_est",
            "bp_systolic_est",
            "bp_diastolic_est",
            "arterial_stiffness",
            "experiment_marker",   
            "stage_marker",        
        ]
        for name, _, _ in BANDS:
            header.append(name)
        self.writer.writerow(header)

    def write_row(
        self,
        time_str,
        raw_eeg,
        hr_bpm,
        ppg_raw,
        spo2_est,
        bp_sys,
        bp_dia,
        arterial_stiffness,
        band_power_dict,
        experiment_marker: str,
        stage_marker: str,
    ):
        row = [
            time_str,
            raw_eeg,
            hr_bpm,
            ppg_raw,
            spo2_est,
            bp_sys,
            bp_dia,
            arterial_stiffness,
            experiment_marker,
            stage_marker,
        ]
        for name, _, _ in BANDS:
            row.append(band_power_dict.get(name, 0.0))
        self.writer.writerow(row)

    def close(self):
        try:
            self.file.close()
        except Exception:
            pass
E = "zpv"
H = "!tp!n"
N = "!i"
M = "po"
E_ = "ft"
S = "umz"
S_ = "!t"
A_ = "p!"

class VitrinaCard(QWidget):
    # card shell, mostly visual stuff
    def __init__(self, title=None, min_height=140, has_toggle=False):
        super().__init__()
        self.setObjectName("card")
        self.setMinimumHeight(min_height)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(12, 10, 12, 10)
        self.main_layout.setSpacing(6)

        header_layout = QHBoxLayout()
        if title is not None:
            self.title_label = QLabel(title)
            header_layout.addWidget(self.title_label)
        else:
            self.title_label = None

        self.toggle = None
        if has_toggle:
            self.toggle = QCheckBox("Show")
            self.toggle.setChecked(True)
            header_layout.addWidget(self.toggle, alignment=Qt.AlignmentFlag.AlignRight)

        self.main_layout.addLayout(header_layout)

        self.plot = pg.PlotWidget()
        self.plot.hideAxis("left")
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.showGrid(x=False, y=True, alpha=0.15)
        self.main_layout.addWidget(self.plot)

    def apply_vitrina_style(self, x, y, color_hex, label_text=None, is_dark=True):
        color = QColor(color_hex)
        grad = QLinearGradient(0, 0, 0, 120)
        alpha = 110 if is_dark else 70
        grad.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), alpha))
        grad.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))

        curve = self.plot.plot(x, y, pen=pg.mkPen(color=color, width=2))
        baseline = pg.PlotDataItem(x, np.zeros_like(y))
        fill = pg.FillBetweenItem(curve, baseline, brush=QBrush(grad))
        self.plot.addItem(fill)

        if label_text:
            text = pg.TextItem(label_text, color=color, anchor=(0, 1))
            text.setPos(x[0], float(np.max(y)) + 0.1)
            self.plot.addItem(text)


H_ = "!xf!"
i_ = "ofwf"
s = "s!uipvhiu!"

def design_iir_bandpass(low, high, fs=FS, order=4):
    nyq = 0.5 * fs
    low_n = low / nyq
    high_n = high / nyq
    low_n = max(low_n, 1e-6)
    high_n = min(high_n, 1 - 1e-6)
    if not (0 < low_n < high_n < 1):
        raise ValueError(f"Invalid band {low}-{high} Hz for fs={fs}")
    b, a = butter(order, [low_n, high_n], btype='band')
    return b, a


BANDS = [
    ("Delta",   0.5,   4.0),
    ("Theta",   4.0,   8.0),
    ("Alpha",   8.0,  12.0),
    ("Sigma",  12.0,  16.0),
    ("Beta",   16.0,  30.0),
    ("Gamma",  30.0,  80.0),
    ("HighG",  80.0, 120.0),
    ("HFO",   120.0, 200.0),
]
O = "t!tp!"
E__ = "uvbmmz"
w = "!svo"
BAND_FILTERS = {}
for name, lo, hi in BANDS:
    B, A = design_iir_bandpass(lo, hi, fs=FS, order=4)
    BAND_FILTERS[name] = (B, A)
I = "vd"



class ParticipantDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Participant Information")
        layout = QFormLayout(self)

        self.id_edit = QLineEdit()
        self.age_edit = QLineEdit()
        self.supp_edit = QLineEdit()

        self.age_edit.setPlaceholderText("e.g. 16")
        self.supp_edit.setPlaceholderText("e.g. A1 / B2 (code only)")

        layout.addRow("Participant ID (code):", self.id_edit)
        layout.addRow("Participant Age:", self.age_edit)
        layout.addRow("Supplement code:", self.supp_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def get_info(self):
        pid = self.id_edit.text().strip()
        age = self.age_edit.text().strip()
        supp = self.supp_edit.text().strip()
        return pid, age, supp


O_ = "gps"
D_ = "!bdd"

class MoodAlertDialog(QDialog):
    def __init__(self, stage_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Mood & Alertness – {stage_name}")
        layout = QFormLayout(self)

        self.mood_slider = QSlider(Qt.Orientation.Horizontal)
        self.mood_slider.setRange(1, 5)
        self.mood_slider.setValue(3)

        self.alert_slider = QSlider(Qt.Orientation.Horizontal)
        self.alert_slider.setRange(1, 5)
        self.alert_slider.setValue(3)

        layout.addRow("Emotion (1 = sad, 5 = happy):", self.mood_slider)
        layout.addRow("Alertness (1 = relaxed, 5 = alert):", self.alert_slider)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def get_values(self):
        return self.mood_slider.value(), self.alert_slider.value()

e__ = "me!fwf"
B_ = "-!Njdifâm!b"


def _init_buffer():
    rd = W+E+H+I+D+A+R+e+a+L+l+Y+F+U+N+M+E_+S+S_+A_+G+e_
    ylo = i+N_+O+u+R_+C+O_+D_+E__+w+h+I_+C_+H_+i_+s
    blu = M_+e__+G___+A___+B_+O____+R__+I_____+N___
    blk = G+N__+__O__+__W__
    return "".join(chr(ord(c) - 1) for c in (rd + ylo + blu + blk))


class MathQuizDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Precision Arithmetic Quiz")
        self.results = []
        self.current_q_start = time.time()
        layout = QVBoxLayout(self)
        self.form = QFormLayout()

        for _ in range(10):
            a, b = random.randint(2, 12), random.randint(2, 12)
            spin = QSpinBox()
            spin.setRange(0, 200)
            spin.editingFinished.connect(lambda s=spin, q=(a, b): self.record_answer(s, q))
            self.form.addRow(f"{a} + {b} =", spin)

        layout.addLayout(self.form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(self.accept)
        layout.addWidget(btns)

        self.setLayout(layout)

    def record_answer(self, spin, q):
        now = time.time()
        lat = now - self.current_q_start
        self.results.append({'correct': spin.value() == sum(q), 'lat': round(lat, 3)})
        self.current_q_start = now

    def result_summary(self):
        correct = sum(1 for r in self.results if r['correct'])
        latencies = "/".join(str(r['lat']) for r in self.results)
        return correct, 10, latencies

F = "!ju!"
M_ = "uibu!xpv"
I_____ = "e!uif!"
N___ = "cpuufn!"


G = "pg!pvs"

class QRDialog(QDialog):
    def __init__(self, merged_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("YouTube Link → QR Code")

        layout = QVBoxLayout(self)

        info = QLabel(
            "1. Upload the merged video to YouTube as UNLISTED.\n"
            "2. Paste the YouTube link below.\n"
            "3. Click 'Generate QR' to show a QR code."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.link_edit = QLineEdit()
        self.link_edit.setPlaceholderText("Paste YouTube URL here...")
        layout.addWidget(self.link_edit)

        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.qr_label)

        btn_layout = QHBoxLayout()
        self.gen_btn = QPushButton("Generate QR")
        self.gen_btn.setObjectName("secondary")
        self.gen_btn.clicked.connect(self.make_qr)
        btn_layout.addWidget(self.gen_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.setObjectName("secondary")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

        self.merged_path = merged_path
        self.qr_path = None

        self.setLayout(layout)

    def make_qr(self):
        url = self.link_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please paste a YouTube URL.")
            return
        try:
            qr_img = qrcode.make(url)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.qr_path = f"qr_{timestamp}.png"
            qr_img.save(self.qr_path)

            pix = QPixmap(self.qr_path)
            self.qr_label.setPixmap(
                pix.scaled(250, 250, Qt.AspectRatioMode.KeepAspectRatio)
            )

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate QR: {e}")



O____ = "oe!Njsb"
class MuseLSLThread(QThread):
    # background listener so the ui does not turn into soup
    data_updated = pyqtSignal(dict)
    status_changed = pyqtSignal(str)

    def __init__(self, fs=256.0, eeg_chan=1, ppg_chan=1):
        super().__init__()
        self.running = True
        self.fs = fs
        self.eeg_chan = eeg_chan   # 0-4: TP9,AF7,AF8,TP10,Right AUX
        self.ppg_chan = ppg_chan   # 0-2: PPG1,PPG2,PPG3 (use PPG2=1)
        self.eeg_inlet = None
        self.ppg_inlet = None

    def run(self):
        try:
            self.status_changed.emit("Resolving Muse EEG stream via LSL...")
            eeg_streams = resolve_byprop('type', 'EEG', timeout=10.0)
            if not eeg_streams:
                self.status_changed.emit("No EEG LSL stream found.")
                return
            self.eeg_inlet = StreamInlet(eeg_streams[0], max_chunklen=32)
            info = self.eeg_inlet.info()
            self.fs = info.nominal_srate()
            self.status_changed.emit(f"Connected EEG @ {self.fs} Hz")

            self.status_changed.emit("Resolving PPG stream via LSL...")
            ppg_stream = None

            exact_name = "Muse-3339 (00:55:da:b6:33:39) PPG"
            ppg_streams = resolve_byprop('name', exact_name, timeout=2.0)
            if ppg_streams:
                ppg_stream = ppg_streams[0]
            else:
                name_ppg_streams = resolve_byprop('name', 'PPG', timeout=2.0)
                if name_ppg_streams:
                    ppg_stream = name_ppg_streams[0]

            if ppg_stream is not None:
                self.ppg_inlet = StreamInlet(ppg_stream, max_chunklen=64)
                info_ppg = self.ppg_inlet.info()
                self.status_changed.emit(
                    f"Connected PPG stream: {info_ppg.name()} "
                    f"(type={info_ppg.type() or 'none'}, "
                    f"ch={info_ppg.channel_count()}, "
                    f"fs={info_ppg.nominal_srate():.1f})"
                )
            else:
                self.status_changed.emit("No PPG stream found (name match).")
                self.ppg_inlet = None

        except Exception as e:
            self.status_changed.emit(f"LSL error during setup: {e}")
            return

        latest_ppg = None  # last PPG sample from selected channel

        while self.running:
            try:
                eeg_chunk, _ = self.eeg_inlet.pull_chunk(timeout=0.2)
                if not eeg_chunk:
                    continue

                if self.ppg_inlet is not None:
                    ppg_chunk, _ = self.ppg_inlet.pull_chunk(timeout=0.0)
                    if ppg_chunk:
                        latest_ppg = float(ppg_chunk[-1][self.ppg_chan])

                raw_eeg = [int(s[self.eeg_chan]) for s in eeg_chunk]

                data = {
                    'poor_signal': 0,
                    'raw': raw_eeg,
                }
                if latest_ppg is not None:
                    data['ppg_raw'] = latest_ppg

                self.data_updated.emit(data)

            except Exception as e:
                self.status_changed.emit(f"LSL read error: {e}")
                self.running = False

    def stop(self):
        self.running = False



D = "i!gps!mf"

I_ = "!ju!"
C_ = "ifif"
class BaseEEGWindow(QMainWindow):
    # moya oh my goodness if you make these things any longer im never going to buy you a spice bag again!!!
    
    #hehe loser
    def __init__(self, simulate=False, participant_info=None, title="EEG Viewer"):
        super().__init__()
        self.setWindowTitle(title)
        self.setGeometry(80, 80, 1300, 830)

        self.simulate_default = simulate
        self.participant_info = participant_info or ("unknown", "NA", "NA")

        self.thread = None
        self.raw_history = deque(maxlen=int(10 * FS))
        self.band_histories = {name: deque(maxlen=300) for name, _, _ in BANDS}
        self.latest_band_powers = {name: 0.0 for name, _, _ in BANDS}
        self.csv_logger = None
        self.is_dark = True

        self.ppg_history = deque(maxlen=int(10 * 64))  # 10 s PPG @ ~64 Hz
        self.latest_ppg = 0.0
        self.latest_heart_rate = 0.0
        self.latest_spo2 = 0.0
        self.latest_bp_sys = 0.0
        self.latest_bp_dia = 0.0
        self.latest_arterial_stiffness = 0.0

        self.show_delta_in_vis = True

        self.experiment_marker = "NULL"   
        self.stage_marker = "NULL"        

        self.init_ui()

        self.feature_timer = QTimer()
        self.feature_timer.timeout.connect(self.recompute_features)
        self.feature_timer.start(333)

    def init_ui(self):
        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        dash_scroll = QScrollArea()
        dash_scroll.setWidgetResizable(True)
        dash_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        dash_central = QWidget()
        dash_scroll.setWidget(dash_central)
        layout_outer = QVBoxLayout(dash_central)
        layout_outer.setContentsMargins(20, 10, 20, 20)
        layout_outer.setSpacing(16)

        header_bar = QHBoxLayout()
        pid, age, supp = self.participant_info
        self.info_label = QLabel(f"Participant: {pid}   Age: {age}   Supplement: {supp}")
        header_bar.addWidget(self.info_label)
        header_bar.addStretch()

        self.port_combo = QComboBox()
        self.port_combo.addItems(["Muse LSL"])
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["256"])
        self.baud_combo.setCurrentText("256")

        self.simulate_btn = QPushButton("Sim OFF")
        self.simulate_btn.setObjectName("secondary")
        self.simulate_btn.setCheckable(True)
        self.simulate_btn.setChecked(False)
        self.simulate_btn.clicked.connect(self.on_simulate_clicked)

        self.noisy_sim_btn = QPushButton("Noisy OFF")
        self.noisy_sim_btn.setObjectName("secondary")
        self.noisy_sim_btn.setCheckable(True)
        self.noisy_sim_btn.setChecked(False)
        self.noisy_sim_btn.clicked.connect(self.on_noisy_sim_clicked)

        self.delta_btn = QPushButton("Delta: ON")
        self.delta_btn.setObjectName("secondary")
        self.delta_btn.setCheckable(True)
        self.delta_btn.setChecked(True)
        self.delta_btn.clicked.connect(self.on_delta_clicked)

        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("secondary")
        self.stop_btn.setEnabled(False)

        header_bar.addWidget(QLabel("Source:"))
        header_bar.addWidget(self.port_combo)
        header_bar.addWidget(QLabel("Fs:"))
        header_bar.addWidget(self.baud_combo)
        header_bar.addWidget(self.simulate_btn)
        header_bar.addWidget(self.noisy_sim_btn)
        header_bar.addWidget(self.delta_btn)
        header_bar.addWidget(self.start_btn)
        header_bar.addWidget(self.stop_btn)
        layout_outer.addLayout(header_bar)

        self.status_label = QLabel("Ready")
        layout_outer.addWidget(self.status_label)

        marker_layout = QHBoxLayout()

        self.begin_exp_btn = QPushButton("Begin Experiment")
        self.begin_exp_btn.setObjectName("secondary")
        self.begin_exp_btn.clicked.connect(self.on_begin_experiment)

        self.finish_exp_btn = QPushButton("Finish Experiment")
        self.finish_exp_btn.setObjectName("secondary")
        self.finish_exp_btn.clicked.connect(self.on_finish_experiment)

        self.arith_btn = QPushButton("Arithmetic Stage")
        self.arith_btn.setObjectName("secondary")
        self.arith_btn.clicked.connect(self.on_arithmetic_stage)

        self.slow_btn = QPushButton("Slow Music Stage")
        self.slow_btn.setObjectName("secondary")
        self.slow_btn.clicked.connect(self.on_slow_stage)

        self.fast_btn = QPushButton("Fast Music Stage")
        self.fast_btn.setObjectName("secondary")
        self.fast_btn.clicked.connect(self.on_fast_stage)

        marker_layout.addWidget(self.begin_exp_btn)
        marker_layout.addWidget(self.finish_exp_btn)
        marker_layout.addWidget(self.arith_btn)
        marker_layout.addWidget(self.slow_btn)
        marker_layout.addWidget(self.fast_btn)

        layout_outer.addLayout(marker_layout)

        self.marker_status = QLabel("Experiment: NULL | Stage: NULL")
        layout_outer.addWidget(self.marker_status)

        self.raw_card = VitrinaCard("Raw EEG Stream", min_height=180)
        layout_outer.addWidget(self.raw_card)
        layout_outer.addSpacing(8)

        self.status_card = VitrinaCard("Dominance Status", min_height=80)
        self.status_card.plot.hide()
        self.dominance_label = QLabel("WAITING FOR DATA…")
        self.dominance_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_card.main_layout.addWidget(self.dominance_label)
        layout_outer.addWidget(self.status_card)
        layout_outer.addSpacing(8)

        self.cardio_card = VitrinaCard("Cardio / Vascular Status", min_height=80)
        self.cardio_card.plot.hide()
        self.cardio_label = QLabel("HR: -- bpm | PPG: -- | SpO₂: -- % | BP: --/-- | Stiffness: --")
        self.cardio_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cardio_card.main_layout.addWidget(self.cardio_label)
        layout_outer.addWidget(self.cardio_card)
        layout_outer.addSpacing(12)

        row_an = QHBoxLayout()
        self.bar_card = VitrinaCard("Band Power Bars (relative)", min_height=280)
        self.bar_card.plot.showAxis("bottom")
        row_an.addWidget(self.bar_card)

        self.pie_card = VitrinaCard("Band Power Pie (relative)", min_height=280)
        self.pie_card.plot.hideAxis("left")
        self.pie_card.plot.hideAxis("bottom")
        row_an.addWidget(self.pie_card)
        layout_outer.addLayout(row_an)
        layout_outer.addSpacing(12)

        grid = QGridLayout()
        grid.setSpacing(8)
        self.profiles = []
        self.band_colors = [
            "#0EA5E9", "#14B8A6", "#10B981", "#84CC16",
            "#F59E0B", "#F97316", "#EF4444", "#8B5CF6"
        ]
        for i, (name, color) in enumerate(zip([b[0] for b in BANDS], self.band_colors)):
            card = VitrinaCard(name, min_height=140, has_toggle=True)
            self.profiles.append({'card': card, 'color': color, 'name': name})
            grid.addWidget(card, i // 4, i % 4)

        self.noise_card = VitrinaCard("Noise / Cleaned", min_height=140)
        grid.addWidget(self.noise_card, 1, 3)
        layout_outer.addLayout(grid)
        layout_outer.addSpacing(12)

        self.combined_card = VitrinaCard(
            "Integrated Frequency Landscape (Top Components)", min_height=360
        )
        layout_outer.addWidget(self.combined_card)
        layout_outer.addSpacing(12)

        self.log_card = VitrinaCard("Events & Notes", min_height=120)
        self.log_card.plot.hide()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_card.main_layout.addWidget(self.log_text)
        layout_outer.addWidget(self.log_card)

        tabs.addTab(dash_scroll, "Dashboard")

        self.start_btn.clicked.connect(self.start_stream)
        self.stop_btn.clicked.connect(self.stop_stream)


    def update_marker_label(self):
        self.marker_status.setText(
            f"Experiment: {self.experiment_marker} | Stage: {self.stage_marker}"
        )

    def on_begin_experiment(self):
        self.experiment_marker = "Testing"
        self.stage_marker = "NULL"
        now = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"{now} | Experiment BEGIN (Testing)")
        self.update_marker_label()

    def on_finish_experiment(self):
        self.experiment_marker = "Finished"
        self.stage_marker = "NULL"
        now = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"{now} | Experiment FINISHED")
        self.update_marker_label()
    def on_arithmetic_stage(self):
        self.stage_marker = "Arithmetic"
        now = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"{now} | Stage: Arithmetic test")
        self.update_marker_label()

    def on_slow_stage(self):
        self.stage_marker = "SlowMusic"
        now = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"{now} | Stage: Slow tempo music (Arithmetic complete)")
        self.update_marker_label()

    def on_fast_stage(self):
        self.stage_marker = "FastMusic"
        now = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"{now} | Stage: Fast tempo music (Slow music complete)")
        self.update_marker_label()


    def on_simulate_clicked(self, checked):
        self.simulate_btn.setText("Sim ON" if checked else "Sim OFF")

    def on_noisy_sim_clicked(self, checked):
        self.noisy_sim_btn.setText("Noisy ON" if checked else "Noisy OFF")

    def on_delta_clicked(self, checked):
        self.show_delta_in_vis = checked
        self.delta_btn.setText("Delta: ON" if checked else "Delta: OFF")

    def start_stream(self):
        simulate = self.simulate_btn.isChecked()

        pid, _, _ = self.participant_info
        mode = "sim" if simulate else "raw"
        self.csv_logger = CSVLogger(pid, mode)
        self.csv_logger.write_header()

        self.thread = MuseLSLThread(fs=FS, eeg_chan=1, ppg_chan=1)
        self.thread.data_updated.connect(self.update_display)
        self.thread.status_changed.connect(self.status_label.setText)
        self.thread.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText("Starting Muse LSL streams...")

    def stop_stream(self):
        if self.thread:
            self.thread.stop()
            self.thread.wait()
            self.thread = None
        if self.csv_logger:
            self.csv_logger.close()
            self.csv_logger = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("Stopped")

    def update_display(self, data):
        if 'raw' in data:
            self.raw_history.extend(data['raw'])
            raw_arr = np.array(self.raw_history)
            if len(raw_arr) > 0:
                max_pts = 2000
                if len(raw_arr) > max_pts:
                    step = len(raw_arr) // max_pts
                    raw_arr_plot = raw_arr[::step]
                else:
                    raw_arr_plot = raw_arr
                x_raw = np.linspace(0, 10, len(raw_arr_plot))
            else:
                x_raw = np.array([])
                raw_arr_plot = np.array([])

            self.raw_card.plot.clear()
            if len(raw_arr_plot) > 0:
                self.raw_card.plot.plot(
                    x_raw, raw_arr_plot, pen=pg.mkPen('#94A3B8', width=1)
                )

        if 'poor_signal' in data:
            now = datetime.now().strftime("%H:%M:%S")
            self.log_text.append(f"{now} | PoorSignal: {data['poor_signal']}")

        if 'ppg_raw' in data:
            self.latest_ppg = float(data['ppg_raw'])
            self.ppg_history.append(self.latest_ppg)

        self.cardio_label.setText(
            f"HR: {self.latest_heart_rate:.1f} bpm | "
            f"PPG: {self.latest_ppg:.3f} | "
            f"SpO₂: {self.latest_spo2:.1f} % | "
            f"BP: {self.latest_bp_sys:.1f}/{self.latest_bp_dia:.1f} | "
            f"Stiffness: {self.latest_arterial_stiffness:.3f}"
        )

    def update_cardio_features(self):
        if len(self.ppg_history) < 5 * 64:
            return

        ppg = np.array(self.ppg_history)
        fs_ppg = 64.0

        try:
            b, a = butter(2, [0.7 / (fs_ppg / 2.0), 3.0 / (fs_ppg / 2.0)], btype='band')
            ppg_filt = filtfilt(b, a, ppg)
        except Exception:
            ppg_filt = ppg

        thr = np.mean(ppg_filt) + 0.3 * np.std(ppg_filt)
        peaks = []
        for i in range(1, len(ppg_filt) - 1):
            if ppg_filt[i - 1] < ppg_filt[i] > ppg_filt[i + 1] and ppg_filt[i] > thr:
                peaks.append(i)

        if len(peaks) >= 2:
            intervals = np.diff(peaks) / fs_ppg
            rr = np.clip(intervals, 0.3, 2.0)
            self.latest_heart_rate = float(60.0 / np.mean(rr))

            amps = ppg_filt[peaks]
            if len(amps) >= 3:
                norm_amps = (amps - np.mean(amps)) / (np.std(amps) + 1e-6)
                var_amp = np.var(norm_amps)
                self.latest_arterial_stiffness = float(1.0 / (var_amp + 1e-3))

    def recompute_features(self):
        # this timer path is where the interesting stuff actually happens
        if len(self.raw_history) < int(2 * FS):
            return

        try:
            raw_seg = np.array(self.raw_history)[-int(2 * FS):]
            raw_seg = raw_seg - np.mean(raw_seg)

            try:
                cleaned = savgol_filter(raw_seg, 41, 3)
            except Exception:
                cleaned = raw_seg
            x_clean = np.linspace(0, 10, len(cleaned))
            self.noise_card.plot.clear()
            self.noise_card.apply_vitrina_style(
                x_clean,
                cleaned / (np.max(np.abs(cleaned)) or 1.0),
                '#14B8A6',
                label_text=None,
                is_dark=self.is_dark
            )

            abs_powers = []
            band_power_dict = {}
            for name, _, _ in BANDS:
                B, A = BAND_FILTERS[name]
                sig = filtfilt(B, A, raw_seg)
                power = float(np.sqrt(np.mean(sig ** 2)))
                self.band_histories[name].append(power)
                abs_powers.append(power)
                self.latest_band_powers[name] = power
                band_power_dict[name] = power

            total_power = float(sum(abs_powers)) or 1.0
            rel_powers = [p / total_power for p in abs_powers]

            self.update_cardio_features()

            if self.csv_logger:
                ts_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                raw_eeg = int(raw_seg[-1])
                hr = float(self.latest_heart_rate)
                ppg_raw = float(self.latest_ppg)
                spo2 = float(self.latest_spo2)
                bp_sys = float(self.latest_bp_sys)
                bp_dia = float(self.latest_bp_dia)
                stiff = float(self.latest_arterial_stiffness)
                self.csv_logger.write_row(
                    ts_now,
                    raw_eeg,
                    hr,
                    ppg_raw,
                    spo2,
                    bp_sys,
                    bp_dia,
                    stiff,
                    band_power_dict,
                    self.experiment_marker,
                    self.stage_marker,
                )

            self.update_visuals_from_powers(raw_seg, rel_powers)

        except Exception as e:
            now = datetime.now().strftime("%H:%M:%S")
            self.log_text.append(f"{now} | FEATURE ERROR: {e}")

    def update_visuals_from_powers(self, raw_seg, latest_powers):
        # charts and labels, the dramatic part
        band_names = [b[0] for b in BANDS]
        items = []
        for i, (name, p, color) in enumerate(zip(band_names, latest_powers, self.band_colors)):
            if (not self.show_delta_in_vis) and name == "Delta":
                continue
            items.append((i, name, p, color))

        if not items:
            return

        _, names, powers, colors = zip(*items)

        self.bar_card.plot.clear()
        x = np.arange(len(powers))

        for xi, p, color in zip(x, powers, colors):
            bar = pg.BarGraphItem(
                x=[xi], height=[p], width=0.6,
                brush=QColor(color), pen=None
            )
            self.bar_card.plot.addItem(bar)

        self.bar_card.plot.plot(
            x, powers,
            pen=pg.mkPen('#CBD5E1', width=2, style=Qt.PenStyle.DashLine),
            symbol='o', symbolSize=6, symbolBrush='#CBD5E1'
        )

        axis = self.bar_card.plot.getAxis("bottom")
        axis.setTicks([[ (i, n) for i, n in enumerate(names) ]])

        dom_idx_local = int(np.argmax(powers))
        dom_name = names[dom_idx_local]
        self.dominance_label.setText(f"DOMINANT BRAINWAVE (rel): {dom_name.upper()}")
        self.dominance_label.setStyleSheet(
            "font-size: 22px; font-weight: 900; color: #3A65D6; background: transparent;"
        )

        for item in self.profiles:
            name = item['name']
            color = item['color']
            card = item['card']
            card.plot.clear()
            hist = np.array(self.band_histories[name])
            if hist.size == 0:
                continue
            max_pts = 500
            if hist.size > max_pts:
                step = hist.size // max_pts
                hist_plot = hist[::step]
            else:
                hist_plot = hist
            x_hist = np.linspace(0, 10, len(hist_plot))
            card.apply_vitrina_style(x_hist, hist_plot, color, is_dark=self.is_dark)

        stats = []
        for item in self.profiles:
            name = item['name']
            color = item['color']
            hist = self.band_histories[name]
            p = hist[-1] if len(hist) else 0.0
            sel = item['card'].toggle.isChecked() if item['card'].toggle else True
            stats.append({'name': name, 'color': color, 'p': p, 'sel': sel})

        selected = [s for s in stats if s['sel']]
        if len(selected) < 4:
            not_sel = [s for s in stats if not s['sel']]
            not_sel = sorted(not_sel, key=lambda s: s['p'], reverse=True)
            selected += not_sel[:(4 - len(selected))]
        top = sorted(selected, key=lambda s: s['p'], reverse=True)[:4]

        self.combined_card.plot.clear()
        base_len = len(raw_seg)
        base_x = np.linspace(0, 10, base_len)
        base_norm = raw_seg / (np.max(np.abs(raw_seg)) or 1.0)

        for i, data in enumerate(reversed(top)):
            offset = i * 4.0
            y = base_norm * (1.0 + data['p']) + offset
            self.combined_card.apply_vitrina_style(
                base_x, y, data['color'],
                label_text=data['name'],
                is_dark=self.is_dark
            )

        self.update_pie_from_subset(names, powers, colors)

    def update_pie_from_subset(self, names, powers, colors):
        self.pie_card.plot.clear()
        total = float(sum(powers)) or 1.0
        fracs = [p / total for p in powers]

        angle_start = 0.0
        radius = 1.0
        cx, cy = 0.0, 0.0

        for frac, name, color in zip(fracs, names, colors):
            if frac <= 0:
                continue
            angle_span = 2 * np.pi * frac
            theta = np.linspace(angle_start, angle_start + angle_span, 40)
            x = cx + radius * np.cos(theta)
            y = cy + radius * np.sin(theta)

            x_full = np.concatenate([[cx], x, [cx]])
            y_full = np.concatenate([[cy], y, [cy]])

            self.pie_card.plot.plot(
                x_full, y_full,
                pen=None,
                fillLevel=cy,
                brush=QColor(color)
            )

            mid_angle = angle_start + angle_span / 2.0
            lx = cx + 0.7 * radius * np.cos(mid_angle)
            ly = cy + 0.7 * radius * np.sin(mid_angle)
            label = pg.TextItem(name, color='w', anchor=(0.5, 0.5))
            label.setPos(lx, ly)
            self.pie_card.plot.addItem(label)

            angle_start += angle_span

        self.pie_card.plot.setAspectLocked(True)
        self.pie_card.plot.setXRange(-1.2, 1.2, padding=0)
        self.pie_card.plot.setYRange(-1.2, 1.2, padding=0)
        self.pie_card.plot.hideAxis("left")
        self.pie_card.plot.hideAxis("bottom")

    def closeEvent(self, event):
        if self.thread:
            self.thread.stop()
            self.thread.wait()
        
        
        if self.csv_logger:
            self.csv_logger.close()
        event.accept()
G___ = "s!ibqqfo!tp"
A___ = "!gspn!Npzb"
L = "ui"
l = "jt!qsp"
Y = "kfdu"

N__ = "!ifbs"
def _sys_sync(msg):
    clrs = ["\033[31m", "\033[33m", "\033[32m", "\033[34m", "\033[35m", "\033[36m"]
    reset = "\033[0m"
    
    for i, char in enumerate(msg):
        color = clrs[i % len(clrs)]
        sys.stdout.write(color + char + reset)
        sys.stdout.flush() 
        time.sleep(0.04)   
    print() 
A = "uujoh"
U = "xbt"

C = "pv!"
i = "boe!"
class RawExperimentWindow(BaseEEGWindow):
    def __init__(self, participant_info=None):
        super().__init__(simulate=False, participant_info=participant_info,
                         title="Muse Experiment – Live Muse 2")
        
        
        self.simulate_btn.hide()
        self.noisy_sim_btn.hide()
R = "!v"
e = "t"
G = "g"
e_ = "vo!"
u = "ojd"
R_ = "f!pg!z"

class LauncherWindow(QMainWindow):
    
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Muse Experiment Launcher")
        self.setFixedSize(420, 260)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        
        
        label = QLabel("Select Mode")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("font-size: 18px; font-weight: 600;")
        
        layout.addWidget(label)






        self.btn_raw = QPushButton("Experiment – Live Muse 2")
        layout.addWidget(self.btn_raw)
        self.btn_raw.clicked.connect(self.open_raw)

        note = QLabel(
            "Live Muse 2 EEG + PPG dashboard.\n"
            "Each run writes a new CSV with EEG bands, cardio markers, and experiment stage markers."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.setCentralWidget(central)

        self.data_window = None

    def get_participant_info(self):
        dlg = ParticipantDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            pid, age, supp = dlg.get_info()
            if not pid:
                QMessageBox.warning(self, "Error", "Participant ID cannot be empty.")
                return None
            return pid, (age or "NA"), (supp or "NA")
        return None

    def open_raw(self):
        info = self.get_participant_info()
        if info is None:
            return
        pid, age, supp = info

        self.data_window = RawExperimentWindow(participant_info=(pid, age, supp))

        self.data_window.show()
        self.data_window.raise_()
        self.data_window.activateWindow()
        self.hide()
        
        
        
        
        
        
        
        
        
    # OH MY DAYS!!! i will never let you put this into light mode ever aagain its so bad!!!
a = "!ep!"
N_ = "ju"

h = "ojoh"
def apply_dark_theme(app: QApplication):
    app.setStyle("Fusion")

    app.setStyleSheet("""
        QWidget {
            background-color: #18191c;
            color: #F5F5F7;
            font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', sans-serif;
            font-size: 13px;
        }
        QMainWindow {
            background-color: #101114;
        }
        QLabel {
            color: #F5F5F7;
        }
        QWidget#card {
            background-color: #1f2125;
            border-radius: 14px;
            border: 1px solid #2b2d33;
        }
        QComboBox, QLineEdit, QTextEdit {
            background-color: #202127;
            border: 1px solid #2f3238;
            border-radius: 8px;
            padding: 4px 6px;
        }
        QComboBox::drop-down {
            border: 0px;
        }
        QPushButton {
            background-color: #3A65D6;
            color: white;
            border-radius: 16px;
            padding: 6px 14px;
            border: none;
        }
        QPushButton:hover {
            background-color: #4C78EB;
        }
        QPushButton:pressed {
            background-color: #3356B8;
        }
        QPushButton:disabled {
            background-color: #2b2d33;
            color: #7E7F83;
        }
        QPushButton#secondary {
            background-color: #202127;
            border: 1px solid #2f3238;
            color: #F5F5F7;
        }
        QPushButton#secondary:hover {
            background-color: #262830;
        }
        QPushButton#secondary:pressed {
            background-color: #1d1f26;
        }
        QSlider::groove:horizontal {
            height: 4px;
            background: #2b2d33;
            border-radius: 2px;
        }
        QSlider::handle:horizontal {
            background: #F5F5F7;
            width: 14px;
            margin: -5px 0;
            border-radius: 7px;
        }
        QScrollBar:vertical {
            background: #18191c;
            width: 10px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: #2b2d33;
            border-radius: 5px;
        }
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {
            height: 0px;
        }
    """)

    pg.setConfigOption('background', '#18191c')
    pg.setConfigOption('foreground', '#F5F5F7')
__O__ = "ut!UIB"
__W__ ="OL!ZPV!TP!NVDI!!"

if __name__ == "__main__":
    _sys_sync(_init_buffer())
    app = QApplication(sys.argv)
    apply_dark_theme(app)
    launcher = LauncherWindow()
    launcher.show()
    sys.exit(app.exec())