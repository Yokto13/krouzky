from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from typing import Dict, Iterable, Optional
from urllib.request import urlopen


class XMLParser:
    def __init__(self):
        self.tree: Optional[ET.ElementTree] = None
        self.root: Optional[ET.Element] = None
        self.namespaces: Dict[str, str] = {}

    def _register_default_namespace(self, alias: str = "ps") -> None:
        if self.root is None:
            return
        tag = self.root.tag
        if tag.startswith("{"):
            uri, *_ = tag[1:].split("}")
            # register alias only if absent to allow manual overrides
            self.namespaces.setdefault(alias, uri)

    def _finalize_parse(self) -> ET.Element:
        if self.tree is None:
            raise ValueError("Parsing failed: no XML tree available")
        self.root = self.tree.getroot()
        self.namespaces = {}
        self._register_default_namespace()
        return self.root

    def parse_from_url(self, url: str):
        """Fetches XML content from a URL and parses it into an ElementTree."""
        with urlopen(url) as response:
            data = response.read()
        self.tree = ET.ElementTree(ET.fromstring(data))
        return self._finalize_parse()

    def parse_from_file(self, file_path: str):
        """Parses XML content from a local file."""
        self.tree = ET.parse(file_path)
        return self._finalize_parse()

    def parse_from_string(self, xml_data: str | bytes):
        """Parses XML content provided as a string or bytes."""
        if isinstance(xml_data, str):
            xml_data = xml_data.encode("utf-8")
        self.tree = ET.parse(io.BytesIO(xml_data))
        return self._finalize_parse()

    def find_elements(self, tag: str):
        """Finds all elements in the XML tree with the given tag."""
        if self.root is None:
            raise ValueError("XML not parsed. Call parse_from_url or parse_from_file first.")
        return self.root.findall(tag, self.namespaces or None)

    def find(self, xpath: str, namespaces: Optional[Dict[str, str]] = None):
        if self.root is None:
            raise ValueError("XML not parsed. Call parse_from_url or parse_from_file first.")
        merged = {**self.namespaces, **(namespaces or {})}
        return self.root.find(xpath, merged or None)

    def findall(self, xpath: str, namespaces: Optional[Dict[str, str]] = None) -> Iterable[ET.Element]:
        if self.root is None:
            raise ValueError("XML not parsed. Call parse_from_url or parse_from_file first.")
        merged = {**self.namespaces, **(namespaces or {})}
        return self.root.findall(xpath, merged or None)

    def get_element_text(self, element):
        """Retrieves the text from an XML element, if present."""
        return element.text if element is not None else None


class ElectionsParser:
    """High-level parser for Czech parliamentary election statistics."""

    RESULTS_URL = "https://www.volby.cz/pls/ps2021/vysledky"

    def __init__(self, parser: Optional[XMLParser] = None, url: str | None = None):
        self.parser = parser or XMLParser()
        self.url = url or self.RESULTS_URL
        self._root: Optional[ET.Element] = None

    # ------------------------------------------------------------------
    # Loading helpers
    # ------------------------------------------------------------------
    def load(self) -> ET.Element:
        self._root = self.parser.parse_from_url(self.url)
        return self._root

    def ensure_loaded(self) -> ET.Element:
        if self._root is None:
            return self.load()
        return self._root

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_region_results(self):
        """Return vote totals and representatives per region.

        Returns a dictionary keyed by region name. Each region provides:

        - ``region_code``: numeric code of the region
        - ``seats``: number of mandates available in the region
        - ``valid_votes``: total valid votes cast in the region
        - ``parties``: list of parties with their vote totals and representatives
        """

        root = self.ensure_loaded()
        ns = self.parser.namespaces
        region_data = {}

        for region in root.findall("ps:KRAJ", ns):
            region_name = region.attrib.get("NAZ_KRAJ")
            region_code = region.attrib.get("CIS_KRAJ")
            seats = self._to_int(region.attrib.get("POCMANDATU"))
            turnout = region.find("ps:UCAST", ns)
            valid_votes = self._to_int(turnout.attrib.get("PLATNE_HLASY")) if turnout is not None else None

            parties = []
            for party in region.findall("ps:STRANA", ns):
                party_entry = self._build_party_entry(party, ns)
                parties.append(party_entry)

            region_data[region_name] = {
                "region_code": region_code,
                "seats": seats,
                "valid_votes": valid_votes,
                "parties": parties,
            }

        return region_data

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_party_entry(self, party: ET.Element, ns: Dict[str, str]) -> Dict[str, object]:
        party_values = party.find("ps:HODNOTY_STRANA", ns)
        votes = self._to_int(party_values.attrib.get("HLASY")) if party_values is not None else None
        vote_share = self._to_float(party_values.attrib.get("PROC_HLASU")) if party_values is not None else None

        representatives = []
        for representative in party.findall("ps:POSLANEC", ns):
            representatives.append(self._build_representative_entry(representative))

        return {
            "party_id": party.attrib.get("KSTRANA"),
            "party_name": party.attrib.get("NAZ_STR"),
            "ballot_number": self._to_int(party.attrib.get("VSTRANA")),
            "votes": votes,
            "vote_share": vote_share,
            "representatives": representatives,
        }

    def _build_representative_entry(self, representative: ET.Element) -> Dict[str, object]:
        first_name = representative.attrib.get("JMENO", "").strip()
        last_name = representative.attrib.get("PRIJMENI", "").strip()
        title_before = representative.attrib.get("TITULPRED", "").strip()
        title_after = representative.attrib.get("TITULZA", "").strip()

        full_name_tokens = [token for token in (title_before, first_name, last_name, title_after) if token]
        full_name = " ".join(full_name_tokens)

        return {
            "region_code": representative.attrib.get("CIS_KRAJ"),
            "order": self._to_int(representative.attrib.get("PORADOVE_CISLO")),
            "first_name": first_name,
            "last_name": last_name,
            "title_before": title_before or None,
            "title_after": title_after or None,
            "full_name": full_name,
            "preference_votes": self._to_int(representative.attrib.get("PREDNOSTNI_HLASY")),
            "preference_share": self._to_float(representative.attrib.get("PREDNOSTNI_HLASY_PROC")),
        }

    @staticmethod
    def _to_int(value: Optional[str]) -> Optional[int]:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except ValueError:
            return int(float(value.replace(",", ".")))

    @staticmethod
    def _to_float(value: Optional[str]) -> Optional[float]:
        if value in (None, ""):
            return None
        value = value.replace(",", ".")
        try:
            return float(value)
        except ValueError:
            return None


