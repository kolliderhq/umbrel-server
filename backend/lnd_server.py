from urllib import response
from utils import *
from lnd_client import LndClient
from time import sleep
from threading import Lock
import json
import threading
import lnurl
from urllib.parse import urlparse, parse_qs
import requests
from lnurl_auth import perform_lnurlauth
import hashlib
import zmq

SOCKET_ADDRESS = "tcp://*:5556"
SOCKET_PUB_ADDRESS = "tcp://*:5557"

SEED_WORD = hashlib.sha256("cheers to you until all enternity and here is my entry ser.".encode("utf-8")).digest()

def lnd_invoice_publisher(ln_client):
	context = zmq.Context()
	socket = context.socket(zmq.PUB)
	socket.bind(SOCKET_PUB_ADDRESS)
	def on_invoice(invoice):
		data = {
			"payment_request": invoice.payment_request,
			"value": invoice.value,
			"settled": invoice.settled
		}
		if data["settled"]:
			response = {
				"type": "received_payment",
				"data": {
					"payment_request": data["payment_request"],
					"amount": data["value"]
				}
			}
			socket.send_multipart(["invoices".encode("utf-8"), json.dumps(response).encode("utf8")])

	ln_client.sub_invoices(on_invoice)

def lnd_node_server(lnd_client):
	print("Started lnd node server")
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
			if action == "get_node_info":
				res = lnd_client.get_info()
				response = {
					"type": "getNodeInfo",
					"data": {
						"identity_pubkey": res.identity_pubkey,
						"alias": res.alias,
						"num_active_channels": res.num_active_channels,
						"num_peers": res.num_peers,
						"block_height": res.block_height,
						"block_hash": res.block_hash,
						"synced_to_chain": res.synced_to_chain,
						"best_header_timestamp": res.best_header_timestamp,
						"version": res.version, 
						"color": res.color,
						"synced_to_graph": res.synced_to_graph
					}
				}
				socket.send_json(response)
				continue
			if action == "create_invoice":
				message = "kollider"
				res = lnd_client.add_invoice(data["amount"], message)
				response = {
					"type": "createInvoice",
					"data": {
						"paymentRequest": res.payment_request
					}
				}
				socket.send_json(response)
				continue
			if action == "send_payment":
				res = lnd_client.send_payment(data["payment_request"])
				response = {
					"type": "sendPayment",
					"data": {
						"status": "success",
					}
				}
				socket.send_json(response)
				continue
			if action == "get_channel_balances":
				res = lnd_client.get_channel_balances()
				response = {
					"type": "getChannelBalances",
					"data": {
						"local": res.local_balance.sat,
						"localMsat": res.local_balance.msat,
						"remote": res.remote_balance.sat,
						"remoteMsat": res.remote_balance.msat
					}
				}
				socket.send_json(response)
				continue
			if action == "get_wallet_balances":
				res = lnd_client.get_onchain_balance()
				response = {
					"type": "getWalletBalances",
					"data": {
						"confirmed_balance": res.confirmed_balance,
						"total_balance": res.total_balance,
					}
				}
				socket.send_json(response)
				continue
			if action == "lnurl_auth":
				decoded_url = lnurl.decode(data["lnurl"])
				res = lnd_client.sign_message(SEED_WORD)
				lnurl_auth_signature = perform_lnurlauth(res.signature, decoded_url)
				try:
					_ = requests.get(lnurl_auth_signature)
					response = {
						"type": "lnurl_auth",
						"data": {
							"status": "success"
						}
					}
					socket.send_json(response)
				except Exception as e:
					print(e)
				continue
		sleep(0.5)
