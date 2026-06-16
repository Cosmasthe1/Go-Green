"""
verra_registry/submitter.py — Go Green
────────────────────────────────────────────────────────────────────────────
EmailSubmitter — sends the issuance package to registry@verra.org via SMTP.

The Verra Registry does not have a REST API for issuance requests.
All submissions are made by emailing registry@verra.org with:
  1. The signed cover letter
  2. The monitoring report (Word/PDF/Markdown)
  3. The GHG calculations spreadsheet
  4. Any additional supporting documents

This module also sends an internal CC to the Go Green team with a copy of
everything submitted, for records and tracking.

Env vars:
  SMTP_HOST          e.g. smtp.gmail.com
  SMTP_PORT          587 (TLS) or 465 (SSL)
  SMTP_USER          sending email address
  SMTP_PASSWORD      app password / OAuth token
  SMTP_FROM          "Go Green Registry <registry@gogreen.co.ke>"
  VERRA_REGISTRY_EMAIL  registry@verra.org  (default)
  GOGREEN_CC_EMAIL   internal CC address
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from .builder import MonitoringReport, VCS_PROJECT_ID, VCS_PROJECT_NAME, VCS_PROPONENT_EMAIL

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SMTP_HOST    = os.environ.get("SMTP_HOST",    "smtp.gmail.com")
SMTP_PORT    = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER    = os.environ.get("SMTP_USER",    "")
SMTP_PASS    = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM    = os.environ.get("SMTP_FROM",    f"Go Green Registry <{VCS_PROPONENT_EMAIL}>")
VERRA_EMAIL  = os.environ.get("VERRA_REGISTRY_EMAIL", "registry@verra.org")
GOGREEN_CC   = os.environ.get("GOGREEN_CC_EMAIL", VCS_PROPONENT_EMAIL)


@dataclass
class SubmissionResult:
    success:        bool
    reference:      str      # e.g. email Message-ID used for tracking
    recipient:      str
    error:          str = ""
    message_id:     str = ""


class EmailSubmitter:
    """
    Sends the issuance package to registry@verra.org.

    In production:
      1. Set all SMTP_* env vars
      2. Use a dedicated "registry@gogreen.co.ke" sending address
      3. The email thread Message-ID becomes the submission_ref stored
         in the IssuanceQueue for tracking follow-ups
    """

    def submit(self, report: MonitoringReport) -> SubmissionResult:
        if not SMTP_USER or not SMTP_PASS:
            logger.warning(
                "SMTP not configured — logging submission instead of sending. "
                "Set SMTP_HOST / SMTP_USER / SMTP_PASSWORD to enable email."
            )
            return self._log_submission(report)

        try:
            return self._send_email(report)
        except Exception as exc:
            logger.error("Email submission failed: %s", exc, exc_info=True)
            return SubmissionResult(
                success   = False,
                reference = "",
                recipient = VERRA_EMAIL,
                error     = str(exc),
            )

    def _send_email(self, report: MonitoringReport) -> SubmissionResult:
        msg = MIMEMultipart()
        msg["From"]    = SMTP_FROM
        msg["To"]      = VERRA_EMAIL
        msg["Cc"]      = GOGREEN_CC
        msg["Subject"] = (
            f"VCU Issuance Request — {VCS_PROJECT_NAME} "
            f"[{report.batch_id}] "
            f"Monitoring Period {report.period_start} to {report.period_end}"
        )

        body = f"""Dear Registry Administrator,

Please find attached our VCU issuance request for the Go Green EV Fleet project
in Kenya under the Verified Carbon Standard (VCS).

Project: {VCS_PROJECT_NAME}
VCS ID:  {VCS_PROJECT_ID or "PENDING REGISTRATION"}
Batch:   {report.batch_id}
Period:  {report.period_start} — {report.period_end}
VCUs Requested: {report.total_net_vcu:.6f} tCO₂e

The complete monitoring report, GHG calculations spreadsheet, and cover letter
are attached as a ZIP archive.

Please confirm receipt and advise on next steps for VVB assignment and
verification approval.

Best regards,
Go Green Limited
{VCS_PROPONENT_EMAIL}
"""
        msg.attach(MIMEText(body, "plain"))

        # Attach the ZIP package
        if report.zip_path.exists():
            with report.zip_path.open("rb") as f:
                part = MIMEBase("application", "zip")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={report.zip_path.name}",
            )
            msg.attach(part)

        # Also attach the cover letter separately for easy reading
        if report.letter_path.exists():
            with report.letter_path.open("rb") as f:
                part2 = MIMEBase("text", "plain")
                part2.set_payload(f.read())
            encoders.encode_base64(part2)
            part2.add_header(
                "Content-Disposition",
                f"attachment; filename={report.letter_path.name}",
            )
            msg.attach(part2)

        recipients = [VERRA_EMAIL]
        if GOGREEN_CC and GOGREEN_CC != VERRA_EMAIL:
            recipients.append(GOGREEN_CC)

        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, recipients, msg.as_string())

        message_id = msg.get("Message-ID", report.batch_id)
        logger.info(
            "Issuance request emailed to %s (CC: %s) — Message-ID: %s",
            VERRA_EMAIL, GOGREEN_CC, message_id,
        )

        return SubmissionResult(
            success    = True,
            reference  = message_id or report.batch_id,
            recipient  = VERRA_EMAIL,
            message_id = message_id or "",
        )

    @staticmethod
    def _log_submission(report: MonitoringReport) -> SubmissionResult:
        """Dry-run: log what would be submitted without sending email."""
        ref = f"DRY-RUN-{report.batch_id}"
        logger.info(
            "DRY-RUN submission (SMTP not configured):\n"
            "  To:      %s\n"
            "  Subject: VCU Issuance Request — %s [%s]\n"
            "  Package: %s\n"
            "  VCUs:    %.6f tCO₂e\n"
            "  Period:  %s — %s\n"
            "  ACTION:  Set SMTP_HOST / SMTP_USER / SMTP_PASSWORD to enable sending.",
            VERRA_EMAIL,
            VCS_PROJECT_NAME, report.batch_id,
            report.zip_path,
            report.total_net_vcu,
            report.period_start, report.period_end,
        )
        return SubmissionResult(
            success   = True,
            reference = ref,
            recipient = VERRA_EMAIL,
            error     = "DRY-RUN: SMTP not configured",
        )
