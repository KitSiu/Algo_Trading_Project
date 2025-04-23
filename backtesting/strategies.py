from datetime import datetime
from vnpy.trader.object import TickData
from vnpy_ctastrategy.template import CtaTemplate


class DynamicTickDoubleMaStrategy(CtaTemplate):
    # 策略参数
    fast_window = 50
    slow_window = 200
    min_trade_interval = 300  # 最小交易间隔（秒）
    min_price_move = 50  # 距上次入场价最小价格移动（元）
    contract_size = 5  # 合约乘数（铝 5 吨/手）
    margin_rate = 0.16  # 保证金率 16%
    capital = 1_000_000  # 初始资金（元）

    parameters = [
        "fast_window", "slow_window",
        "min_trade_interval", "min_price_move",
        "contract_size", "margin_rate", "capital"
    ]
    variables = ["fast_ma", "slow_ma", "last_trade_dt", "last_entry_price", "current_capital"]

    def __init__(self, engine, strategy_name, vt_symbol, setting):
        super().__init__(engine, strategy_name, vt_symbol, setting)
        self.prices: list[float] = []
        self.last_trade_dt: datetime = datetime.min
        self.last_entry_price: float = 0
        self.current_capital: float = self.capital

    def on_init(self):
        self.write_log("策略初始化完成: 初始资金 %s" % self.capital)

    def on_start(self):
        self.write_log("策略启动")

    def on_stop(self):
        self.write_log("策略停止")

    def on_tick(self, tick: TickData):
        price = tick.last_price
        self.prices.append(price)
        max_len = max(self.fast_window, self.slow_window)
        if len(self.prices) > max_len:
            self.prices.pop(0)

        # 指标未准备好
        if len(self.prices) < self.slow_window:
            return

        # 计算快慢均线
        self.fast_ma = sum(self.prices[-self.fast_window:]) / self.fast_window
        self.slow_ma = sum(self.prices[-self.slow_window:]) / self.slow_window

        # 时间过滤
        now = tick.datetime
        if (now - self.last_trade_dt).total_seconds() < self.min_trade_interval:
            return

        pos = self.pos
        # 计算可用最大手数
        margin_per_contract = price * self.contract_size * self.margin_rate
        max_lots = int(self.current_capital / margin_per_contract)
        if max_lots <= 0:
            return

        # 金叉开多
        if self.fast_ma > self.slow_ma and pos <= 0:
            if self.last_entry_price == 0 or (price - self.last_entry_price) >= self.min_price_move:
                self.buy(price, max_lots)
                self.last_trade_dt = now
                self.last_entry_price = price

        # 死叉平多 / 开空
        elif self.fast_ma < self.slow_ma and pos > 0:
            if (self.last_entry_price - price) >= self.min_price_move:
                self.sell(price, pos)
                self.last_trade_dt = now

        elif self.fast_ma < self.slow_ma and pos >= 0:
            if self.last_entry_price == 0 or (self.last_entry_price - price) >= self.min_price_move:
                self.short(price, max_lots)
                self.last_trade_dt = now
                self.last_entry_price = price

        elif self.fast_ma > self.slow_ma and pos < 0:
            if (price - self.last_entry_price) >= self.min_price_move:
                self.cover(price, abs(pos))
                self.last_trade_dt = now

    def on_trade(self, trade):
        # 更新策略持仓收益到 current_capital
        pnl = trade.price * trade.volume * self.contract_size
        # 多单 pnl 为正，空单 pnl 价格取反
        if trade.direction.name == "SHORT":
            pnl = -pnl
        self.current_capital += pnl
        self.put_event()

    def on_order(self, order):
        pass

    def on_stop_order(self, stop_order):
        pass


