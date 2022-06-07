from time import sleep
from kollider_api_client.rest import KolliderRestClient
import json
import lnurl
import hashlib
import requests
from lnurl_auth import perform_lnurlauth
from lnd_client import LndClient
from os import environ

SEED_WORD = hashlib.sha256("cheers to you until all enternity and here is my entry ser.".encode("utf-8")).digest()

def liq_protection(ln_client, logger):
    KOLLIDER_JWT = ""
    KOLLIDER_JWT_REFRESH = ""
    lnurl_resp = requests.get("https://api.kollider.xyz/v1/auth/external/lnurl_auth")
    logger.debug("Ext lnurl_auth status=%d", lnurl_resp.status_code)
    if lnurl_resp.status_code == 201:
        lnurl_resp_parsed = lnurl_resp.json()
        decoded_url = lnurl.decode(lnurl_resp_parsed["lnurl_auth"])
        res = ln_client.sign_message(SEED_WORD)
        lnurl_auth_signature = perform_lnurlauth(res.signature, decoded_url)
        try:
            auth_res = requests.get(lnurl_auth_signature)
            logger.debug("Authing liq_protection res=%d", auth_res.status_code)
            if auth_res.status_code == 201:
                auth_res_parsed = auth_res.json()
                if "token" in auth_res_parsed.keys():
                    KOLLIDER_JWT = auth_res_parsed["token"]
                    KOLLIDER_JWT_REFRESH = auth_res_parsed["refresh"]
                else:
                    logger.debug("Failed to locate JWT")
        except Exception as e:
            logger.debug(f"Error on lnurl_auth: {e}")
    while KOLLIDER_JWT == "":
        sleep(2)
    product_ids = []
    mark_prices = {}
    rest = KolliderRestClient(base_url="https://api.kollider.xyz/v1", jwt=KOLLIDER_JWT, jwt_refresh=KOLLIDER_JWT_REFRESH)
    products_parsed = rest.get_tradeable_symbols()
    if products_parsed is not None:
        for key in products_parsed.keys():
            product_ids.append(key)
    while True:
        for key in product_ids:
            rest_ticker = rest.get_ticker(key)
            if rest_ticker is not None:
                mark_prices[key] = int(float(rest_ticker["best_ask"]) + float(rest_ticker["best_bid"])) / 2
        positions_parsed = rest.get_positions()
        # logger.debug("Positions: %s", positions_parsed)
        if positions_parsed is not None:
            if "error" in positions_parsed:
                if positions_parsed["error"] == "Expired":
                    logger.debug("Renewing expired JWT")
                    renew_resp = rest.renew_jwt()
                    logger.debug("JWT renewal resp: %s", renew_resp)
            else:
                for key in positions_parsed.keys():
                    if key in mark_prices:
                        liq_price = float(positions_parsed[key]['liq_price'])
                        if positions_parsed[key]['side'] == "Bid":
                            liq_diff = mark_prices[key] - liq_price
                            percent_diff = liq_diff / float(mark_prices[key])
                            amount = int(float(positions_parsed[key]['mark_value']) / float(positions_parsed[key]['leverage']))
                            amount /= 10
                            if percent_diff <= 0.02:
                                # add_margin
                                logger.debug("Adding margin for position (%s) %d sats", key, amount)
                                resp_parsed = rest.change_margin(action="Add", symbol=key, amount=amount)
                                logger.debug("Add margin response: %s", resp_parsed)
                            elif percent_diff >= (0.04 * float(positions_parsed[key]['leverage'])):
                                # remove_margin
                                logger.debug("Deleting margin for position (%s) %d sats", key, amount)
                                resp_parsed = rest.change_margin(action="Delete", symbol=key, amount=amount)
                                logger.debug("Delete margin response: %s", resp_parsed)
                        else:
                            liq_diff = liq_price - mark_prices[key]
                            percent_diff = liq_diff / float(liq_price)
                            amount = int(float(positions_parsed[key]['mark_value']) / float(positions_parsed[key]['leverage']))
                            amount /= 10
                            if percent_diff <= 0.02:
                                # add_margin
                                logger.debug("Adding margin for position (%s) %d sats", key, amount)
                                resp_parsed = rest.change_margin(action="Add", symbol=key, amount=amount)
                                logger.debug("Add margin response: %s", resp_parsed)
                            elif percent_diff >= (0.04 * float(positions_parsed[key]['leverage'])):
                                # remove_margin
                                logger.debug("Deleting margin for position (%s) %d sats", key, amount)
                                resp_parsed = rest.change_margin(action="Delete", symbol=key, amount=amount)
                                logger.debug("Delete margin response: %s", resp_parsed)
                    else:
                        logger.debug("Have no mark prices for key %s", key)
        sleep(10)

if __name__ == "__main__":
    with open('config.json') as a:
        settings = json.load(a)
    node_url = ""
    if environ.get("LND_IP") is None:
        node_url = settings["lnd"]["node_url"]
    else:
        node_url = f"{environ['LND_IP']}:10009"
    macaroon_path = settings["lnd"]["admin_macaroon_path"]
    tls_path = settings["lnd"]["tls_path"]
    lnd_client = LndClient(node_url, macaroon_path, tls_path, logger)
    liq_protection(lnd_client)