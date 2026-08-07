//+------------------------------------------------------------------+
//| PumpingBotFollower.mq5                                           |
//| User PC: Exness MT5 pe lagao — master trades auto copy           |
//|                                                                  |
//| SETUP (ek dafa):                                                 |
//|  1) Exness MT5 install + apna account login                      |
//|  2) Algo Trading ON + WebRequest allow (server URL)              |
//|  3) Yeh EA Experts folder mein copy → chart pe drag              |
//|  4) Inputs: InpToken = app → PC Setup se EA token                |
//|  Rozana: bas MT5 open + login + AutoTrading ON                   |
//+------------------------------------------------------------------+
#property copyright "PumpingBot"
#property version   "3.34"
#property strict

input string InpServerUrl = "https://web-production-c78a0.up.railway.app";
input string InpToken     = "";          // App → PC Setup → EA Token
input int    InpPollMs    = 1000;        // poll interval
input int    InpMagic     = 888888;
input double InpMinLot    = 0.01;

string g_base;
int    g_timer = 0;

// master_ticket -> local ticket
string MapKey(long master) { return "pb_" + IntegerToString((int)master); }

bool HttpGet(const string url, string &out)
{
   char data[];
   char result[];
   string headers = "User-Agent: PumpingBotEA/3.34\r\n";
   ResetLastError();
   int code = WebRequest("GET", url, headers, 8000, data, result, headers);
   if(code == -1)
   {
      int err = GetLastError();
      Print("WebRequest GET failed err=", err, " — Tools→Options→EA→Allow WebRequest: ", g_base);
      return false;
   }
   out = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
   return (code >= 200 && code < 300);
}

bool HttpPostJson(const string url, const string json, string &out)
{
   char data[];
   char result[];
   string headers = "Content-Type: application/json\r\nUser-Agent: PumpingBotEA/3.34\r\n";
   int len = StringToCharArray(json, data, 0, WHOLE_ARRAY, CP_UTF8);
   if(len > 0) len -= 1; // drop null
   ArrayResize(data, len);
   ResetLastError();
   int code = WebRequest("POST", url, headers, 8000, data, result, headers);
   if(code == -1)
   {
      Print("WebRequest POST failed err=", GetLastError());
      return false;
   }
   out = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
   return (code >= 200 && code < 300);
}

string JsonEscape(const string s)
{
   string r = s;
   StringReplace(r, "\\", "\\\\");
   StringReplace(r, "\"", "\\\"");
   return r;
}

string ExtractJsonString(const string json, const string key)
{
   string pat = "\"" + key + "\"";
   int p = StringFind(json, pat);
   if(p < 0) return "";
   p = StringFind(json, ":", p);
   if(p < 0) return "";
   int q1 = StringFind(json, "\"", p + 1);
   if(q1 < 0) return "";
   int q2 = StringFind(json, "\"", q1 + 1);
   if(q2 < 0) return "";
   return StringSubstr(json, q1 + 1, q2 - q1 - 1);
}

bool ExtractJsonBool(const string json, const string key, const bool def=false)
{
   string pat = "\"" + key + "\"";
   int p = StringFind(json, pat);
   if(p < 0) return def;
   p = StringFind(json, ":", p);
   if(p < 0) return def;
   string rest = StringSubstr(json, p + 1, 16);
   if(StringFind(rest, "true") >= 0) return true;
   if(StringFind(rest, "false") >= 0) return false;
   return def;
}

double ExtractJsonNumber(const string json, const string key, const double def=0)
{
   string pat = "\"" + key + "\"";
   int p = StringFind(json, pat);
   if(p < 0) return def;
   p = StringFind(json, ":", p);
   if(p < 0) return def;
   string num = "";
   for(int i = p + 1; i < StringLen(json); i++)
   {
      ushort c = StringGetCharacter(json, i);
      if((c >= '0' && c <= '9') || c == '.' || c == '-' )
         num += ShortToString(c);
      else if(StringLen(num) > 0)
         break;
   }
   if(StringLen(num) == 0) return def;
   return StringToDouble(num);
}

string ResolveSymbol(const string raw)
{
   if(SymbolSelect(raw, true)) return raw;
   string u = raw;
   // try common Exness suffixes
   string tryList[6];
   tryList[0] = raw;
   tryList[1] = raw + "m";
   tryList[2] = raw + "c";
   if(StringLen(u) > 1)
   {
      string base = u;
      if(StringGetCharacter(base, StringLen(base) - 1) == 'm' ||
         StringGetCharacter(base, StringLen(base) - 1) == 'c')
         base = StringSubstr(base, 0, StringLen(base) - 1);
      tryList[3] = base;
      tryList[4] = base + "m";
      tryList[5] = base + "c";
   }
   for(int i = 0; i < 6; i++)
   {
      if(StringLen(tryList[i]) == 0) continue;
      if(SymbolSelect(tryList[i], true)) return tryList[i];
   }
   return raw;
}

