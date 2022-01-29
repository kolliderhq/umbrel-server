from ast import parse
from os import get_inheritable
from random import seed
import re
from kollider_api_client.ws import KolliderWsClient
from kollider_api_client.rest import KolliderRestClient
from utils import *
from lnd_client import LndClient
from kollider_msgs import OpenOrder, Position, TradableSymbol, Ticker, Orderbook, Trade
from time import sleep
from threading import Lock
import json
from math import floor
import uuid
from pprint import pprint
import threading
from custom_errors import *

import zmq
import copy

SOCKET_PUB_ADDRESS = "tcp://*:5559"
SOCKET_ADDRESS = "tcp://*:5558"

def save_to_settings(settings):
    with open(settings["settings_path"], 'w') as outfile:
        json.dump(settings, outfile, indent=4, sort_keys=True)

class HedgerState(object):
    position_quantity = 0
    ask_open_order_quantity = 0
    bid_open_order_quantity = 0
    target_quantity = 0
    target_value = 0
    is_locking = False
    lock_price = None
    side = None
    predicted_funding_payment = 0

    def to_dict(self):
        return {
            "position_quantity": self.position_quantity,
            "bid_open_order_quantity": self.bid_open_order_quantity,
            "ask_open_order_quantity": self.ask_open_order_quantity,
            "target_quantity": self.target_quantity,
            "target_value": self.target_value,
            "is_locking": self.is_locking,
            "lock_price": self.lock_price,
            "side": self.side,
            "predicted_funding_payment": self.predicted_funding_payment
        }


class StagedHedgeState(object):
    estimated_fill_price = None

    def to_dict(self):
        return {
            "estimated_fill_price": self.estimated_fill_price,
        }


class Wallet(object):

    def __init__(self):
        self.channel_balance = 0
        self.onchain_balance = 0
        self.kollider_balance = 0

    def update_channel_balance(self, balance):
        self.channel_balance = balance

    def update_onchain_balance(self, balance):
        self.onchain_balance = balance

    def update_kollider_balance(self, balance):
        self.kollider_balance = balance

    def to_dict(self):
        return {
            "channel_balance": self.channel_balance,
            "onchain_balance": self.onchain_balance,
            "kollider_balance": self.kollider_balance
        }

    def total_ln_balance(self):
        return self.channel_balance + self.kollider_balance


