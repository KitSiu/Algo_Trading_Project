import dolphindb as ddb
from datetime import datetime
from vnpy.trader.object import TickData
from vnpy.trader.constant import Exchange
from dateutil import parser


class DolphinDBTickFeed:
    def __init__(self, host='localhost', port=8848, user="admin", password="123456"):
        self.session = ddb.session()
        self.session.connect(host, port, user, password)

    def load_tick_data(self, symbol: str, exchange: Exchange, start: datetime, end: datetime):
        db_path = "dfs://ticks"
        table_name = 'future_ticks'
        if start == end:
            script = f"""
                        select * from loadTable("{db_path}", "{table_name}") 
                        where time = {start.strftime('%Y.%m.%d')}
                        order by time
                        """
        else:
            script = f"""
            select * from loadTable("{db_path}", "{table_name}") 
            where time between timestamp({start.strftime('%Y.%m.%d')}) : timestamp({end.strftime('%Y.%m.%d')})
            order by time
            """
        df = self.session.run(script)
        ticks = []
        for _, row in df.iterrows():
            time_str = str(row["time"])
            dt = parser.parse(time_str)
            tick = TickData(
                symbol=symbol,
                exchange=exchange,
                datetime=dt,
                name=symbol,
                last_price=row["current"],
                high_price=row["high"],
                low_price=row["low"],
                volume=row["volume"],
                turnover=row["money"],
                ask_price_1=row["a1_p"],
                ask_volume_1=row["a1_v"],
                bid_price_1=row["b1_p"],
                bid_volume_1=row["b1_v"],
                gateway_name="DDB"
            )
            ticks.append(tick)
        return ticks
