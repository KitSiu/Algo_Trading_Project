# Algo_Trading_Project MFE5210

项目介绍：基于vnpy框架开发的Tick级别中国商品期货回测系统，支持多策略动态参数配置、实时进度展示和可视化分析。

[点击观看回测演示](https://owyenliu.github.io/video-demo/)

## 环境配置
- 一键安装：https://download.vnpy.com/veighna_studio-3.9.4.exe
- 指定项目解释器&虚拟环境为vnpy根目录的python.exe
- 在该环境安装jupyter&注册ipykernel以使用jupyter notebook进行调试
```bash
F:\VeighNa\python.exe -m pip install ipykernel
F:\VeighNa\python.exe -m ipykernel install --user --name veighna --display-name "Python (VeighNa)"
启动jupyter notebook 在右上角change kernel选择"Python (VeighNa)"
```

## 文件结构
project-root
 - dolphindb_tick_feed.py # DolphinDB数据连接模块
 - strategies.py # 策略实现模块
 - tick_backtest_gui.py # 图形化回测界面主程序
 - config.py # 数据库配置

### 阶段1：数据获取与处理
- 期货的tick数据2010.01-2024.12，来自聚宽
- 共5000多w行，被保存至服务器的dolphindb数据库
- 当start_date=end_date时，获取单天的tick数据只需2~3秒 ；当取一个月的tick数据时采用between运算，耗时1~2分钟。因此建议测试时时长小于等于一个月

### 阶段2：回测框架搭建
- 因为vnpy暂不支持dolphindb的直接导入；vnpy内置的策略模版都是bar级别的，不支持tick；新版本vnpy4.0.0&python3.13与dolphindb不兼容
- 所以选择vnpy3.9.4&python3.10为核心进行二次开发，完成整个回测流程的重构

### 阶段3：策略开发
- 策略选择继承vnpy_ctastrategy的模版CtaTemplate，因为模版虽然是适用于bar数据的，但是回测的驱动逻辑属于事件驱动，可以直接用来回测tick数据


### 阶段4：GUI回测系统
- 集成功能：数据加载、参数设置、回测实现、运行日志跟踪、统计指标展示、分析图表汇总

### 阶段5：基于实盘交易功能&TCA的分析和展望
- 实时交易系统和回测的差别：
- 1.数据的获取方式：回测使用的是历史数据，采用事件驱动的方式来循环遍历数据；而实时交易系统采用的是发布-订阅Pub/Sub模型，即在订阅后，由交易所主动推送数据，我们只需要一直运行程序，在获取到数据后就可以更新页面、请求下单。所以回测使用的数据回放是在模拟pubsub模型的推送过程，差别在于延迟导致的能否成交问题。
- 2.撮合：实盘不完成撮合，而是vnpy.gateway中的接口（如 ctp_gateway）把订单直接下到券商/交易所，撮合是交易所完成的，策略无法控制成交与否，再由交易所返回的order和trade来得到反馈。
- 3.所以，为了回测更贴近真实场景，我们可以在策略中加入其他设计来解决能不能成交的问题（比如说对手单的区间成交量够不够？而不是粗略的假设按当前价+滑点买多少有多少），同时再用vnpy的框架考虑带来的成本有多少。
vnpy的回测框架主要是在engine.calculate_result() 的以下代码中使用slippage来计算当日滑点成本，这属于成交后的估计
```bash
self.slippage += trade.volume * size * slippage

self.turnover += turnover
self.commission += turnover * rate

# Net pnl takes account of commission and slippage cost
self.total_pnl = self.trading_pnl + self.holding_pnl
self.net_pnl = self.total_pnl - self.commission - self.slippage
```

  