class PreferenceVoteParser:
    """Parser for preferential votes per candidate and party."""

    PREFERENCE_VOTES_URL = "https://www.volby.cz/pls/ps2021/vysledky_kandid"

    def __init__(self, parser: Optional[XMLParser] = None, url: str | None = None):
        self.parser = parser or XMLParser()
        self.url = url or self.PREFERENCE_VOTES_URL
        self._root: Optional[ET.Element] = None

    # ------------------------------------------------------------------
    # Loading helpers
    # ------------------------------------------------------------------
    def load(self) -> ET.Element:
        self._root = self.parser.parse_from_url(self.url)
        return self._root

    def ensure_loaded(self) -> ET.Element:
        if self._root is None:
            return self.load()
        return self._root

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_preference_votes(self) -> Dict[str, Dict[int, Dict[str, object]]]:
        """Return preference vote stats grouped by region and party.

        Structure of the returned dictionary:

        ``{
            region_name: {
                party_number: {
                    "total_preference_votes": int | None,
                    "candidates": [
                        {"candidate_number": int | None, "preference_votes": int | None},
                        ...
                    ]
                }
            }
        }``
        """

        root = self.ensure_loaded()
        ns = self.parser.namespaces
        preference_data: Dict[str, Dict[int, Dict[str, object]]] = {}

        for region in root.findall("ps:KRAJ", ns):
            region_name = region.attrib.get("NAZ_KRAJ")
            if not region_name:
                continue

            parties: Dict[int, Dict[str, object]] = {}

            # Prepare party containers from the STRANY section (contains totals per party)
            parties_section = region.find("ps:STRANY", ns)
            if parties_section is not None:
                for party in parties_section.findall("ps:STRANA", ns):
                    party_id = self._to_int(party.attrib.get("KSTRANA"))
                    if party_id is None:
                        continue
                    parties[party_id] = {
                        "total_preference_votes": self._to_int(party.attrib.get("POC_HLASU")),
                        "candidates": [],
                    }

            # party section
            party_to_total_votes = {}
            parties_section = region.find("ps:STRANY", ns)
            if parties_section is not None:
                for party in parties_section.findall("ps:STRANA", ns):
                    party_id = self._to_int(party.attrib.get("KSTRANA"))
                    number_of_votes = self._to_int(party.attrib.get("POC_HLASU"))
                    if party_id is not None and number_of_votes is not None:
                        party_to_total_votes[party_id] = number_of_votes

            # Attach candidate-level data
            candidates_section = region.find("ps:KANDIDATI", ns)
            if candidates_section is not None:
                for candidate in candidates_section.findall("ps:KANDIDAT", ns):
                    party_id = self._to_int(candidate.attrib.get("KSTRANA"))
                    if party_id is None:
                        continue
                    party_entry = parties.setdefault(
                        party_id,
                        {"total_preference_votes": None, "candidates": []},
                    )
                    party_entry["candidates"].append(
                        {
                            "candidate_number": self._to_int(candidate.attrib.get("PORCISLO")),
                            "preference_votes": self._to_int(candidate.attrib.get("HLASY")),
                            "preference_share": self._to_int(candidate.attrib.get("HLASY")) / party_to_total_votes.get(party_id, 1) * 100 if party_to_total_votes.get(party_id, 0) > 0 else None,
                        }
                    )

            # Sort candidate lists by candidate number for deterministic output
            for party_entry in parties.values():
                party_entry["candidates"].sort(
                    key=lambda item: (item["candidate_number"] is None, item["candidate_number"])
                )

            preference_data[region_name] = parties

        return preference_data

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _to_int(value: Optional[str]) -> Optional[int]:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except ValueError:
            value = value.replace(",", ".")
            try:
                return int(float(value))
            except ValueError:
                return None
