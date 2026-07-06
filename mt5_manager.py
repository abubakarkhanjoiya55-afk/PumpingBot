import asyncio
import threading
import time
from datetime import datetime, timezone, timedelta

METAAPI_TOKEN     = "eyJhbGciOiJSUzUxMiIsInR5cCI6IkpXVCJ9.eyJfaWQiOiI0YjI1NjU3N2M1ZDk4NzIzMzAwNTcwMWM0ODY0OTkwMiIsImFjY2Vzc1J1bGVzIjpbeyJpZCI6InRyYWRpbmctYWNjb3VudC1tYW5hZ2VtZW50LWFwaSIsIm1ldGhvZHMiOlsidHJhZGluZy1hY2NvdW50LW1hbmFnZW1lbnQtYXBpOnJlc3Q6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiLCJ3cml0ZXIiXSwicmVzb3VyY2VzIjpbIio6JFVTRVJfSUQkOioiXX0seyJpZCI6Im1ldGFhcGktcmVzdC1hcGkiLCJtZXRob2RzIjpbIm1ldGFhcGktYXBpOnJlc3Q6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiLCJ3cml0ZXIiXSwicmVzb3VyY2VzIjpbIio6JFVTRVJfSUQkOioiXX0seyJpZCI6Im1ldGFhcGktcnBjLWFwaSIsIm1ldGhvZHMiOlsibWV0YWFwaS1hcGk6d3M6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiLCJ3cml0ZXIiXSwicmVzb3VyY2VzIjpbIio6JFVTRVJfSUQkOioiXX0seyJpZCI6Im1ldGFhcGktcmVhbC10aW1lLXN0cmVhbWluZy1hcGkiLCJtZXRob2RzIjpbIm1ldGFhcGktYXBpOndzOnB1YmxpYzoqOioiXSwicm9sZXMiOlsicmVhZGVyIiwid3JpdGVyIl0sInJlc291cmNlcyI6WyIqOiRVU0VSX0lEJDoqIl19LHsiaWQiOiJtZXRhc3RhdHMtYXBpIiwibWV0aG9kcyI6WyJtZXRhc3RhdHMtYXBpOnJlc3Q6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiLCJ3cml0ZXIiXSwicmVzb3VyY2VzIjpbIio6JFVTRVJfSUQkOioiXX0seyJpZCI6InJpc2stbWFuYWdlbWVudC1hcGkiLCJtZXRob2RzIjpbInJpc2stbWFuYWdlbWVudC1hcGk6cmVzdDpwdWJsaWM6KjoqIl0sInJvbGVzIjpbInJlYWRlciIsIndyaXRlciJdLCJyZXNvdXJjZXMiOlsiKjokVVNFUl9JRCQ6KiJdfSx7ImlkIjoiY29weWZhY3RvcnktYXBpIiwibWV0aG9kcyI6WyJjb3B5ZmFjdG9yeS1hcGk6cmVzdDpwdWJsaWM6KjoqIl0sInJvbGVzIjpbInJlYWRlciIsIndyaXRlciJdLCJyZXNvdXJjZXMiOlsiKjokVVNFUl9JRCQ6KiJdfSx7ImlkIjoibXQtbWFuYWdlci1hcGkiLCJtZXRob2RzIjpbIm10LW1hbmFnZXItYXBpOnJlc3Q6ZGVhbGluZzoqOioiLCJtdC1tYW5hZ2VyLWFwaTpyZXN0OnB1YmxpYzoqOioiXSwicm9sZXMiOlsicmVhZGVyIiwid3JpdGVyIl0sInJlc291cmNlcyI6WyIqOiRVU0VSX0lEJDoqIl19LHsiaWQiOiJiaWxsaW5nLWFwaSIsIm1ldGhvZHMiOlsiYmlsbGluZy1hcGk6cmVzdDpwdWJsaWM6KjoqIl0sInJvbGVzIjpbInJlYWRlciJdLCJyZXNvdXJjZXMiOlsiKjokVVNFUl9JRCQ6KiJdfV0sImlnbm9yZVJhdGVMaW1pdHMiOmZhbHNlLCJ0b2tlbklkIjoiMjAyMTAyMTMiLCJpbXBlcnNvbmF0ZWQiOmZhbHNlLCJyZWFsVXNlcklkIjoiNGIyNTY1NzdjNWQ5ODcyMzMwMDU3MDFjNDg2NDk5MDIiLCJpYXQiOjE3ODMwMDQ4MTR9.XVk7jkTCPcMuekU-u1sglLoT-4wqHf1-IbAgeaUbc5URn0iJcIGWDWdV0KqEKh6oaUkcNzTSN-hqGBDpCSZl5FtCrNwEBXqEngDlMRokz2csqkwnmsERzpGXhQXBvup5jcVJGGFYid5hZqXYVc1ipSU7v6Y1G0LuO4EAgz-eWbWJ93iqTzUK9zS_voAdh1067VTBRpplTQgpBCPbt8fvwZcJ18w_uvMngEqjNVjRh5P63quYa5sfB9QIyU8yzafTcd8iNrz7H6FXYoRy6LpVon0e92pLLh5Fxo7nwCeNS_VCgavig1SPw6fHIX7xJDjo12ULAWIDgqMqqYfXWG_BWuCGS_fV7BLbNXQcTFwkVKBjOOCS0rfo2d6_4wF0fDEwuBzgSI6Ldv-NdBpPvQpqz-WWexDWpvuap462JTVuzYWOSaQAmQX4trFm3cj0XYK6yBAa0rnzKqkm7B6qV5JK9Z_d30riBSDHTJ5eqzTlSSdsMAsj5lv8KuLTsJbASxI72lF4cYgMGABF-fIcH-DW69bSW9Dcd3-6kiTbQ-CFsvL61TGczMzBZmlU5WWguEXL5VF-azdljuiNJy4dCXup9pfmcdm4GnJIEjhbUd89QW1LG8-NMDxXjV0D4wKr7BCuy7rFHHe2wShqWuaftXHX9Brg7oFwCQBCo0YFCjFouLY"
MASTER_ACCOUNT_ID = "5e4d5291-3a52-4e73-9a95-2d6ea449843c"