class MacdDivergenceTickStrategy(CtaTemplate):
    fast_period = 12
    slow_period = 26
    signal_period = 9

    # 背离检测阈值（可调）
    min_trade_interval = 300  # 最小交易间隔（秒）

    # 合约与资金
    contract_size = 5  # 每手乘数
    margin_rate = 0.16  # 保证金率
    capital = 1_000_000  # 初始资金

    parameters = [
        "fast_period", "slow_period", "signal_period",
        "min_trade_interval", "contract_size", "margin_rate", "capital"
    ]
    variables = [
        "macd", "signal", "histogram",
        "last_trade_dt", "last_price_low", "last_hist_low", "current_capital"
    ]

    def __init__(self, engine, strategy_name, vt_symbol, setting):
        super().__init__(engine, strategy_name, vt_symbol, setting)

        # EMA 初始化
        self.ema_fast = None
        self.ema_slow = None
        self.ema_signal = None

        self.price_history: list[float] = []
        self.hist_history: list[float] = []

        self.last_trade_dt: datetime = datetime.min
        self.last_price_low: float = float('inf')
        self.last_hist_low: float = float('inf')
        self.current_capital: float = self.capital

    def on_init(self):
        self.write_log(f"策略初始化完成，初始资金: {self.capital}")

    def on_start(self):
        self.write_log("策略启动")

    def on_stop(self):
        self.write_log("策略停止")

    def on_tick(self, tick: TickData):
        price = tick.last_price
        now = tick.datetime

        # 更新 EMA
        alpha_fast = 2 / (self.fast_period + 1)
        alpha_slow = 2 / (self.slow_period + 1)
        alpha_signal = 2 / (self.signal_period + 1)

        if self.ema_fast is None:
            self.ema_fast = price
            self.ema_slow = price
            self.ema_signal = 0
        else:
            self.ema_fast = alpha_fast * price + (1 - alpha_fast) * self.ema_fast
            self.ema_slow = alpha_slow * price + (1 - alpha_slow) * self.ema_slow
        macd = self.ema_fast - self.ema_slow

        if self.ema_signal == 0:
            self.ema_signal = macd
        else:
            self.ema_signal = alpha_signal * macd + (1 - alpha_signal) * self.ema_signal
        hist = macd - self.ema_signal

        self.macd = macd
        self.signal = self.ema_signal
        self.histogram = hist

        # 收集历史用于背离检测
        self.price_history.append(price)
        self.hist_history.append(hist)

        # 初始累积
        if len(self.price_history) < 2:
            return

        # 最低点更新
        if price < self.last_price_low:
            self.last_price_low = price
        if hist < self.last_hist_low:
            self.last_hist_low = hist

        # 检测底背离：
        # 当前价格创新低，但 hist 未创新低，且间隔足够
        if (now - self.last_trade_dt).total_seconds() >= self.min_trade_interval:
            if price < self.last_price_low and hist > self.last_hist_low:
                # 动态仓位
                margin_per = price * self.contract_size * self.margin_rate
                max_lots = int(self.current_capital / margin_per)
                if max_lots > 0:
                    self.buy(price, max_lots)
                    self.last_trade_dt = now
                    # 重置底背离基准
                    self.last_price_low = price
                    self.last_hist_low = hist

    def on_trade(self, trade):
        # 更新资金
        pnl = (trade.price - trade.price) * trade.volume * self.contract_size
        # 多单 pnl = 0 here for simplicity; 后续可累加交易盈亏
        # 更新 current_capital 需调用引擎统计
        self.current_capital = self.engine.capital
        self.put_event()

    def on_order(self, order):
        pass

    def on_stop_order(self, stop_order):
        pass


class TickDynamicBollChannelStrategy(CtaTemplate):
    window = 200  # 布林通道计算窗口
    dev_multiplier = 2.5  # 标准差倍数
    min_trade_interval = 300  # 最小交易间隔（秒）
    contract_size = 5  # 合约乘数
    margin_rate = 0.16  # 保证金率
    capital = 1_000_000  # 初始资金

    parameters = [
        "window", "dev_multiplier",
        "min_trade_interval", "contract_size",
        "margin_rate", "capital"
    ]
    variables = [
        "upper", "lower", "mean",
        "current_capital", "last_trade_dt"
    ]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.prices: list[float] = []
        self.last_trade_dt: datetime = datetime.min
        self.current_capital: float = self.capital

    def on_init(self):
        self.write_log(f"策略初始化完成，初始资金：{self.capital}")

    def on_start(self):
        self.write_log("策略启动")

    def on_stop(self):
        self.write_log("策略停止")

    def on_tick(self, tick: TickData):
        price = tick.last_price
        now = tick.datetime

        # 1. 更新价格序列
        self.prices.append(price)
        if len(self.prices) > self.window:
            self.prices.pop(0)

        # 2. 数据不足
        if len(self.prices) < self.window:
            return

        # 3. 计算布林通道
        self.mean = sum(self.prices) / self.window
        variance = sum((p - self.mean) ** 2 for p in self.prices) / self.window
        std = variance ** 0.5
        self.upper = self.mean + self.dev_multiplier * std
        self.lower = self.mean - self.dev_multiplier * std

        # 4. 频率控制
        if (now - self.last_trade_dt).total_seconds() < self.min_trade_interval:
            return

        # 5. 动态计算最大可开手数
        margin_per = price * self.contract_size * self.margin_rate
        max_lots = int(self.current_capital / margin_per)
        if max_lots <= 0:
            return

        pos = self.pos

        # 6. 策略信号
        # 突破上轨，且当前无多头持仓，开多
        if price > self.upper and pos <= 0:
            self.buy(price, max_lots)
            self.last_trade_dt = now

        # 突破下轨，且当前无空头持仓，开空
        elif price < self.lower and pos >= 0:
            self.short(price, max_lots)
            self.last_trade_dt = now

    def on_trade(self, trade):
        # 更新资金（使用引擎计算后的最新 equity）
        self.current_capital = self.capital
        self.put_event()

    def on_order(self, order):
        pass

    def on_stop_order(self, stop_order):
        pass
