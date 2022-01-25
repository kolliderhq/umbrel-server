from ecdsa import SECP256k1, SigningKey
import hashlib

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
