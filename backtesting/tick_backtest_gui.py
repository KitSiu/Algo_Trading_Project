import sys
from datetime import datetime
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['SimHei']  # 黑体
matplotlib.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QLineEdit, QDateTimeEdit, QPushButton, QCheckBox,
                               QGroupBox, QFormLayout, QProgressBar, QTabWidget, QTableWidget,
                               QTableWidgetItem, QScrollArea, QSplitter, QTextEdit, QSizePolicy,
                               QComboBox, QStackedWidget, QHeaderView)
from PySide6.QtCore import Qt, QDateTime, QThread, Signal, QObject
from PySide6.QtGui import QDoubleValidator, QIntValidator, QFont
from vnpy.trader.constant import Interval, Exchange
from vnpy_ctabacktester.engine import BacktestingEngine
from vnpy_ctastrategy.base import BacktestingMode
from dolphindb_tick_feed import DolphinDBTickFeed
from strategies import DynamicTickDoubleMaStrategy, MacdDivergenceTickStrategy, TickDynamicBollChannelStrategy
import plotly.graph_objects as go
from config import *

STAT_TRANSLATIONS = {
    'start_date': '开始日期',
    'end_date': '结束日期',
    'total_days': '总天数',
    'profit_days': '盈利天数',
    'loss_days': '亏损天数',
    'capital': '初始资金',
    'end_balance': '结束资金',
    'max_drawdown': '最大回撤',
    'max_ddpercent': '最大回撤百分比',
    'max_drawdown_duration': '最大回撤持续天数',
    'total_net_pnl': '总净收益',
    'daily_net_pnl': '每日净收益',
    'total_commission': '总手续费',
    'daily_commission': '每日手续费',
    'total_slippage': '总滑点',
    'daily_slippage': '每日滑点',
    'total_turnover': '总成交量',
    'daily_turnover': '每日成交量',
    'total_trade_count': '总交易次数',
    'daily_trade_count': '每日交易次数',
    'total_return': '总收益率',
    'annual_return': '年化收益率',
    'daily_return': '日收益率',
    'return_std': '收益率标准差',
    'sharpe_ratio': '夏普比率',
    'ewm_sharpe': '指数加权夏普',
    'return_drawdown_ratio': '收益回撤比'
}


def create_balance_fig(df):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df.index, y=df["balance"],
        mode="lines", name="净值",
        line=dict(color="#1f77b4")
    ))
    fig.update_layout(
        title="账户净值曲线",
        xaxis_title="日期",
        yaxis_title="净值",
        height=300,
        margin=dict(l=40, r=40, t=40, b=40)
    )
    return fig


def create_drawdown_fig(df):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df.index, y=df["drawdown"],
        fill='tozeroy',
        fillcolor="rgba(255,0,0,0.3)",
        line=dict(color="red"),
        name="回撤"
    ))
    fig.update_layout(
        title="净值回撤",
        xaxis_title="日期",
        yaxis_title="回撤比例",
        height=300,
        showlegend=False
    )
    return fig


def create_daily_pnl_fig(df):
    colors = np.where(df["net_pnl"] >= 0, 'green', 'red')
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df.index, y=df["net_pnl"],
        marker_color=colors,
        name="日盈亏"
    ))
    fig.update_layout(
        title="每日盈亏",
        xaxis_title="日期",
        yaxis_title="盈亏金额",
        height=300,
        bargap=0.1
    )
    return fig


def create_pnl_distribution_fig(df):
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=df["net_pnl"],
        nbinsx=50,
        marker_color='#2ca02c',
        opacity=0.7
    ))
    fig.update_layout(
        title="盈亏分布直方图",
        xaxis_title="盈亏金额",
        yaxis_title="频次",
        height=300,
        bargap=0.05
    )
    return fig


class DataLoader(QThread):
    progress = Signal(int)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, data_feed, symbol, exchange, start, end):
        super().__init__()
        self.data_feed = data_feed
        self.symbol = symbol
        self.exchange = exchange
        self.start_time = start
        self.end_time = end

    def run(self):
        try:
            ticks = self.data_feed.load_tick_data(
                symbol=self.symbol,
                exchange=self.exchange,
                start=self.start_time,
                end=self.end_time
            )
            self.finished.emit(ticks)
        except Exception as e:
            self.error.emit(str(e))


class BacktestWorker(QThread):
    update_progress = Signal(int, str)
    finished = Signal(object)
    log_message = Signal(str)

    def __init__(self, engine, strategies):
        super().__init__()
        self.engine = engine
        self.strategies = strategies

    def run(self):
        try:
            # 重定向 output
            self.engine.output = lambda msg: self.log_message.emit(str(msg))
            self.engine.clear_data()
            for strategy_cls, params in self.strategies:
                self.engine.add_strategy(strategy_cls, params)

            self.engine.run_backtesting()
            df = self.engine.calculate_result()
            stats = self.engine.calculate_statistics()
            # fig = self.engine.show_chart()
            self.finished.emit((df, stats))
        except Exception as e:
            self.finished.emit(e)


