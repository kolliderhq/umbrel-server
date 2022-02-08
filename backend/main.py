from ast import parse
from distutils.sysconfig import customize_compiler
from os import get_inheritable, environ
from random import seed
from kollider_api_client.ws import KolliderWsClient
from kollider_api_client.rest import KolliderRestClient
from utils import *
from lnd_client import LndClient
from kollider_msgs import OpenOrder, Position, TradableSymbol, Ticker
from time import sleep
from threading import Lock
import json
from math import floor
import uuid
from pprint import pprint
import threading
import lnurl
from lnurl.types import Url
from urllib.parse import urlparse, parse_qs
import requests
from lnurl_auth import perform_lnurlauth
import hashlib
from lnd_server import lnd_node_server, lnd_invoice_publisher
from lnhedgehog import HedgerEngine
from utils import setup_custom_logger

import zmq


class ReplaceClearnetUrl(Url):
    allowed_schemes = {"http", "https"}


def main():
    lnurl.types.ClearnetUrl = ReplaceClearnetUrl
    with open('config.json') as a:
        settings = json.load(a)

    logger = setup_custom_logger("lnhedgehog", settings.get("log_level"))

    kollider_api_key = settings["kollider"]["api_key"]
    kollider_url = settings["kollider"]["ws_url"]
    kollider_passphrase = settings["kollider"]["api_passphrase"]
    kollider_secret = settings["kollider"]["api_secret"]

    node_url = ""
    if environ.get("LND_IP") is None:
        node_url = settings["lnd"]["node_url"]
    else:
        node_url = f"{environ['LND_IP']}:10009"
    macaroon_path = settings["lnd"]["admin_macaroon_path"]
    tls_path = settings["lnd"]["tls_path"]

    lnd_client = LndClient(node_url, macaroon_path, tls_path, logger)
    rn_engine = HedgerEngine(lnd_client, logger)

    lock = Lock()

    lnd_node_server_thread = threading.Thread(
        target=lnd_node_server, daemon=False, args=(lnd_client, logger))
    lnd_node_server_thread.start()

    lnd_publisher_thread = threading.Thread(
        target=lnd_invoice_publisher, daemon=True, args=(lnd_client, ))
    lnd_publisher_thread.start()

    if kollider_api_key and kollider_passphrase and kollider_passphrase and kollider_url:
        rn_engine.connect(kollider_url, kollider_api_key,
                          kollider_secret, kollider_passphrase)
        hedger_thread = threading.Thread(
            target=rn_engine.start, daemon=True, args=(settings,))
        hedger_thread.start()

    while True:
        pass


if __name__ in "__main__":
    main()
