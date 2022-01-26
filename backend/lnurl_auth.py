import asyncio
from binascii import unhexlify
from io import BytesIO
from urllib.parse import parse_qs, urlencode, urlparse
import hmac
import hashlib
from lnurl import LnurlErrorResponse
import json
from ecdsa import SECP256k1, SigningKey
from typing import Optional
import urllib

def lnurlauth_key(randstr: str, domain: str) -> SigningKey:
    hashing_key = hashlib.sha256(randstr.encode("utf-8")).digest()
    linking_key = hmac.digest(hashing_key, domain.encode("utf-8"), "sha256")
    return SigningKey.from_string(
        linking_key, curve=SECP256k1, hashfunc=hashlib.sha256
    )

def int_to_bytes_suitable_der(x: int) -> bytes:
    """for strict DER we need to encode the integer with some quirks"""
    b = x.to_bytes((x.bit_length() + 7) // 8, "big")
    if len(b) == 0:
        # ensure there's at least one byte when the int is zero
        return bytes([0])
    if b[0] & 0x80 != 0:
        # ensure it doesn't start with a 0x80 and so it isn't
        # interpreted as a negative number
        return bytes([0]) + b
    return b

def encode_strict_der(r_int, s_int, order):
    # if s > order/2 verification will fail sometimes
    # so we must fix it here (see https://github.com/indutny/elliptic/blob/e71b2d9359c5fe9437fbf46f1f05096de447de57/lib/elliptic/ec/index.js#L146-L147)
    if s_int > order // 2:
        s_int = order - s_int
    # now we do the strict DER encoding copied from
    # https://github.com/KiriKiri/bip66 (without any checks)
    r = int_to_bytes_suitable_der(r_int)
    s = int_to_bytes_suitable_der(s_int)
    r_len = len(r)
    s_len = len(s)
    sign_len = 6 + r_len + s_len
    signature = BytesIO()
    signature.write(0x30 .to_bytes(1, "big", signed=False))
    signature.write((sign_len - 2).to_bytes(1, "big", signed=False))
    signature.write(0x02 .to_bytes(1, "big", signed=False))
    signature.write(r_len.to_bytes(1, "big", signed=False))
    signature.write(r)
    signature.write(0x02 .to_bytes(1, "big", signed=False))
    signature.write(s_len.to_bytes(1, "big", signed=False))
    signature.write(s)
    return signature.getvalue()

def perform_lnurlauth(randstr: str, callback: str) -> Optional[LnurlErrorResponse]:
	cb = urlparse(callback)
	# recv k1 from server
	k1 = unhexlify(parse_qs(cb.query)["k1"][0])
	# derive keypair using randstr and domain
	key = lnurlauth_key(randstr, cb.netloc)
	# use keypair to sign digest
	sig = key.sign_digest_deterministic(k1, sigencode=encode_strict_der)
	# take k1, key, and sig and send it back to the URL
	callback = callback.split("?")[0] + "?" + urllib.parse.urlencode({
		"k1": k1.hex(),
		"key": key.verifying_key.to_string("compressed").hex(),
		"sig": sig.hex(),
	}) 
	return callback
		

if __name__ == "__main__":
    cb = "https://api.kollider.xyz/v1/auth/ln_login?tag=login&k1=7b110f87c049a9a6043f243424c394b22b4d0161232df3af8079d28d1b6fc143"
    asyncio.run(perform_lnurlauth("konstiscool", cb))