double NormLot(const string symbol, double lot)
{
   double minLot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double step   = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   if(minLot <= 0) minLot = InpMinLot;
   if(step <= 0) step = 0.01;
   if(lot < minLot) lot = minLot;
   if(lot > maxLot && maxLot > 0) lot = maxLot;
   lot = MathFloor(lot / step) * step;
   if(lot < minLot) lot = minLot;
   return NormalizeDouble(lot, 2);
}

long FindByMasterComment(const long master_ticket)
{
   string tag = "PB" + IntegerToString((int)master_ticket);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      string cmt = PositionGetString(POSITION_COMMENT);
      if(StringFind(cmt, tag) == 0 || cmt == tag)
         return (long)ticket;
   }
   return 0;
}

void Ack(const string cmd_id, const bool ok, const long ticket, const long master,
         const string symbol, const string side, const double lot,
         const double price, const double profit, const string err)
{
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   string json = "{";
   json += "\"login\":" + IntegerToString((int)login) + ",";
   json += "\"token\":\"" + JsonEscape(InpToken) + "\",";
   json += "\"cmd_id\":\"" + JsonEscape(cmd_id) + "\",";
   json += "\"ok\":" + (ok ? "true" : "false") + ",";
   json += "\"ticket\":" + IntegerToString((int)ticket) + ",";
   json += "\"master_ticket\":" + IntegerToString((int)master) + ",";
   json += "\"symbol\":\"" + JsonEscape(symbol) + "\",";
   json += "\"side\":\"" + JsonEscape(side) + "\",";
   json += "\"lot\":" + DoubleToString(lot, 2) + ",";
   json += "\"price\":" + DoubleToString(price, 5) + ",";
   json += "\"profit\":" + DoubleToString(profit, 2) + ",";
   json += "\"error\":\"" + JsonEscape(err) + "\"";
   json += "}";
   string out;
   HttpPostJson(g_base + "/ea/ack", json, out);
}

void DoCopyOpen(const string cmd)
{
   string cmd_id = ExtractJsonString(cmd, "id");
   string symbol = ResolveSymbol(ExtractJsonString(cmd, "symbol"));
   string side   = ExtractJsonString(cmd, "side");
   long master   = (long)ExtractJsonNumber(cmd, "master_ticket", 0);
   double m_lot  = ExtractJsonNumber(cmd, "master_lot", InpMinLot);
   double m_bal  = ExtractJsonNumber(cmd, "master_balance", 0);
   double sl     = ExtractJsonNumber(cmd, "sl", 0);
   double entry  = ExtractJsonNumber(cmd, "entry", 0);
   double score  = ExtractJsonNumber(cmd, "score", 50);

   if(master > 0 && FindByMasterComment(master) > 0)
   {
      Print("Skip duplicate master=", master);
      return;
   }

   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   double lot = m_lot;
   if(m_bal > 0 && bal > 0)
      lot = MathMax(InpMinLot, NormalizeDouble(m_lot * (bal / m_bal), 2));
   if(score >= 90) lot = NormalizeDouble(lot * 1.15, 2);
   lot = NormLot(symbol, lot);

   MqlTradeRequest req;
   MqlTradeResult  res;
   ZeroMemory(req);
   ZeroMemory(res);
   req.action    = TRADE_ACTION_DEAL;
   req.symbol    = symbol;
   req.volume    = lot;
   req.deviation = 50;
   req.magic     = InpMagic;
   req.comment   = "PB" + IntegerToString((int)master);
   req.type_filling = ORDER_FILLING_IOC;

   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   if(side == "SELL")
   {
      req.type  = ORDER_TYPE_SELL;
      req.price = bid;
      if(sl > 0 && entry > 0)
         req.sl = bid + MathAbs(entry - sl);
   }
   else
   {
      req.type  = ORDER_TYPE_BUY;
      req.price = ask;
      if(sl > 0 && entry > 0)
         req.sl = ask - MathAbs(entry - sl);
   }

   bool ok = OrderSend(req, res);
   if(!ok || (res.retcode != TRADE_RETCODE_DONE && res.retcode != TRADE_RETCODE_DONE_PARTIAL))
   {
      Print("COPY OPEN fail ", symbol, " ", side, " ret=", res.retcode, " ", res.comment);
      Ack(cmd_id, false, 0, master, symbol, side, lot, 0, 0, IntegerToString((int)res.retcode));
      return;
   }
   Print("COPY OPEN ok ", symbol, " ", side, " lot=", lot, " ticket=", res.order);
   Ack(cmd_id, true, (long)res.order, master, symbol, side, lot, res.price, 0, "");
}

