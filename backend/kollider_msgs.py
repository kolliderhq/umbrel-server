from BTrees.OOBTree import OOBTree
import copy

class Position(object):
    def __init__(self, msg=None):
        if msg:
            self.symbol = msg["symbol"]
            self.quantity = int(msg["quantity"])
            self.entry_price = float(msg["entry_price"])
            self.leverage = float(msg["leverage"])
            self.liq_price = float(msg["liq_price"])
            self.open_order_ids = msg["open_order_ids"]
            self.side = msg["side"]
            self.timestamp = msg["timestamp"]
            self.upnl = int(msg["upnl"])
            self.rpnl = float(msg["rpnl"])

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "leverage": self.leverage,
            "liq_price": self.liq_price,
            "open_order_ids": self.open_order_ids,
            "side": self.side,
            "timestamp": self.timestamp,
            "upnl": self.upnl,
            "rpnl": self.rpnl
        }

class OpenOrder(object):
    quantity = 0
    order_id = 0
    price = 0
    timestamp = ""
    filled = 0
    ext_order_id = ""
    oredr_type = ""
    side = ""
    symbol = ""
    leverage = 0
    margin_type = ""
    settlement_type = ""

    def __init__(self, msg=None, dp=None):
        if not dp:
            dp = 0
        if msg:
            self.quantity = int(msg["quantity"])
            self.order_id =  int(msg["order_id"])
            self.price = float(msg["price"]) * (10**-dp)
            self.timestamp = msg["timestamp"]
            self.filled = int(msg["filled"])
            self.ext_order_id = int(msg["order_id"])
            self.order_type = msg["order_type"]
            self.side =  msg["side"]
            self.symbol = msg["symbol"]
            self.leverage = float(msg["leverage"])
            self.margin_type = msg["margin_type"]
            self.settlement_type = msg["settlement_type"]

class TradableSymbol(object):

    def __init__(self, msg=None):
        if msg:
            self.base_margin = float(msg["base_margin"])
            self.contract_size = int(msg["contract_size"])
            self.is_inverse_priced = msg["is_inverse_priced"]
            self.last_price = float(msg["last_price"])
            self.maintenance_margin = float(msg["maintenance_margin"])
            self.max_leverage = float(msg["max_leverage"])
            self.price_dp = int(msg["price_dp"])
            self.symbol = msg["symbol"]
            self.underlying_symbol = msg["underlying_symbol"]
            self.tick_size = float(msg["tick_size"])

class Ticker(object):
    best_bid = 0
    best_ask = 0
    mid = 0
    last_price = 0
    last_quantity = 0
    last_side = None,
    symbol = None,

    def __init__(self, msg=None):
        if msg:
            self.best_bid = float(msg["best_bid"])
            self.best_ask = float(msg["best_ask"])
            self.mid = float(msg["mid"])
            self.last_price = float(msg["last_price"])
            self.quantity = float(msg["last_quantity"])
            self.last_side = msg["last_side"]
            self.symbol = msg["symbol"]


class Orderbook(object):

    def __init__(self, venue):
        self.bids = copy.copy(OOBTree())
        self.asks = copy.copy(OOBTree())
        self.level = "l2"
        self.venue = venue

