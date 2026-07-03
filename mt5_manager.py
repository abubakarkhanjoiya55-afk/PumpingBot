import asyncio
import threading
import time

METAAPI_TOKEN      = "eyJhbGciOiJSUzUxMiIsInR5cCI6IkpXVCJ9.eyJfaWQiOiI0YjI1NjU3N2M1ZDk4NzIzMzAwNTcwMWM0ODY0OTkwMiIsImFjY2Vzc1J1bGVzIjpbeyJpZCI6InRyYWRpbmctYWNjb3VudC1tYW5hZ2VtZW50LWFwaSIsIm1ldGhvZHMiOlsidHJhZGluZy1hY2NvdW50LW1hbmFnZW1lbnQtYXBpOnJlc3Q6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiLCJ3cml0ZXIiXSwicmVzb3VyY2VzIjpbIio6JFVTRVJfSUQkOioiXX0seyJpZCI6Im1ldGFhcGktcmVzdC1hcGkiLCJtZXRob2RzIjpbIm1ldGFhcGktYXBpOnJlc3Q6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiLCJ3cml0ZXIiXSwicmVzb3VyY2VzIjpbIio6JFVTRVJfSUQkOioiXX0seyJpZCI6Im1ldGFhcGktcnBjLWFwaSIsIm1ldGhvZHMiOlsibWV0YWFwaS1hcGk6d3M6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiLCJ3cml0ZXIiXSwicmVzb3VyY2VzIjpbIio6JFVTRVJfSUQkOioiXX0seyJpZCI6Im1ldGFhcGktcmVhbC10aW1lLXN0cmVhbWluZy1hcGkiLCJtZXRob2RzIjpbIm1ldGFhcGktYXBpOndzOnB1YmxpYzoqOioiXSwicm9sZXMiOlsicmVhZGVyIiwid3JpdGVyIl0sInJlc291cmNlcyI6WyIqOiRVU0VSX0lEJDoqIl19LHsiaWQiOiJtZXRhc3RhdHMtYXBpIiwibWV0aG9kcyI6WyJtZXRhc3RhdHMtYXBpOnJlc3Q6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiLCJ3cml0ZXIiXSwicmVzb3VyY2VzIjpbIio6JFVTRVJfSUQkOioiXX0seyJpZCI6InJpc2stbWFuYWdlbWVudC1hcGkiLCJtZXRob2RzIjpbInJpc2stbWFuYWdlbWVudC1hcGk6cmVzdDpwdWJsaWM6KjoqIl0sInJvbGVzIjpbInJlYWRlciIsIndyaXRlciJdLCJyZXNvdXJjZXMiOlsiKjokVVNFUl9JRCQ6KiJdfSx7ImlkIjoiY29weWZhY3RvcnktYXBpIiwibWV0aG9kcyI6WyJjb3B5ZmFjdG9yeS1hcGk6cmVzdDpwdWJsaWM6KjoqIl0sInJvbGVzIjpbInJlYWRlciIsIndyaXRlciJdLCJyZXNvdXJjZXMiOlsiKjokVVNFUl9JRCQ6KiJdfSx7ImlkIjoibXQtbWFuYWdlci1hcGkiLCJtZXRob2RzIjpbIm10LW1hbmFnZXItYXBpOnJlc3Q6ZGVhbGluZzoqOioiLCJtdC1tYW5hZ2VyLWFwaTpyZXN0OnB1YmxpYzoqOioiXSwicm9sZXMiOlsicmVhZGVyIiwid3JpdGVyIl0sInJlc291cmNlcyI6WyIqOiRVU0VSX0lEJDoqIl19LHsiaWQiOiJiaWxsaW5nLWFwaSIsIm1ldGhvZHMiOlsiYmlsbGluZy1hcGk6cmVzdDpwdWJsaWM6KjoqIl0sInJvbGVzIjpbInJlYWRlciJdLCJyZXNvdXJjZXMiOlsiKjokVVNFUl9JRCQ6KiJdfV0sImlnbm9yZVJhdGVMaW1pdHMiOmZhbHNlLCJ0b2tlbklkIjoiMjAyMTAyMTMiLCJpbXBlcnNvbmF0ZWQiOmZhbHNlLCJyZWFsVXNlcklkIjoiNGIyNTY1NzdjNWQ5ODcyMzMwMDU3MDFjNDg2NDk5MDIiLCJpYXQiOjE3ODMwMDQ4MTR9.XVk7jkTCPcMuekU-u1sglLoT-4wqHf1-IbAgeaUbc5URn0iJcIGWDWdV0KqEKh6oaUkcNzTSN-hqGBDpCSZl5FtCrNwEBXqEngDlMRokz2csqkwnmsERzpGXhQXBvup5jcVJGGFYid5hZqXYVc1ipSU7v6Y1G0LuO4EAgz-eWbWJ93iqTzUK9zS_voAdh1067VTBRpplTQgpBCPbt8fvwZcJ18w_uvMngEqjNVjRh5P63quYa5sfB9QIyU8yzafTcd8iNrz7H6FXYoRy6LpVon0e92pLLh5Fxo7nwCeNS_VCgavig1SPw6fHIX7xJDjo12ULAWIDgqMqqYfXWG_BWuCGS_fV7BLbNXQcTFwkVKBjOOCS0rfo2d6_4wF0fDEwuBzgSI6Ldv-NdBpPvQpqz-WWexDWpvuap462JTVuzYWOSaQAmQX4trFm3cj0XYK6yBAa0rnzKqkm7B6qV5JK9Z_d30riBSDHTJ5eqzTlSSdsMAsj5lv8KuLTsJbASxI72lF4cYgMGABF-fIcH-DW69bSW9Dcd3-6kiTbQ-CFsvL61TGczMzBZmlU5WWguEXL5VF-azdljuiNJy4dCXup9pfmcdm4GnJIEjhbUd89QW1LG8-NMDxXjV0D4wKr7BCuy7rFHHe2wShqWuaftXHX9Brg7oFwCQBCo0YFCjFouLY"
METAAPI_ACCOUNT_ID = "5e4d5291-3a52-4e73-9a95-2d6ea449843c"

