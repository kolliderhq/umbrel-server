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
import hashlib
from lnd_server import lnd_node_server, lnd_invoice_publisher
from liq_protection import liq_protection
from utils import setup_custom_logger

class ReplaceClearnetUrl(Url):
    allowed_schemes = {"http", "https"}


def main():
    lnurl.types.ClearnetUrl = ReplaceClearnetUrl
    with open('config.json') as a:
        settings = json.load(a)

    logger = setup_custom_logger("kollider-lnd-server", settings.get("log_level"))

    node_url = ""
    if environ.get("LND_IP") is None:
        node_url = settings["lnd"]["node_url"]
    else:
        node_url = f"{environ['LND_IP']}:10009"
    macaroon_path = settings["lnd"]["admin_macaroon_path"]
    tls_path = settings["lnd"]["tls_path"]

    lnd_client = LndClient(node_url, macaroon_path, tls_path, logger)

    lock = Lock()

    lnd_node_server_thread = threading.Thread(
        target=lnd_node_server, daemon=True, args=(lnd_client, logger))
    lnd_node_server_thread.start()

    lnd_publisher_thread = threading.Thread(
        target=lnd_invoice_publisher, daemon=True, args=(lnd_client, ))
    lnd_publisher_thread.start()

    liq_protection_thread = threading.Thread(
        target=liq_protection, daemon=True, args=(lnd_client, logger))
    liq_protection_thread.start()

    while True:
        if not lnd_node_server_thread.is_alive():
            logger.error("lnd_node_server_thread is dead. Trying to restart.")
            lnd_node_server_thread = threading.Thread(
                target=lnd_node_server, daemon=True, args=(lnd_client, logger))
            lnd_node_server_thread.start()

        if not lnd_publisher_thread.is_alive():
            logger.error("lnd_publisher_thread is dead. Trying to restart.")
            lnd_publisher_thread = threading.Thread(
                target=lnd_invoice_publisher, daemon=True, args=(lnd_client, ))
            lnd_publisher_thread.start()

        if not liq_protection_thread.is_alive():
            logger.error("liquidation_protection_thread is dead. Trying to restart.")
            liq_protection_thread = threading.Thread(
                target=liq_protection, daemon=True, args=(lnd_client, logger))
            liq_protection_thread.start()

if __name__ in "__main__":
    main()