class StrategyConfigWidget(QWidget):
    def __init__(self, strategy_class, parent=None):
        super().__init__(parent)
        self.strategy_class = strategy_class
        self.params = {}
        self.init_ui()

    def init_ui(self):
        layout = QFormLayout()
        for param in self.strategy_class.parameters:
            default_value = getattr(self.strategy_class, param)
            widget = QLineEdit(str(default_value))

            if isinstance(default_value, float):
                widget.setValidator(QDoubleValidator())
            elif isinstance(default_value, int):
                widget.setValidator(QIntValidator())

            layout.addRow(QLabel(param), widget)
            self.params[param] = widget
        self.setLayout(layout)

    def get_params(self):
        params = {}
        for param, widget in self.params.items():
            text = widget.text()
            param_type = type(getattr(self.strategy_class, param))
            try:
                params[param] = param_type(text) if text else getattr(self.strategy_class, param)
            except ValueError:
                params[param] = getattr(self.strategy_class, param)
        return params


class BacktestGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.history_data = []
        self.init_ui()
        self.loader = None
        self.worker = None
        # 延迟最大化，确保布局完成
        QTimer.singleShot(0, self.showMaximized)

    def init_ui(self):
        self.setFont(QFont("Arial", 11))
        self.setWindowTitle("Tick级回测系统")
        main_splitter = QSplitter(Qt.Horizontal)

        # 左侧面板
        left_panel = QSplitter(Qt.Vertical)

        # 左侧上半部分：数据配置
        data_group = QGroupBox("数据配置")
        data_layout = QFormLayout()
        self.symbol_edit = QLineEdit("AL2401")

        default_start = QDateTime(2024, 4, 1, 0, 0, 0)
        default_end = QDateTime(2024, 5, 1, 0, 0, 0)
        self.start_edit = QDateTimeEdit(default_start)
        self.end_edit = QDateTimeEdit(default_end)
        self.start_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.end_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")

        self.load_btn = QPushButton("加载数据")
        self.load_btn.clicked.connect(self.load_data)
        self.data_progress = QProgressBar()

        data_layout.addRow("合约代码", self.symbol_edit)
        data_layout.addRow("开始时间", self.start_edit)
        data_layout.addRow("结束时间", self.end_edit)
        data_layout.addRow(self.load_btn)
        data_layout.addRow(self.data_progress)
        data_group.setLayout(data_layout)

        # 策略选择配置
        strategy_group = QGroupBox("策略配置")
        strategy_layout = QVBoxLayout()
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems([
            "动态双均线策略",
            "MACD背离策略",
            "布林通道策略"
        ])
        self.strategy_stack = QStackedWidget()

        # 创建策略配置部件
        self.strategy_widgets = {
            0: StrategyConfigWidget(DynamicTickDoubleMaStrategy),
            1: StrategyConfigWidget(MacdDivergenceTickStrategy),
            2: StrategyConfigWidget(TickDynamicBollChannelStrategy)
        }
        for widget in self.strategy_widgets.values():
            self.strategy_stack.addWidget(widget)

        strategy_layout.addWidget(QLabel("选择策略："))
        strategy_layout.addWidget(self.strategy_combo)
        strategy_layout.addWidget(self.strategy_stack)
        strategy_group.setLayout(strategy_layout)

        # 将回测按钮和进度条移动到策略下方
        self.start_btn = QPushButton("开始回测")
        self.progress_bar = QProgressBar()
        control_layout = QVBoxLayout()
        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.progress_bar)
        strategy_layout.addLayout(control_layout)
        self.start_btn.clicked.connect(self.start_backtest)

        left_panel.addWidget(data_group)
        left_panel.addWidget(strategy_group)

        # 左侧下半部分：统计和日志
        right_left_panel = QSplitter(Qt.Vertical)

        # 统计表格
        stats_group = QGroupBox("统计指标")
        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(2)
        self.stats_table.setHorizontalHeaderLabels(["指标", "值"])
        # 平均分配列宽
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        stats_layout = QVBoxLayout()
        stats_layout.addWidget(self.stats_table)
        stats_group.setLayout(stats_layout)

        # 日志显示
        log_group = QGroupBox("运行日志")
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        log_layout = QVBoxLayout()
        log_layout.addWidget(self.log_view)
        log_group.setLayout(log_layout)

        right_left_panel.addWidget(stats_group)
        right_left_panel.addWidget(log_group)

        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(right_left_panel)

        # 右侧图表区域
        chart_group = QGroupBox("分析图表")
        chart_splitter = QSplitter(Qt.Vertical)

        # 右侧：四个 Matplotlib 画布
        self.canvases = []
        for _ in range(4):
            fig = Figure(figsize=(4, 3))
            canvas = FigureCanvas(fig)
            chart_splitter.addWidget(canvas)
            self.canvases.append((fig, canvas))

        chart_layout = QVBoxLayout()
        chart_layout.addWidget(chart_splitter)
        chart_group.setLayout(chart_layout)
        main_splitter.addWidget(chart_group)
        main_splitter.setSizes([500, 500, 1000])

        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.addWidget(main_splitter)
        main_layout.addLayout(control_layout)
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # 信号连接
        self.strategy_combo.currentIndexChanged.connect(self.strategy_stack.setCurrentIndex)

    def load_config(self):
        pass

    def load_data(self):
        self.data_progress.setRange(0, 0)
        self.load_btn.setEnabled(False)

        data_feed = DolphinDBTickFeed(host=DB_IP,
                                      port=DB_PORT,
                                      user=DB_USER,
                                      password=DB_PASSWORD)
        self.loader = DataLoader(
            data_feed=data_feed,
            symbol=self.symbol_edit.text(),
            exchange=Exchange.SHFE,
            start=self.start_edit.dateTime().toPython(),
            end=self.end_edit.dateTime().toPython()
        )

        self.loader.finished.connect(self.handle_data_loaded)
        self.loader.error.connect(self.handle_data_error)
        self.loader.start()

    def handle_data_loaded(self, ticks):
        self.history_data = ticks
        self.data_progress.setRange(0, 1)
        self.data_progress.setFormat("已成功加载！")
        self.load_btn.setEnabled(True)
        self.log_view.append(f"[{datetime.now()}] 成功加载 {len(ticks)} 条tick数据")

    def handle_data_error(self, error_msg):
        self.data_progress.setRange(0, 1)
        self.data_progress.setFormat("加载失败！")
        self.load_btn.setEnabled(True)
        self.log_view.append(f"[{datetime.now()}] 数据加载错误: {error_msg}")

    def start_backtest(self):
        selected_index = self.strategy_combo.currentIndex()
        strategy_cls = [
            DynamicTickDoubleMaStrategy,
            MacdDivergenceTickStrategy,
            TickDynamicBollChannelStrategy
        ][selected_index]

        params = self.strategy_widgets[selected_index].get_params()

        engine = BacktestingEngine()
        engine.set_parameters(
            vt_symbol=f"{self.symbol_edit.text()}.SHFE",
            interval=Interval.TICK,
            start=self.start_edit.dateTime().toPython(),
            end=self.end_edit.dateTime().toPython(),
            rate=0.0002,
            slippage=2.5,
            size=5,
            pricetick=5,
            capital=1_000_000,
            mode=BacktestingMode.TICK
        )
        engine.history_data = self.history_data

        self.worker = BacktestWorker(engine, [(strategy_cls, params)])
        self.worker.log_message.connect(self.log_view.append)
        self.worker.finished.connect(self.handle_backtest_result)
        self.worker.start()
        self.progress_bar.setRange(0, 0)

    def handle_backtest_result(self, result):
        self.progress_bar.setRange(0, 1)
        if isinstance(result, Exception):
            self.log_view.append(f"[{datetime.now()}] 回测失败: {str(result)}")
            return

        df, stats = result

        # 更新统计表格，确保两列
        self.stats_table.setRowCount(len(stats))
        for row, (key, value) in enumerate(stats.items()):
            # 翻译第一列
            cn_key = STAT_TRANSLATIONS.get(key, key)
            self.stats_table.setItem(row, 0, QTableWidgetItem(cn_key))
            self.stats_table.setItem(row, 1, QTableWidgetItem(str(value)))

        # 图1: 账户净值
        fig, canvas = self.canvases[0]
        fig.clear()
        ax = fig.add_subplot(111)
        ax.plot(df.index, df['balance'])
        ax.set_title('账户净值')
        ax.set_xlabel('日期')  # x轴标注
        ax.set_ylabel('资金')  # y轴标注
        # 优化 x 轴日期显示，不要太密集
        fig.autofmt_xdate(rotation=30)
        canvas.draw()

        # 图2: 净值回撤
        fig, canvas = self.canvases[1]
        fig.clear()
        ax = fig.add_subplot(111)
        ax.fill_between(df.index, df['drawdown'], color='red', alpha=0.3)
        ax.set_title('净值回撤')
        ax.set_xlabel('日期')
        ax.set_ylabel('回撤')
        fig.autofmt_xdate(rotation=30)
        canvas.draw()

        # 图3: 每日盈亏
        fig, canvas = self.canvases[2]
        fig.clear()
        ax = fig.add_subplot(111)
        colors = ['g' if x >= 0 else 'r' for x in df['net_pnl']]
        ax.bar(df.index, df['net_pnl'], color=colors)
        ax.set_title('每日盈亏')
        ax.set_xlabel('日期')
        ax.set_ylabel('盈亏')
        fig.autofmt_xdate(rotation=30)
        canvas.draw()

        # 图4: 盈亏分布
        fig, canvas = self.canvases[3]
        fig.clear()
        ax = fig.add_subplot(111)
        ax.hist(df['net_pnl'], bins=50)
        ax.set_title('盈亏分布')
        ax.set_xlabel('盈亏金额')
        ax.set_ylabel('频次')
        canvas.draw()

        # 更新统计表格
        self.stats_table.setRowCount(len(stats))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = BacktestGUI()
    gui.show()  # 最大化由 QTimer 调用
    sys.exit(app.exec())