TIMEFRAME_M5 = "5m"
TIMEFRAME_H1 = "1h"
TIMEFRAME_H4 = "4h"

TRADE_ACTION_DEAL  = "DEAL"
ORDER_TYPE_BUY     = "ORDER_TYPE_BUY"
ORDER_TYPE_SELL    = "ORDER_TYPE_SELL"
ORDER_TIME_GTC     = "ORDER_TIME_GTC"
ORDER_FILLING_IOC  = "ORDER_FILLING_IOC"
TRADE_RETCODE_DONE = "TRADE_RETCODE_DONE"

class AccountInfo:
    def __init__(self, data):
        self.balance = data.get('balance', 0)
        self.equity  = data.get('equity', 0)
        self.profit  = data.get('profit', 0)
        self.margin  = data.get('margin', 0)
        self.name    = data.get('name', '')

class SymbolInfo:
    def __init__(self, data):
        self.trade_tick_value = data.get('tickValue', 1)
        self.trade_tick_size  = data.get('tickSize', 0.01)
        self.volume_min       = data.get('minVolume', 0.01)
        self.volume_max       = data.get('maxVolume', 100)
        self.volume_step      = data.get('volumeStep', 0.01)
        self.point            = data.get('point', 0.00001)

class SymbolTick:
    def __init__(self, data):
        self.bid = data.get('bid', 0)
        self.ask = data.get('ask', 0)

class Position:
    def __init__(self, data):
        self.ticket = data.get('id', 0)
        self.symbol = data.get('symbol', '')
        self.profit = data.get('profit', 0)
        self.volume = data.get('volume', 0)
        self.magic  = data.get('magic', 0)
        self.type   = 0 if data.get('type') == 'POSITION_TYPE_BUY' else 1

class TradeResult:
    def __init__(self, success):
        self.retcode = TRADE_RETCODE_DONE if success else "FAILED"
        self.order   = 0
        self.comment = "done" if success else "failed"

class MT5Manager:
    def __init__(self):
        self._api        = None
        self._account    = None
        self._connection = None
        self._loop       = None
        self._thread     = None
        self._ready      = False

    def _start_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run(self, coro):
        if self._loop is None or not self._loop.is_running():
            return None
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=30)
        except Exception as e:
            print(f"[MetaApi] {e}")
            return None

    def initialize(self, login=None, password=None, server=None):
        try:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._start_loop, daemon=True)
                self._thread.start()
                time.sleep(1)
            return self._run(self._async_init())
        except Exception as e:
            print(f"[Init] {e}")
            return False

    async def _async_init(self):
        try:
            from metaapi_cloud_sdk import MetaApi
            self._api     = MetaApi(METAAPI_TOKEN)
            self._account = await self._api.metatrader_account_api.get_account(METAAPI_ACCOUNT_ID)
            if self._account.state != 'DEPLOYED':
                await self._account.deploy()
            await self._account.wait_connected()
            self._connection = self._account.get_rpc_connection()
            await self._connection.connect()
            await self._connection.wait_synchronized()
            self._ready = True
            print("[MetaApi] Connected!")
            return True
        except Exception as e:
            print(f"[MetaApi] {e}")
            return False

    def account_info(self):
        if not self._ready: return None
        data = self._run(self._connection.get_account_information())
        return AccountInfo(data) if data else None

    def symbol_info(self, symbol):
        if not self._ready: return None
        data = self._run(self._connection.get_symbol_specification(symbol))
        return SymbolInfo(data) if data else None

    def symbol_info_tick(self, symbol):
        if not self._ready: return None
        data = self._run(self._connection.get_symbol_price(symbol))
        return SymbolTick(data) if data else None

    def positions_get(self, symbol=None):
        if not self._ready: return []
        data = self._run(self._connection.get_positions())
        if not data: return []
        positions = [Position(p) for p in data]
        if symbol:
            positions = [p for p in positions if p.symbol == symbol]
        return positions

    def copy_rates_from_pos(self, symbol, timeframe, start, count):
        if not self._ready: return None
        data = self._run(self._connection.get_candles(symbol, timeframe, count=count))
        if not data: return None
        return [{
            'open':  c.get('open', 0),
            'high':  c.get('high', 0),
            'low':   c.get('low', 0),
            'close': c.get('close', 0),
            'time':  c.get('time', 0),
        } for c in data]

    def order_send(self, request):
        if not self._ready: return TradeResult(False)
        result = self._run(self._async_order(request))
        return TradeResult(result)

    async def _async_order(self, request):
        try:
            symbol  = request['symbol']
            volume  = request['volume']
            sl      = request.get('sl', None)
            comment = request.get('comment', '')
            if request['type'] == ORDER_TYPE_BUY:
                await self._connection.create_market_buy_order(
                    symbol, volume, stop_loss=sl, comment=comment)
            else:
                await self._connection.create_market_sell_order(
                    symbol, volume, stop_loss=sl, comment=comment)
            return True
        except Exception as e:
            print(f"[Order] {e}")
            return False

mt5_manager = MT5Manager()