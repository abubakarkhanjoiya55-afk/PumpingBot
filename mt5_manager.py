import MetaTrader5 as mt5
import threading

class MT5Manager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self, login=None, password=None, server=None):
        # Always try to initialize - MT5 handles duplicate calls
        if login:
            result = mt5.initialize(login=login, password=password, server=server)
        else:
            result = mt5.initialize()
        if result:
            info = mt5.account_info()
            print(f"[MT5] Connected: {info.name if info else 'Unknown'}")
        else:
            print(f"[MT5] Init failed: {mt5.last_error()}")
        return result

    def account_info(self):
        return mt5.account_info()

    def copy_rates_from_pos(self, symbol, timeframe, start, count):
        return mt5.copy_rates_from_pos(symbol, timeframe, start, count)

    def symbol_info(self, symbol):
        return mt5.symbol_info(symbol)

    def symbol_info_tick(self, symbol):
        return mt5.symbol_info_tick(symbol)

    def positions_get(self, symbol=None):
        if symbol:
            return mt5.positions_get(symbol=symbol)
        return mt5.positions_get()

    def order_send(self, request):
        return mt5.order_send(request)

    @property
    def TIMEFRAME_M1(self): return mt5.TIMEFRAME_M1
    @property
    def TIMEFRAME_M5(self): return mt5.TIMEFRAME_M5
    @property
    def TIMEFRAME_M15(self): return mt5.TIMEFRAME_M15
    @property
    def TIMEFRAME_H1(self): return mt5.TIMEFRAME_H1
    @property
    def TIMEFRAME_H4(self): return mt5.TIMEFRAME_H4
    @property
    def ORDER_TYPE_BUY(self): return mt5.ORDER_TYPE_BUY
    @property
    def ORDER_TYPE_SELL(self): return mt5.ORDER_TYPE_SELL
    @property
    def TRADE_ACTION_DEAL(self): return mt5.TRADE_ACTION_DEAL
    @property
    def ORDER_TIME_GTC(self): return mt5.ORDER_TIME_GTC
    @property
    def ORDER_FILLING_IOC(self): return mt5.ORDER_FILLING_IOC
    @property
    def TRADE_RETCODE_DONE(self): return mt5.TRADE_RETCODE_DONE

mt5_manager = MT5Manager()