void DoCopyClose(const string cmd)
{
   string cmd_id = ExtractJsonString(cmd, "id");
   long master   = (long)ExtractJsonNumber(cmd, "master_ticket", 0);
   string symbol = ExtractJsonString(cmd, "symbol");
   long ticket   = FindByMasterComment(master);
   if(ticket <= 0)
   {
      Ack(cmd_id, true, 0, master, symbol, "", 0, 0, 0, "already_closed");
      return;
   }
   if(!PositionSelectByTicket((ulong)ticket))
   {
      Ack(cmd_id, true, ticket, master, symbol, "", 0, 0, 0, "gone");
      return;
   }
   string sym = PositionGetString(POSITION_SYMBOL);
   double vol = PositionGetDouble(POSITION_VOLUME);
   double profit = PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
   long type = PositionGetInteger(POSITION_TYPE);

   MqlTradeRequest req;
   MqlTradeResult  res;
   ZeroMemory(req);
   ZeroMemory(res);
   req.action    = TRADE_ACTION_DEAL;
   req.position  = (ulong)ticket;
   req.symbol    = sym;
   req.volume    = vol;
   req.deviation = 50;
   req.magic     = InpMagic;
   req.comment   = "PB_CLOSE";
   req.type_filling = ORDER_FILLING_IOC;
   if(type == POSITION_TYPE_BUY)
   {
      req.type  = ORDER_TYPE_SELL;
      req.price = SymbolInfoDouble(sym, SYMBOL_BID);
   }
   else
   {
      req.type  = ORDER_TYPE_BUY;
      req.price = SymbolInfoDouble(sym, SYMBOL_ASK);
   }
   bool ok = OrderSend(req, res);
   Ack(cmd_id, ok, ticket, master, sym, "", vol, res.price, profit,
       ok ? "" : IntegerToString((int)res.retcode));
}

void SendHello()
{
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   string json = "{";
   json += "\"login\":" + IntegerToString((int)login) + ",";
   json += "\"token\":\"" + JsonEscape(InpToken) + "\",";
   json += "\"balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + ",";
   json += "\"equity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2) + ",";
   json += "\"currency\":\"" + JsonEscape(AccountInfoString(ACCOUNT_CURRENCY)) + "\",";
   json += "\"server\":\"" + JsonEscape(AccountInfoString(ACCOUNT_SERVER)) + "\"";
   json += "}";
   string out;
   if(HttpPostJson(g_base + "/ea/hello", json, out))
      Print("EA hello ok: ", out);
   else
      Print("EA hello FAILED — check WebRequest URL allow list");
}

void PollOnce()
{
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   string url = g_base + "/ea/poll?login=" + IntegerToString((int)login)
              + "&token=" + InpToken
              + "&balance=" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2)
              + "&equity=" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2);
   // token may need URL encoding — hex tokens are safe
   string out;
   if(!HttpGet(url, out))
      return;
   if(!ExtractJsonBool(out, "can_copy", true))
   {
      Comment("PumpingBot EA: LOCKED (daily 25% / admin unlock)");
      return;
   }
   Comment("PumpingBot EA: ONLINE — waiting for master copies");

   // naive split on copy_open / copy_close objects inside commands array
   int pos = 0;
   while(true)
   {
      int o = StringFind(out, "\"type\"", pos);
      if(o < 0) break;
      int start = o;
      // walk back to nearest {
      for(int b = o; b >= 0 && b > o - 80; b--)
      {
         if(StringGetCharacter(out, b) == '{')
         {
            start = b;
            break;
         }
      }
      int depth = 0;
      int end = -1;
      for(int i = start; i < StringLen(out); i++)
      {
         ushort c = StringGetCharacter(out, i);
         if(c == '{') depth++;
         else if(c == '}')
         {
            depth--;
            if(depth == 0) { end = i; break; }
         }
      }
      if(end < 0) break;
      string cmd = StringSubstr(out, start, end - start + 1);
      string typ = ExtractJsonString(cmd, "type");
      if(typ == "copy_open") DoCopyOpen(cmd);
      else if(typ == "copy_close") DoCopyClose(cmd);
      pos = end + 1;
   }
}

int OnInit()
{
   g_base = InpServerUrl;
   while(StringLen(g_base) > 0 && StringGetCharacter(g_base, StringLen(g_base) - 1) == '/')
      g_base = StringSubstr(g_base, 0, StringLen(g_base) - 1);

   if(StringLen(InpToken) < 8)
   {
      Alert("PumpingBot: InpToken khali hai — App → PC Setup se EA Token paste karo");
      return INIT_FAILED;
   }
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
      Alert("PumpingBot: AutoTrading / Algo Trading ON karo");

   SendHello();
   g_timer = MathMax(500, InpPollMs);
   EventSetMillisecondTimer(g_timer);
   Print("PumpingBotFollower started server=", g_base, " login=", AccountInfoInteger(ACCOUNT_LOGIN));
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   PollOnce();
}

void OnTick()
{
   // timer-driven
}
