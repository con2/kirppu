# -*- coding: utf-8 -*-
import contextlib
import typing

from xml.dom.minidom import getDOMImplementation, Element

from django.conf import settings
from django.utils import timezone


class Pain:
    def __init__(self, pain_version: int = 9) -> None:
        self.impl = getDOMImplementation()
        self.ns = f"urn:iso:std:iso:20022:tech:xsd:pain.001.001.{pain_version:02d}"
        self.doc = self.impl.createDocument(self.ns, f"Document", None)
        self.root: Element = typing.cast(Element, self.doc.documentElement)
        self.root.setAttribute("xmlns", self.ns)
        self.root.setAttribute("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
        self.root.setAttribute(
            "xsi:schemaLocation", f"{self.ns} pain.001.001.{pain_version:02d}.xsd"
        )

        self.cstmr = self.doc.createElement("CstmrCdtTrfInitn")
        self.root.appendChild(self.cstmr)

        self.grphdr = self.doc.createElement("GrpHdr")
        self.cstmr.appendChild(self.grphdr)

        self.pmtinf = self.doc.createElement("PmtInf")
        self.cstmr.appendChild(self.pmtinf)
        self._trf_count = 0

    def _append_text(self, element: Element, name: str, text: str) -> Element:
        el = self.doc.createElement(name)
        if text:
            el.appendChild(self.doc.createTextNode(text))
        element.appendChild(el)
        return el

    @staticmethod
    def _find_child(element: Element, name: str) -> Element:
        for child in element.childNodes:
            if child.nodeType == child.ELEMENT_NODE and child.nodeName == name:
                return typing.cast(Element, child)
        assert False, "No child node found"

    @contextlib.contextmanager
    def _element(self, parent: Element, name: str):
        element = self.doc.createElement(name)
        parent.appendChild(element)
        yield element

    def group_header(
        self,
        msg_id: str,
        initiating_party: str,
        pmt_id: str,
        exc_date: str,
        cre_date: str | None,
    ) -> typing.Self:
        # GrpHdr
        self._append_text(self.grphdr, "MsgId", msg_id)
        self._append_text(
            self.grphdr, "CreDtTm", cre_date or timezone.now().isoformat()
        )
        self._append_text(self.grphdr, "NbOfTxs", "")  # filled in .finish()
        with self._element(self.grphdr, "InitgPty") as init:
            self._append_text(init, "Nm", initiating_party)

        # PmtInf
        self._append_text(self.pmtinf, "PmtInfId", pmt_id)
        self._append_text(self.pmtinf, "PmtMtd", "TRF")
        with self._element(self.pmtinf, "ReqdExctnDt") as exc:
            self._append_text(exc, "Dt", exc_date)

        return self

    def debtor(self, org_name: str, org_id: str, iban: str, bic: str) -> typing.Self:
        with self._element(self.pmtinf, "Dbtr") as dbtr:
            self._append_text(dbtr, "Nm", org_name)
            with self._element(dbtr, "Id") as dbtr_id:
                with self._element(dbtr_id, "OrgId") as dbtr_org:
                    with self._element(dbtr_org, "Othr") as dbtr_othr:
                        self._append_text(dbtr_othr, "Id", org_id)
                        with self._element(dbtr_othr, "SchmeNm") as dbtr_schm:
                            self._append_text(dbtr_schm, "Cd", "BANK")

        with self._element(self.pmtinf, "DbtrAcct") as dbtr_acct:
            with self._element(dbtr_acct, "Id") as dbtr_acct_id:
                self._append_text(dbtr_acct_id, "IBAN", iban)

        with self._element(self.pmtinf, "DbtrAgt") as dbtr_agt:
            with self._element(dbtr_agt, "FinInstnId") as dbtr_fin:
                self._append_text(dbtr_fin, "BICFI", bic)

        return self

    def transfer_to(
        self, e2e_id: str, name: str, iban: str, msg: str, amount: str
    ) -> typing.Self:
        with self._element(self.pmtinf, "CdtTrfTxInf") as trf:
            with self._element(trf, "PmtId") as pmt_id:
                self._append_text(pmt_id, "EndToEndId", e2e_id)

            with self._element(trf, "Amt") as pmt_amt:
                amt = self._append_text(pmt_amt, "InstdAmt", amount)
                amt.setAttribute("Ccy", "EUR")  # TODO

            with self._element(trf, "Cdtr") as pmt_cdtr:
                self._append_text(pmt_cdtr, "Nm", name)

            with self._element(trf, "CdtrAcct") as pmt_cdtr_acct:
                with self._element(pmt_cdtr_acct, "Id") as pmt_cdtr_acct_id:
                    self._append_text(pmt_cdtr_acct_id, "IBAN", iban)

            with self._element(trf, "RmtInf") as pmt_rmt:
                self._append_text(pmt_rmt, "Ustrd", msg)

        self._trf_count += 1

        return self

    def finish(self) -> typing.Self:
        self._find_child(self.grphdr, "NbOfTxs").appendChild(
            self.doc.createTextNode(str(self._trf_count))
        )
        return self


def main():
    settings.configure(TIME_ZONE="Europe/Helsinki")
    print(
        Pain(13)
        .group_header("TestiMsg", "Tapahtuma ry", "TestPay", str(timezone.now().date()))
        .debtor("Tapahtuma ry", "12345678", "FI1260415379240366", "AABAFI22")
        .transfer_to(
            id_="Testi1",
            name="Ahto Simakuutio",
            iban="DE89370400440532013000",
            msg="Testi",
            amount="1.04",
        )
        .finish()
        .doc.toprettyxml(indent="  ", encoding="UTF-8")
        .decode()
    )


if __name__ == "__main__":
    main()
