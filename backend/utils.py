from ecdsa import SECP256k1, SigningKey
import hashlib
import logging

SATOSHI_MULTIPLIER = 100000000

def opposite_side(side):
	if side == "Bid":
		return "Ask"
	return "Bid"

def sats_to_dollars(sats_amount, price):
	return int((sats_amount / SATOSHI_MULTIPLIER * price) * 1000) / 1000

def lnurlauth_key(self, domain: str) -> SigningKey:
	hashing_key = hashlib.sha256(self.id.encode("utf-8")).digest()
	linking_key = hmac.digest(hashing_key, domain.encode("utf-8"), "sha256")

	return SigningKey.from_string(
		linking_key, curve=SECP256k1, hashfunc=hashlib.sha256
	)

def setup_custom_logger(name, log_level="DEBUG"):

	if not log_level:
		log_level = "DEBUG"

	filename = name + ".log"

	logger = logging.getLogger(name)
	print(filename)
	formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(module)s > %(message)s')

	file_handler = logging.FileHandler(filename)
	stream_handler = logging.StreamHandler()

	stream_handler.setFormatter(formatter)
	file_handler.setFormatter(formatter)

	logger.addHandler(stream_handler)
	logger.addHandler(file_handler)

	logger.setLevel(log_level)
	logger.propagate = False

	logger.filemode='a'
	return logger