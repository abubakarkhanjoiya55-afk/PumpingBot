"""
Local MetaTrader5 wrapper — Windows only, no MetaAPI.

Requires: pip install MetaTrader5
And a running / installed MT5 terminal logged into the account.
"""

from __future__ import annotations

import time
from typing import Optional


class LocalMT5:
    def __init__(self, login: int, password: str, server: str, path: Optional[str] = None):
        self.login = int(login)
        self.password = password
        self.server = server
        self.path = path
        self._mt5 = None
        self.ready = False

    def connect(self) -> bool:
        try:
            import MetaTrader5 as mt5
        except ImportError as e:
            print(f"[LOCAL MT5] MetaTrader5 package missing: {e}")
            print("[LOCAL MT5] Install on Windows: pip install MetaTrader5")
            return False

        self._mt5 = mt5
        kwargs = {}
        if self.path:
            kwargs["path"] = self.path

        if not mt5.initialize(**kwargs):
            print(f"[LOCAL MT5] initialize failed: {mt5.last_error()}")
            return False

        authorized = mt5.login(self.login, password=self.password, server=self.server)
        if not authorized:
            print(f"[LOCAL MT5] login failed: {mt5.last_error()}")
            mt5.shutdown()
            return False

        self.ready = True
        info = mt5.account_info()
        print(f"[LOCAL MT5] Connected {self.login}@{self.server} "
              f"balance={getattr(info, 'balance', '?')}")
        return True

    def shutdown(self):
        if self._mt5:
            try:
                self._mt5.shutdown()
            except Exception:
                pass
        self.ready = False

    def account(self) -> dict:
        info = self._mt5.account_info() if self._mt5 else None
        if not info:
            return {"balance": 0, "equity": 0}
        return {
            "balance": float(info.balance),
            "equity": float(info.equity),
            "profit": float(info.profit),
            "margin": float(info.margin),
            "name": info.name,
            "leverage": int(info.leverage or 100),
            "login": int(info.login),
            "server": info.server,
        }

    def symbol_tick(self, symbol: str):
        return self._mt5.symbol_info_tick(symbol)

    def ensure_symbol(self, symbol: str) -> bool:
        mt5 = self._mt5
        if not mt5.symbol_select(symbol, True):
            return False
        return mt5.symbol_info(symbol) is not None

    def copy_rates(self, symbol: str, timeframe, count: int = 80):
        mt5 = self._mt5
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None:
            return None
        return [{
            "time": int(r["time"]),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
        } for r in rates]

    def positions(self, symbol: Optional[str] = None):
        mt5 = self._mt5
        if symbol:
            pos = mt5.positions_get(symbol=symbol)
        else:
            pos = mt5.positions_get()
        if not pos:
            return []
        out = []
        for p in pos:
            out.append({
                "ticket": int(p.ticket),
                "symbol": p.symbol,
                "type": int(p.type),  # 0 buy, 1 sell
                "volume": float(p.volume),
                "profit": float(p.profit),
                "price_open": float(p.price_open),
                "sl": float(p.sl),
                "tp": float(p.tp),
                "magic": int(p.magic),
                "comment": p.comment,
            })
        return out

    def _filling_mode(self, symbol: str):
        mt5 = self._mt5
        info = mt5.symbol_info(symbol)
        if info is None:
            return mt5.ORDER_FILLING_IOC
        filling = info.filling_mode
        # bitmask: 1=FOK, 2=IOC, 4=RETURN
        if filling & 2:
            return mt5.ORDER_FILLING_IOC
        if filling & 1:
            return mt5.ORDER_FILLING_FOK
        return mt5.ORDER_FILLING_RETURN

    def market_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        sl: float = 0.0,
        tp: float = 0.0,
        magic: int = 888888,
        comment: str = "PB_LOCAL",
        deviation: int = 80,
    ) -> dict:
        mt5 = self._mt5
        if not self.ensure_symbol(symbol):
            return {"ok": False, "error": f"symbol_unavailable:{symbol}"}

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"ok": False, "error": "no_tick"}

        order_type = mt5.ORDER_TYPE_BUY if side.upper() == "BUY" else mt5.ORDER_TYPE_SELL
        price = tick.ask if side.upper() == "BUY" else tick.bid
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "price": price,
            "deviation": deviation,
            "magic": magic,
            "comment": comment[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_mode(symbol),
        }
        if sl:
            request["sl"] = float(sl)
        if tp:
            request["tp"] = float(tp)

        result = mt5.order_send(request)
        if result is None:
            return {"ok": False, "error": str(mt5.last_error())}
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {
                "ok": False,
                "error": f"retcode={result.retcode}",
                "comment": result.comment,
            }
        ticket = int(result.order or result.deal or 0)
        return {
            "ok": True,
            "ticket": ticket,
            "price": float(result.price or price),
            "volume": float(volume),
        }

    def close_position(self, ticket: int, comment: str = "PB_CLOSE") -> dict:
        mt5 = self._mt5
        pos_list = mt5.positions_get(ticket=ticket)
        if not pos_list:
            return {"ok": True, "skip": True, "error": "already_closed"}
        pos = pos_list[0]
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            return {"ok": False, "error": "no_tick"}

        order_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        price = tick.bid if pos.type == 0 else tick.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": float(pos.volume),
            "type": order_type,
            "position": int(ticket),
            "price": price,
            "deviation": 80,
            "magic": int(pos.magic),
            "comment": comment[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_mode(pos.symbol),
        }
        result = mt5.order_send(request)
        if result is None:
            return {"ok": False, "error": str(mt5.last_error())}
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {"ok": False, "error": f"retcode={result.retcode}"}
        return {
            "ok": True,
            "ticket": int(ticket),
            "profit": float(pos.profit),
            "price": float(price),
        }

    def close_by_master_link(self, master_ticket: int, symbol: str) -> dict:
        """Close local copy whose comment embeds master ticket."""
        tag = f"M{master_ticket}"
        for pos in self.positions(symbol):
            if tag in (pos.get("comment") or "") or pos.get("magic") == 888888:
                # Prefer exact comment match when multiple
                if tag in (pos.get("comment") or ""):
                    return self.close_position(pos["ticket"], comment="PB_COPY_CLOSE")
        # fallback: close any PB_COPY on symbol
        for pos in self.positions(symbol):
            c = pos.get("comment") or ""
            if "PB_COPY" in c or pos.get("magic") == 888888:
                return self.close_position(pos["ticket"], comment="PB_COPY_CLOSE")
        return {"ok": True, "skip": True, "error": "no_local_position"}

    def timeframe_m1(self):
        return self._mt5.TIMEFRAME_M1