TIMEFRAME_M5       = "5m"
TIMEFRAME_H1       = "1h"
TIMEFRAME_H4       = "4h"
TRADE_ACTION_DEAL  = "DEAL"
ORDER_TYPE_BUY     = "ORDER_TYPE_BUY"
ORDER_TYPE_SELL    = "ORDER_TYPE_SELL"
ORDER_TIME_GTC     = "ORDER_TIME_GTC"
ORDER_FILLING_IOC  = "ORDER_FILLING_IOC"
TRADE_RETCODE_DONE = "TRADE_RETCODE_DONE"


class AccountInfo:
    def __init__(self, data):
        self.balance  = data.get('balance', 0)
        self.equity   = data.get('equity', 0)
        self.profit   = data.get('profit', 0)
        self.margin   = data.get('margin', 0)
        self.name     = data.get('name', '')
        self.leverage = data.get('leverage', 100) or 100


class SymbolInfo:
    def __init__(self, data):
        self.trade_tick_value = data.get('tickValue', 1)
        self.trade_tick_size  = data.get('tickSize', 0.01)
        self.volume_min       = data.get('minVolume', 0.01)
        self.volume_max       = data.get('maxVolume', 100)
        self.volume_step      = data.get('volumeStep', 0.01)
        self.point            = data.get('point', 0.00001)
        self.contract_size    = data.get('contractSize', 100000) or 100000


class SymbolTick:
    def __init__(self, data):
        self.bid = data.get('bid', 0)
        self.ask = data.get('ask', 0)


