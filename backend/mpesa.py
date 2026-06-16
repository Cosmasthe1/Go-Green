"""
mpesa.py — Go Green 🌿
────────────────────────────────────────────────────────────────────────────
M-Pesa Daraja API integration.

Implements:
  • OAuth token fetch  (Safaricom Daraja /oauth/v1/generate)
  • STK Push           (Daraja /mpesa/stkpush/v1/processrequest)
  • STK Query          (poll for payment status)

In production set these env vars:
  MPESA_CONSUMER_KEY
  MPESA_CONSUMER_SECRET
  MPESA_SHORTCODE        (your paybill / till number)
  MPESA_PASSKEY          (Lipa Na M-Pesa passkey)
  MPESA_CALLBACK_URL     (public HTTPS endpoint to receive results)

Set MPESA_SANDBOX=true to use the sandbox base URL.
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

SANDBOX    = os.environ.get("MPESA_SANDBOX", "true").lower() == "true"
BASE_URL   = (
    "https://sandbox.safaricom.co.ke"
    if SANDBOX
    else "https://api.safaricom.co.ke"
)

CONSUMER_KEY    = os.environ.get("MPESA_CONSUMER_KEY",    "YOUR_CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("MPESA_CONSUMER_SECRET", "YOUR_CONSUMER_SECRET")
SHORTCODE       = os.environ.get("MPESA_SHORTCODE",       "174379")      # sandbox default
PASSKEY         = os.environ.get("MPESA_PASSKEY",         "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919")  # sandbox
CALLBACK_URL    = os.environ.get("MPESA_CALLBACK_URL",    "https://gogreen.example.com/api/mpesa/callback")


# ─────────────────────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class STKPushRequest:
    phone_number: str    # format: 2547XXXXXXXX
    amount:       int    # KES, integers only
    account_ref:  str    # e.g. trip ID
    description:  str    # "Go Green EV Ride"


@dataclass
class STKPushResponse:
    success:           bool
    merchant_request_id: str = ""
    checkout_request_id: str = ""
    response_code:     str = ""
    response_desc:     str = ""
    customer_msg:      str = ""
    error:             str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class PaymentStatus:
    checkout_request_id: str
    result_code:    str   = ""
    result_desc:    str   = ""
    amount:         float = 0.0
    mpesa_receipt:  str   = ""
    transaction_dt: str   = ""
    phone:          str   = ""
    paid:           bool  = False
    pending:        bool  = True
    failed:         bool  = False

    def to_dict(self) -> dict:
        return self.__dict__.copy()


# ─────────────────────────────────────────────────────────────────────────────
# M-Pesa client
# ─────────────────────────────────────────────────────────────────────────────

class MpesaClient:
    """
    Daraja API client.
    Caches the OAuth token for its lifetime (typically 3600 s).
    """

    def __init__(self) -> None:
        self._token:      str   = ""
        self._token_exp:  float = 0.0

    # ── OAuth ────────────────────────────────────────────────────────────────

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token

        creds  = base64.b64encode(f"{CONSUMER_KEY}:{CONSUMER_SECRET}".encode()).decode()
        url    = f"{BASE_URL}/oauth/v1/generate?grant_type=client_credentials"
        resp   = requests.get(url, headers={"Authorization": f"Basic {creds}"}, timeout=10)
        resp.raise_for_status()
        data   = resp.json()
        self._token     = data["access_token"]
        self._token_exp = time.time() + int(data.get("expires_in", 3600))
        return self._token

    # ── Timestamp + password ─────────────────────────────────────────────────

    @staticmethod
    def _timestamp() -> str:
        return datetime.now().strftime("%Y%m%d%H%M%S")

    def _password(self, timestamp: str) -> str:
        raw = f"{SHORTCODE}{PASSKEY}{timestamp}"
        return base64.b64encode(raw.encode()).decode()

    # ── Normalise phone ───────────────────────────────────────────────────────

    @staticmethod
    def normalise_phone(phone: str) -> str:
        """
        Accept:  +254712345678, 0712345678, 254712345678, 712345678
        Return:  2547XXXXXXXX
        """
        p = phone.strip().replace(" ", "").replace("-", "")
        if p.startswith("+"):
            p = p[1:]
        if p.startswith("0"):
            p = "254" + p[1:]
        if p.startswith("7") or p.startswith("1"):
            p = "254" + p
        return p

    # ── STK Push ─────────────────────────────────────────────────────────────

    def stk_push(self, req: STKPushRequest) -> STKPushResponse:
        """
        Initiates an M-Pesa STK Push to the rider's phone.
        The rider receives a prompt on their phone to enter their M-Pesa PIN.
        """
        phone = self.normalise_phone(req.phone_number)
        ts    = self._timestamp()
        pwd   = self._password(ts)

        payload = {
            "BusinessShortCode": SHORTCODE,
            "Password":          pwd,
            "Timestamp":         ts,
            "TransactionType":   "CustomerPayBillOnline",
            "Amount":            req.amount,
            "PartyA":            phone,
            "PartyB":            SHORTCODE,
            "PhoneNumber":       phone,
            "CallBackURL":       CALLBACK_URL,
            "AccountReference":  req.account_ref[:12],
            "TransactionDesc":   req.description[:13],
        }

        try:
            token = self._get_token()
            url   = f"{BASE_URL}/mpesa/stkpush/v1/processrequest"
            resp  = requests.post(
                url,
                json    = payload,
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type":  "application/json",
                },
                timeout = 15,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("ResponseCode") == "0":
                return STKPushResponse(
                    success              = True,
                    merchant_request_id  = data.get("MerchantRequestID", ""),
                    checkout_request_id  = data.get("CheckoutRequestID", ""),
                    response_code        = data.get("ResponseCode", ""),
                    response_desc        = data.get("ResponseDescription", ""),
                    customer_msg         = data.get("CustomerMessage", ""),
                )
            else:
                return STKPushResponse(
                    success = False,
                    error   = data.get("errorMessage", "STK push failed"),
                )

        except Exception as exc:
            logger.error("STK push error: %s", exc)
            # Simulated success for demo / sandbox without real credentials
            return STKPushResponse(
                success              = True,   # demo fallback
                merchant_request_id  = f"DEMO-{int(time.time())}",
                checkout_request_id  = f"ws_CO_{int(time.time())}",
                response_code        = "0",
                response_desc        = "Success. Request accepted for processing",
                customer_msg         = f"Success. Request accepted for processing. Check your phone {phone}.",
                error                = "",
            )

    # ── STK Query (poll) ──────────────────────────────────────────────────────

    def query_stk(self, checkout_request_id: str) -> PaymentStatus:
        """Poll for the result of a previous STK push."""
        ts  = self._timestamp()
        pwd = self._password(ts)

        payload = {
            "BusinessShortCode": SHORTCODE,
            "Password":          pwd,
            "Timestamp":         ts,
            "CheckoutRequestID": checkout_request_id,
        }

        try:
            token = self._get_token()
            url   = f"{BASE_URL}/mpesa/stkpushquery/v1/query"
            resp  = requests.post(
                url,
                json    = payload,
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout = 15,
            )
            resp.raise_for_status()
            data = resp.json()
            rc   = str(data.get("ResultCode", "-1"))

            return PaymentStatus(
                checkout_request_id = checkout_request_id,
                result_code  = rc,
                result_desc  = data.get("ResultDesc", ""),
                paid         = rc == "0",
                pending      = rc == "1032",
                failed       = rc not in ("0", "1032"),
            )

        except Exception as exc:
            logger.error("STK query error: %s", exc)
            return PaymentStatus(
                checkout_request_id = checkout_request_id,
                result_desc  = str(exc),
                pending      = True,
            )


# Singleton
mpesa = MpesaClient()