class HedgerEngine(KolliderWsClient):
    def __init__(self, lnd_client):
        self.kollider_api_key = None
        self.kollider_api_secret = None
        self.kollider_api_passphrase = None
        # Orders that are currently open on the Kollider platform.
        self.open_orders = {}
        # Positions that are currently open on the Kollider platform.
        self.positions = {}
        self.current_index_price = 0
        self.current_mark_price = 0
        self.target_fiat_currency = "USD"
        self.target_symbol = "BTCUSD.PERP"
        self.target_index_symbol = ".BTCUSD"
        self.orderbook = None
        self.ws_is_open = False
        self.contracts = {}

        self.hedge_value = 0
        self.staged_hedge_value = 0

        self.hedge_side = None
        self.target_leverage = 100

        # Last hedge state.
        self.last_state = HedgerState()

        # Summary of the connected node.
        self.node_info = None

        # Order type that is used to make trades on Kollider.
        self.order_type = "Market"

        self.wallet = Wallet()

        self.lnd_client = lnd_client

        self.last_ticker = Ticker()

        self.received_tradable_symbols = False

        # Average hourly funding rates for each symbol. Used
        # as an prediction of the next funding rate.
        self.average_hourly_funding_rates = {}

        self.is_locked = True
        self.has_live_market_order = False # protection against us sending redundant market orders

        context = zmq.Context()
        self.publisher = context.socket(zmq.PUB)
        self.publisher.bind(SOCKET_PUB_ADDRESS)

        self.settings = {}

    def has_kollider_creds(self):
        return self.kollider_api_key and self.kollider_api_secret and self.kollider_api_passphrase

    def to_dict(self):
        average_funding = self.average_hourly_funding_rates.get(
            self.target_symbol)
        average_funding = average_funding if average_funding else 0
        return {
            "node_info": self.node_info,
            "wallet": self.wallet.to_dict(),
            "current_index_price": self.current_index_price,
            "current_mark_price": self.current_mark_price,
            "last_state": self.last_state.to_dict(),
            "target_fiat_currency": self.target_fiat_currency,
            "target_symbol": self.target_index_symbol,
            "target_index_symbol": self.target_index_symbol,
            "hedge_value": self.hedge_value,
            "staged_hedge_value": self.staged_hedge_value,
            "average_hourly_funding_rate": average_funding
        }

    def set_params(self, **args):
        print(args)
        self.kollider_api_key = args["kollider"].get(
            "api_key") if args["kollider"].get("api_key") else None
        self.kollider_api_secret = args["kollider"].get(
            "api_secret") if args["kollider"].get("api_secret") else None
        self.kollider_api_passphrase = args["kollider"].get(
            "api_passphrase") if args["kollider"].get("api_passphrase") else None
        self.hedge_proportion = args.get(
            "hedge_proportion") if args.get("hedge_proportion") else 0
        self.hedge_side = args.get(
            "hedge_side") if args.get("hedge_side") else None
        self.hedge_value = args.get(
            "hedge_value") if args.get("hedge_value") else 0
        self.target_fiat_currency = args.get(
            "target_fiat_currency") if args.get("target_fiat_currency") else None
        self.target_symbol = args.get(
            "target_symbol") if args.get("target_symbol") else None
        self.target_index_price = args.get("target_index_symbol") if args.get(
            "target_index_symbol") else None
        self.target_leverage = args.get(
            "target_leverage") if args.get("target_leverage") else None
        self.order_type = args.get("order_type") if args.get(
            "order_type") else "Market"

    def publish_msg(self, msg, type):
        message = {
            "type": type,
            "data": msg,
        }
        self.publisher.send_multipart(["hedger_stream".encode("utf-8"), json.dumps(message).encode("utf-8")])

    def on_open(self, event):
        self.auth()
        sleep(1)
        self.sub_index_price([self.target_index_symbol])
        self.sub_mark_price([self.target_symbol])
        self.sub_ticker([self.target_symbol])
        self.sub_position_states()
        self.sub_orderbook_l2(self.target_symbol)
        self.fetch_positions()
        self.fetch_open_orders()
        self.fetch_tradable_symbols()
        self.fetch_ticker(self.target_symbol)
        self.fetch_balances()
        self.ws_is_open = True

    def on_pong(self, ctx, event):
        None

    def on_error(self, ctx, event):
        pass

    def on_message(self, _ctx, msg):
        msg = json.loads(msg)
        t = msg["type"]
        data = msg["data"]
        if t == 'authenticate':
            if data["message"] == "success":
                self.is_authenticated = True
            else:
                print("Auth Unsuccessful: {}".format(data))
                self.is_authenticated = False
                self.__reset()

        elif t == 'index_values':
            self.current_index_price = float(data["value"])

        elif t == 'mark_prices':
            self.current_mark_price = float(data["price"])

        elif t == 'positions':
            print("Received positions.")
            positions = data["positions"]
            for key, value in positions.items():
                self.positions[key] = Position(msg=value)

        elif t == 'open_orders':
            print("Received open orders")
            open_orders = data["open_orders"]
            for symbol, open_orders in open_orders.items():
                for open_order in open_orders:
                    if self.open_orders.get(symbol) is None:
                        self.open_orders[symbol] = []
                    oo = OpenOrder(msg=open_order)
                    self.open_orders[symbol].append(oo)

        elif t == 'tradable_symbols':
            for symbol, contract in data["symbols"].items():
                self.contracts[symbol] = TradableSymbol(msg=contract)
            self.received_tradable_symbols = True

        elif t == 'open':
            open_order = data
            contract = self.get_contract()
            dp = contract.price_dp
            open_order_parsed = OpenOrder(data, dp)
            if self.open_orders.get(open_order_parsed.symbol) is None:
                self.open_orders[open_order_parsed.symbol] = []
            self.open_orders[open_order_parsed.symbol].append(
                open_order_parsed)

        elif t == 'done':
            symbol = data["symbol"]
            order_id = data["order_id"]
            self.open_orders[symbol] = [
                open_order for open_order in self.open_orders[symbol] if open_order.order_id != order_id]

        elif t == 'trade':
            trade = Trade(data)
            if trade.order_type == "Market":
                self.has_live_market_order = False # we are assuming there's only 1 market order

        elif t == 'fill':
            symbol = msg["symbol"]
            order_id = msg["order_id"]
            quantity = msg["quantity"]
            orders = self.open_orders.get(symbol)

            if orders is None:
                return
            for order in orders:
                if order.order_id == order_id:
                    order.quantity -= quantity

        elif t == 'position_states':
            position = Position(msg=data)
            if position.symbol == self.target_symbol:
                self.positions[self.target_symbol] = position
            self.publish_msg(position.to_dict(), "position_state")
        elif t == 'ticker':
            self.last_ticker = Ticker(msg=data)

        elif t == 'order_invoice':
            print("Received Pay to Trade invoice for: {}".format(
                data["margin"]))
            res = self.lnd_client.send_payment(data["invoice"])

        elif t == 'settlement_request':
            print("Received settlement Request")
            amount = data["amount"]
            self.make_withdrawal(amount, "Kollider Trade Settlement")

        elif t == "level2state":
            if data["update_type"] == "snapshot":
                ob = copy.copy(Orderbook("kollider"))
                for key, value in data["bids"].items():
                    ob.bids[int(key)] = value

                for key, value in data["asks"].items():
                    ob.asks[int(key)] = value

                if self.orderbook is not None:
                    del self.state.orderbooks[data["symbol"]]
                self.orderbook = ob
            else:
                bids = data["bids"]
                asks = data["asks"]
                if not self.orderbook:
                    return
                if bids:
                    for price, quantity in bids.items():
                        if quantity == 0:
                            del self.orderbook.bids[int(price)]
                        else:
                            self.orderbook.bids[int(price)] = quantity
                if asks:
                    for price, quantity in asks.items():
                        if quantity == 0:
                            del self.orderbook.asks[int(price)]
                        else:
                            self.orderbook.asks[int(price)] = quantity

        elif t == 'balances':
            total_balance = 0
            cash_balance = float(data["cash"])
            if cash_balance > 1:
                self.make_withdrawal(cash_balance, "Kollider Payout")
            total_balance += cash_balance
            isolated_margin = data["isolated_margin"].get(self.target_symbol)
            if isolated_margin is not None:
                total_balance += float(isolated_margin)

            order_margin = data["order_margin"].get(self.target_symbol)
            if order_margin is not None:
                total_balance += float(order_margin)
            self.wallet.update_kollider_balance(total_balance)

        elif t == 'error':
            print("ERROR")
            print(data)

    def calc_sat_value(self, qty, price, contract):
        if contract.is_inverse_priced:
            return 1 / price * qty * SATOSHI_MULTIPLIER
        else:
            return price * qty * SATOSHI_MULTIPLIER

    def calc_average_price(self, qty_1, qty_2, price_1, price_2, contract):
        if contract.is_inverse_priced:
            return (qty_1 + qty_2) / (qty_1 / price_1 + qty_2 / price_2)
        return (qty_1 * price_1 + qty_2 * price_2) / (qty_1 + qty_2)

    def convert_price(self, price, contract):
        return price / 10 ** contract.price_dp

    def calc_average_entry(self, side, amount_in_sats):
        bucket = None
        if side == "bid":
            bucket = reversed(self.orderbook.bids.items())
        else:
            bucket = self.orderbook.asks.items()

        remaining_value = amount_in_sats

        contract = self.contracts.get(self.target_symbol)
        if not contract:
            return

        running_numerator = 0
        running_denominator = 0

        for (price, qty) in bucket:
            price = self.convert_price(price, contract)
            value = self.calc_sat_value(qty, price, contract)
            remaining_value -= value
            if contract.is_inverse_priced:
                running_numerator += qty
                running_denominator += qty / price
            else:
                running_numerator += qty * price
                running_denominator += qty
            if remaining_value <= 0:
                break

        if remaining_value <= 0:
            return running_numerator / running_denominator

        raise InsufficientBookDepth(remaining_value)

    def estimate_hedge_price(self):
        if self.staged_hedge_value > 0:
            staged_hedge_state = StagedHedgeState()
            position = self.positions.get(self.target_symbol)
            contract = self.contracts.get(self.target_symbol)
            if not contract:
                return
            current_hedged_value = 0
            if position:
                current_hedged_value = self.calc_sat_value(position.quantity, position.entry_price, contract)
                staged_hedge_state.estimated_fill_price = position.entry_price

            diff_qty = self.staged_hedge_value - current_hedged_value

            if diff_qty > 0:
                try:
                    staged_hedge_state.estimated_fill_price = self.calc_average_entry("bid", diff_qty)
                    if position:
                        staged_hedge_state.estimated_fill_price = self.calc_average_price(diff_qty, position.quantity, staged_hedge_state.estimated_fill_price, position.entry_price)
                except InsufficientBookDepth as err:
                    error = {
                        "msg": "InsufficientBookDepth",
                        "remaining": err.remaining_value,
                    }
                    self.publish_msg(error, "error")
                    return

            msg = {
                "type": "estimate_hedge_price",
                "data": {
                        "current_hedged_value": current_hedged_value,
                        "staged_targed_hedge_value": self.staged_hedge_value,
                        "price": staged_hedge_state.to_dict(),
                }
            }
            self.publisher.send_multipart(
                ["hedger_stream".encode("utf-8"), json.dumps(msg).encode("utf-8")])

    def make_withdrawal(self, amount, message):
        amt = int(amount)
        res = self.lnd_client.add_invoice(amt, message)
        withdrawal_request = {
            "withdrawal_request": {
                "Ln": {
                    "payment_request": res.payment_request,
                    "amount": amt,
                }
            }
        }
        self.withdrawal_request(withdrawal_request)

    def cancel_all_orders_on_side(self, side):
        orders = self.open_orders.get(self.target_symbol)

        if orders is None:
            return

        for order in orders:
            if order.side == side:
                self.cancel_order(
                    {"order_id": order.order_id, "symbol": self.target_symbol, "settlement_type": "Delayed"})

    def calc_contract_value(self):
        if self.contracts.get(self.target_symbol) is not None:
            contract = self.get_contract()
            price = self.current_mark_price
            if contract.is_inverse_priced:
                return contract.contract_size / price * SATOSHI_MULTIPLIER
            else:
                return contract.contract_size * price * SATOSHI_MULTIPLIER
        else:
            raise Exception("Target contract not available")

    def calc_number_of_contracts_required(self, value_target):
        try:
            value_per_contract = self.calc_contract_value()
            qty_of_contracts = floor(value_target / value_per_contract)
            return qty_of_contracts
        except Exception as e:
            print(e)

    def get_open_orders(self):
        return self.open_orders.get(self.target_symbol)

    def get_open_position(self):
        return self.positions.get(self.target_symbol)

    def get_contract(self):
        return self.contracts.get(self.target_symbol)

    def get_best_price(self, side):
        if side == "Bid":
            return self.last_ticker.best_bid
        else:
            return self.last_ticker.best_ask

    def update_average_funding_rates(self):
        rest_client = KolliderRestClient(
            "http://api.staging.kollider.internal/v1/")
        average_funding_rates = rest_client.get_average_funding_rates()
        for funding_rate in average_funding_rates["data"]:
            self.average_hourly_funding_rates[funding_rate["symbol"]
                                              ] = funding_rate["mean_funding_rate"]

    def build_target_state(self):
        state = HedgerState()

        total_value = self.wallet.total_ln_balance()
        # hedge_value = (target_value * self.hedge_proportion)
        if total_value < self.hedge_value:
            print("error can't hedge more than you have.")
            return
        hedge_value = self.hedge_value

        # The number a contracts we need to cover the value.
        target_number_of_contracts = self.calc_number_of_contracts_required(
            hedge_value)

        # Getting current open orders.
        open_orders = self.get_open_orders()

        open_ask_order_quantity = 0
        open_bid_order_quantity = 0

        current_position_quantity = 0

        if open_orders is not None:
            open_bid_order_quantity = sum(
                [open_order.quantity for open_order in open_orders if open_order.side == "Bid"])
            open_ask_order_quantity = sum(
                [open_order.quantity for open_order in open_orders if open_order.side == "Ask"])

        # Getting current position on target symbol.
        open_position = self.get_open_position()

        if open_position is not None:
            current_position_quantity = open_position.quantity
            state.side = open_position.side
            # If current position is on the wrong side we adding a minus to reflect that.
            if open_position.side != opposite_side(self.hedge_side):
                current_position_quantity = current_position_quantity * -1
            else:
                state.lock_price = open_position.entry_price

        state.target_quantity = target_number_of_contracts
        state.target_value = hedge_value
        state.bid_open_order_quantity = open_bid_order_quantity
        state.ask_open_order_quantity = open_ask_order_quantity
        state.position_quantity = current_position_quantity

        hourly_funding_rate = self.average_hourly_funding_rates.get(
            self.target_symbol)
        if hourly_funding_rate is not None:
            state.predicted_funding_payment = hedge_value * hourly_funding_rate
        else:
            state.predicted_funding_payment = 0

        self.last_state = state

        return state

    def converge_state(self, state):
        # Nothing needs to be done if target is current.

        target_side = opposite_side(self.hedge_side)

        current = 0
        if target_side == "Bid":
            current = state.bid_open_order_quantity + state.position_quantity
        else:
            current = state.ask_open_order_quantity + state.position_quantity

        target = state.target_quantity

        if target == current:
            self.cancel_all_orders_on_side(self.hedge_side)
            return

        contract = self.get_contract()

        dp = contract.price_dp

        side = None

        if target > current:
            side = opposite_side(self.hedge_side)
            self.cancel_all_orders_on_side(self.hedge_side)

        elif target < current:
            side = self.hedge_side
            if target_side == "Bid" and state.bid_open_order_quantity > 0:
                self.cancel_all_orders_on_side(target_side)
                return
            elif target_side == "Ask" and state.ask_open_order_quantity > 0:
                self.cancel_all_orders_on_side(target_side)
                return


        if not self.has_live_market_order: # prevent redundant market orders while waiting for fill
            price = self.get_best_price(side)

            # Adding the order to the top of the book by adding/subtracting one tick.
            if side == "Bid":
                price += contract.tick_size
            else:
                price -= contract.tick_size

            price = int(price * (10**dp))

            qty_required = abs(target - current)

            order = {
                'symbol': self.target_symbol,
                'side': side,
                'quantity': qty_required,
                'leverage': self.target_leverage,
                'price': price,
                'order_type': self.order_type,
                'margin_type': 'Isolated',
                'settlement_type': 'Instant',
                'ext_order_id': str(uuid.uuid4()),
            }

            self.place_order(order)

            if self.order_type == "Market":
                self.has_live_market_order = True

    def check_state(self, state):
        side = opposite_side(self.hedge_side)
        position = self.positions.get(self.target_symbol)
        contract = self.contracts.get(self.target_symbol)
        if position:
            hedged_value = self.calc_sat_value(position.quantity, position.entry_price, contract)
            if self.hedge_value == 0:
                self.is_locked = False
            else:
                if abs(hedged_value - self.hedge_value) / self.hedge_value < 0.01:
                    self.is_locked = True
                    self.has_live_market_order = True
        return state

    def print_state(self, state):
        pprint(state.to_dict())
        pprint(self.wallet.to_dict())

    def update_node_info(self):
        try:
            node_info = self.lnd_client.get_info()
            self.node_info = {
                "alias": node_info.alias,
                "identity_pubkey": node_info.identity_pubkey,
                "num_active_channels": node_info.num_active_channels,
            }
        except Exception as e:
            print(e)

    def update_wallet_data(self):
        channel_balances = self.lnd_client.get_channel_balances()
        onchain_balances = self.lnd_client.get_onchain_balance()
        self.wallet.update_channel_balance(channel_balances.balance)
        self.wallet.update_onchain_balance(onchain_balances.total_balance)

    def cli(self):
        print("Hedger Cli")
        context = zmq.Context()
        socket = context.socket(zmq.REP)
        socket.bind(SOCKET_ADDRESS)
        while True:
            message = ""
            try:
                message = socket.recv_json()
            except Exception as e:
                print(e)
                continue
            if message.get("action") is not None:
                action = message.get("action")
                data = message.get("data")
                if action == "set_kollider_credentials":
                    api_key = data.get("api_key")
                    api_secret = data.get("api_secret")
                    api_passphrase = data.get("api_passphrase")
                    if api_key and api_secret and api_passphrase:
                        self.kollider_api_key = api_key
                        self.kollider_api_secret = api_secret
                        self.kollider_api_passphrase = api_passphrase
                        response = {
                            "type": "set_kollider_credentials",
                            "data": {
                                    "status": "success"
                            }
                        }
                        socket.send_json(response)
                        continue
                    else:
                        response = {
                            "type": "set_kollider_credentials",
                            "data": {
                                    "status": "Plase provide all credentials"
                            }
                        }
                        socket.send_json(response)
                        continue

                if action == "get_hedge_state":
                    response = {
                        "type": "set_hedge_state",
                        "data": {
                                "state": self.to_dict()
                        }
                    }
                    socket.send_json(response)
                    continue

                if action == "get_wallet_state":
                    response = {
                        "type": "get_wallet_state",
                        "data": {
                                "state": self.wallet.to_dict()
                        }
                    }
                    socket.send_json(response)
                    continue

                if action == "create_new_hedge":
                    if data["is_staged"]:
                        self.staged_hedge_value = data["amount"]
                    else:
                        self.hedge_value = data["amount"]
                        self.settings["hedge_value"] = data["amount"]
                        save_to_settings(self.settings)
                    response = {
                        "type": "create_new_hedge",
                        "data": {
                                "state": "success"
                        }
                    }
                    socket.send_json(response)
                    continue

                if action == "get_funding_history":
                    pass

                if action == "get_wallet_state":
                    pass
        sleep(0.5)

    def start(self, settings):
        print("Connecting to Kollider websockets..")
        pprint(settings)
        while not self.ws_is_open:
            pass
        print("Connected to websockets.")

        cycle_speed = settings["cycle_speed"]

        self.set_params(**settings)
        self.settings = settings

        self.update_node_info()

        cli_thread = threading.Thread(target=self.cli, daemon=False, args=())
        cli_thread.start()

        while True:
            if not self.has_kollider_creds():
                continue

            # Don't do anything if we haven't received the contracts.
            if not self.received_tradable_symbols and not self.is_authenticated:
                continue

            # Don't do anything if we haven't received mark or index price.
            if self.current_index_price == 0 or self.current_mark_price == 0:
                continue

            # Don't do anything if we have no ticker price.
            if self.last_ticker.last_side is None:
                continue

            self.update_wallet_data()
            self.estimate_hedge_price()

            self.update_average_funding_rates()

            # Getting current state.
            state = self.build_target_state()
            self.check_state(state)
            # Printing the state.
            # Converging to that state.
            self.converge_state(state)

            sleep(cycle_speed)