def _to_int_ticket(value):
    """MetaApi returns position/order ids as strings — normalize to int
    everywhere so DB storage (Integer column) and comparisons stay consistent
    across brokers/DB backends (SQLite is forgiving about str/int, Postgres is not)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class Position:
    def __init__(self, data):
        self.ticket  = _to_int_ticket(data.get('id', 0))
        self.symbol  = data.get('symbol', '')
        self.profit  = data.get('profit', 0)
        self.volume  = data.get('volume', 0)
        self.magic   = data.get('magic', 0)
        self.comment = data.get('comment', '')
        self.type    = 0 if data.get('type') == 'POSITION_TYPE_BUY' else 1


class TradeResult:
    def __init__(self, success, order_id=0):
        self.retcode = TRADE_RETCODE_DONE if success else "FAILED"
        self.order   = _to_int_ticket(order_id)   # ← actual ticket ID, normalized to int
        self.comment = "done" if success else "failed"


class MT5Manager:
    """
    Har user ke liye alag instance bana sakte ho.
    Master:   MT5Manager()                      → MASTER_ACCOUNT_ID use karta hai
    Follower: MT5Manager(account_id="xyz...")   → us user ka MetaApi account
    """
    def __init__(self, account_id=None):
        self._account_id = account_id or MASTER_ACCOUNT_ID
        self._api        = None
        self._account    = None
        self._connection = None
        self._loop       = None
        self._thread     = None
        self._ready      = False
        self._lock       = threading.Lock()

        # Constants — instance pe directly available
        self.TIMEFRAME_M5       = TIMEFRAME_M5
        self.TIMEFRAME_H1       = TIMEFRAME_H1
        self.TIMEFRAME_H4       = TIMEFRAME_H4
        self.TRADE_ACTION_DEAL  = TRADE_ACTION_DEAL
        self.ORDER_TYPE_BUY     = ORDER_TYPE_BUY
        self.ORDER_TYPE_SELL    = ORDER_TYPE_SELL
        self.ORDER_TIME_GTC     = ORDER_TIME_GTC
        self.ORDER_FILLING_IOC  = ORDER_FILLING_IOC
        self.TRADE_RETCODE_DONE = TRADE_RETCODE_DONE

    def _start_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run(self, coro):
        if self._loop is None or not self._loop.is_running():
            return None
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=120)
        except Exception as e:
            print(f"[MetaApi:{self._account_id[:8]}] {e}")
            self._ready = False
            try:
                asyncio.run_coroutine_threadsafe(self._async_reconnect(), self._loop)
            except:
                pass
            return None

    def initialize(self, login=None, password=None, server=None):
        """
        login/password/server yahan ignore hote hain —
        MetaApi account pehle se registered hona chahiye.
        account_id constructor mein pass karo.
        """
        try:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._start_loop, daemon=True)
                self._thread.start()
                time.sleep(1)
            if not self._ready:
                asyncio.run_coroutine_threadsafe(self._async_init(), self._loop)
            return True
        except Exception as e:
            print(f"[Init] {e}")
            return False

    async def _async_init(self):
        try:
            from metaapi_cloud_sdk import MetaApi
            self._api     = MetaApi(METAAPI_TOKEN)
            self._account = await self._api.metatrader_account_api.get_account(self._account_id)
            if self._account.state != 'DEPLOYED':
                await self._account.deploy()
            await self._account.wait_connected()
            self._connection = self._account.get_rpc_connection()
            await self._connection.connect()
            await self._connection.wait_synchronized(timeout_in_seconds=60)
            self._ready = True
            print(f"[MetaApi] Connected! Account: {self._account_id[:8]}...")
        except Exception as e:
            print(f"[MetaApi] Init error: {e}")
            self._ready = False

    async def _async_reconnect(self):
        print(f"[MetaApi:{self._account_id[:8]}] Reconnecting...")
        await self._async_init()

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
        data = self._run(self._async_get_candles(symbol, timeframe, count))
        if not data: return None
        return [{
            'open':  c.get('open', 0),
            'high':  c.get('high', 0),
            'low':   c.get('low', 0),
            'close': c.get('close', 0),
            'time':  c.get('time', 0),
        } for c in data]

    async def _async_get_candles(self, symbol, timeframe, count):
        try:
            start_time = datetime.now(timezone.utc) - timedelta(days=5)
            data = await self._account.get_historical_candles(symbol, timeframe, start_time, count)
            return data
        except Exception as e:
            print(f'[Candles] {e}')
            return None

    def order_send(self, request):
        if not self._ready: return TradeResult(False)
        result = self._run(self._async_order(request))
        if result is None:
            return TradeResult(False)
        return TradeResult(result[0], result[1])

    def modify_position(self, ticket, sl=None, tp=None):
        """Move SL/TP of an already-open position (broker-side trailing stop)."""
        if not self._ready:
            return False
        result = self._run(self._async_modify(ticket, sl, tp))
        return bool(result)

    async def _async_modify(self, ticket, sl, tp):
        try:
            kwargs = {}
            if sl is not None:
                kwargs['stop_loss'] = sl
            if tp is not None:
                kwargs['take_profit'] = tp
            await self._connection.modify_position(str(ticket), **kwargs)
            return True
        except Exception as e:
            print(f"[Modify] {e}")
            return False

    async def _async_order(self, request):
        try:
            position_id = request.get('position')

            # ── FIX: "position" key means CLOSE an existing position — earlier
            # this incorrectly opened a brand-new opposite-direction order
            # instead of actually closing the ticket (so TP/SL/trail exits
            # never really closed anything — they just added hedge positions).
            if position_id is not None:
                res = await self._connection.close_position(str(position_id))
                order_id = res.get('orderId', position_id) if isinstance(res, dict) else position_id
                return (True, order_id)

            symbol = request['symbol']
            volume = request['volume']
            sl     = request.get('sl', None)
            tp     = request.get('tp', None)
            if request['type'] == ORDER_TYPE_BUY:
                res = await self._connection.create_market_buy_order(
                    symbol, volume, stop_loss=sl, take_profit=tp)
            else:
                res = await self._connection.create_market_sell_order(
                    symbol, volume, stop_loss=sl, take_profit=tp)
            # order ID return karo
            order_id = res.get('orderId', 0) if isinstance(res, dict) else 0
            return (True, order_id)
        except Exception as e:
            print(f"[Order] {e}")
            return (False, 0)


# ─── COPY TRADING: Naya user ka MetaApi account find ya create karo ──────────

async def _find_or_create_metaapi_account(login, password, server):
    """
    User ka MT5 login MetaApi mein dhundo.
    Agar nahi mila toh naya account create karo.
    Returns: MetaApi account ID (string)
    """
    try:
        from metaapi_cloud_sdk import MetaApi
        api = MetaApi(METAAPI_TOKEN)

        # Pehle existing accounts mein dhundo
        accounts = await api.metatrader_account_api.get_accounts()
        for acc in accounts:
            acc_login = str(getattr(acc, 'login', '') or '')
            acc_server = str(getattr(acc, 'server', '') or '')
            if acc_login == str(login) and acc_server == server:
                print(f"[MetaApi] Found existing account for login={login}: {acc.id}")
                return acc.id

        # Nahi mila — naya create karo
        print(f"[MetaApi] Creating new account for login={login} server={server}")
        new_account = await api.metatrader_account_api.create_account({
            'name':        f'PumpingBot_{login}',
            'type':        'cloud',
            'login':       str(login),
            'password':    password,
            'server':      server,
            'platform':    'mt5',
            'application': 'MetaApi',
            'magic':       888888,
        })
        await new_account.deploy()
        await new_account.wait_connected(timeout_in_seconds=60)
        print(f"[MetaApi] New account created: {new_account.id}")
        return new_account.id

    except Exception as e:
        print(f"[MetaApi] find_or_create error: {e}")
        return None


async def find_or_create_metaapi_account(login, password, server):
    """Async wrapper — main.py ke async endpoints se seedha call karo"""
    return await _find_or_create_metaapi_account(login, password, server)


def create_user_manager(account_id):
    """
    Follower ke liye naya MT5Manager banao aur initialize karo.
    Returns: MT5Manager instance
    """
    manager = MT5Manager(account_id=account_id)
    manager.initialize()
    return manager


# ─── Master singleton ────────────────────────────────────────────────────────
mt5_manager = MT5Manager()   # Master — MASTER_ACCOUNT_ID use karta hai