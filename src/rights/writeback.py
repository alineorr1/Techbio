"""Asset IP public-only desk writeback → wave-1b.rights-stub.v1.

Maps locked desk classifications into RightsRecord and persists with
``write_rights``. Empty/unfilled ownability stays NOT OPTIONABLE.
process.outreach is always ``none``. Unpaid / no outreach.

CONTINGENT requires ≥1 citable indication-specific patent/application
number (see ``apply_contingent_patent_bar``). This writeback set is
WALK_AWAY throughout (CONTINGENT count = 0), including Viramal and BOL.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from src.db import dump_json, load_json
from src.identity.programme import identifiers_from_nct, programme_id_for
from src.ingest.ctg import nested
from src.paths import RAW_CTG_DIR, RIGHTS_DIR, ROOT
from src.rights.codes import DESK_WRITEBACK_NCTS, HARD_KILL_CODES, SOFT_CODES
from src.rights.gates import (
    NOT_OPTIONABLE,
    NOT_OPTIONABLE_CODE,
    apply_contingent_patent_bar,
    evaluate_pre_pass,
)
from src.rights.query import ownability_query
from src.rights.schema import RightsRecord, cmc_of, pathway_505b2_of, utc_now
from src.rights.store import load_rights, write_rights

DASHBOARD_SNAPSHOT = ROOT / "dashboard" / "public" / "data" / "snapshot.json"
UPDATED_AT = "2026-09-13"
UPDATED_BY = "asset_ip"

# Snapshot programme_id pins (preserve empty-stub clustering). Eliapixant is
# indication=other and is absent from the FP-hygiene snapshot.
PROGRAMME_ID_PIN: dict[str, str] = {
    "NCT02669238": "p_86d51305873ced31",
    "NCT04554693": "p_4f175b745b09831b",
    "NCT05670353": "p_8251ee95e6d5c271",
    "NCT04372121": "p_d79ac79555e6767e",
    "NCT03380091": "p_9b9d0521f3a2de83",
    "NCT03970330": "p_ee21f2560ee9bf49",
    "NCT00703092": "p_4b51934768117dac",
    "NCT01631981": "p_f96ea52e2156b09a",
    "NCT03352076": "p_07cf8f66f987a83d",
    "NCT05370521": "p_2097f825e66b7d95",
    "NCT03201601": "p_86fb871363bb8bc7",
    "NCT03340324": "p_61dc5cf4e385ce0b",
    "NCT00212277": "p_15991eb9e4abb629",
    "NCT00865488": "p_54de2c96e80b1f46",
    "NCT00758953": "p_148055a0d7f4e9e1",
    "NCT03481842": "p_4f900da37005a857",
    "NCT04174911": "p_1d6546b07307da4e",
}


def _conf(raw: str | None) -> str:
    token = (raw or "high").strip().lower()
    return {"high": "high", "med": "medium", "medium": "medium", "low": "low"}.get(token, "high")


def _jurisdiction(number: str | None) -> str | None:
    if not number:
        return None
    compact = number.upper().replace(" ", "").replace("/", "")
    for prefix in ("WO", "US", "EP", "AU", "CN", "JP", "CA", "KR"):
        if compact.startswith(prefix):
            return prefix
    return None


def _families(patents: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in patents or []:
        number = item.get("number")
        title = item.get("title") or item.get("focus")
        if item.get("adjacent"):
            title = f"adjacent {title or ''}".strip()
        out.append(
            {
                "family_id": None,
                "jurisdiction": _jurisdiction(number),
                "publication_numbers": [number] if number else [],
                "status": item.get("status") or "unknown",
                "title": title,
            }
        )
    return out


def resolve_programme_id(nct_id: str, root: Path | None = None) -> str:
    existing = load_rights(nct_id=nct_id, root=root)
    if existing and existing.get("programme_id"):
        return str(existing["programme_id"])
    if nct_id in PROGRAMME_ID_PIN:
        return PROGRAMME_ID_PIN[nct_id]
    return programme_id_for(identifiers_from_nct(nct_id))


def desk_fills() -> list[dict[str, Any]]:
    """Authoritative Asset IP / CoS public-only closes. All WALK_AWAY."""
    return [
        {
            "nct_id": "NCT02669238",
            "classification": "WALK_AWAY",
            "confidence": "high",
            "title": "Evaluation of a Subcutaneous Progestogen Implants in the Medical Management of Painful Endometriosis",
            "asset_name": "Nexplanon (etonogestrel)",
            "sponsor": "Centre Hospitalier Universitaire de la Réunion",
            "sponsor_type": "academic",
            "who_can_grant": "CHU Réunion / French public hospital TT (if any); product rights = Organon (Nexplanon)",
            "indication": "Endometriosis",
            "modality": "device",
            "hard": ["K_COM_ELSEWHERE", "K_VALUE_NOT_CAPTURED"],
            "soft": [],
            "patents": [],
            "public_patent_null": True,
            "patents_note": "None found for CHU/END-IMPACT. Third-party Organon Nexplanon list patents.",
            "next_diligence": "None — closed",
            "cmc_note": "Commercial Organon implant CMC; no CHU package",
            "angle_505b2": "weak/none — off-label marketed implant",
        },
        {
            "nct_id": "NCT04554693",
            "classification": "WALK_AWAY",
            "confidence": "high",
            "title": "The Use of Low Dose Metronidazole to Decrease Postoperative Pain After Endometriosis Surgery",
            "asset_name": "Metronidazole",
            "sponsor": "University of Louisville",
            "sponsor_type": "academic",
            "who_can_grant": "University of Louisville TT; PI Resad Pasic",
            "indication": "Endometriosis",
            "modality": "small_molecule",
            "hard": ["K_COM_ELSEWHERE", "K_VALUE_NOT_CAPTURED"],
            "soft": [],
            "patents": [],
            "public_patent_null": True,
            "patents_note": "None found. Generic metronidazole; no Louisville/Pasic endometriosis MOU patents.",
            "next_diligence": "None — closed",
            "cmc_note": "Generic oral solid; no novel CMC",
            "generic": True,
        },
        {
            "nct_id": "NCT05670353",
            "classification": "WALK_AWAY",
            "confidence": "high",
            "title": "Cannabidiol for the Treatment of Pelvic Pain in Endometriosis (DREAMLAND)",
            "asset_name": "CBD extract",
            "sponsor": "University of Sao Paulo",
            "sponsor_type": "academic",
            "who_can_grant": "USP TT; PI Omero Benedicto Poli Neto",
            "indication": "Endometriosis",
            "modality": "other",
            "hard": ["K_FAILED_PIVOTAL", "K_VALUE_NOT_CAPTURED", "K_REG_CAPTURE_DESTROY"],
            "soft": [],
            "patents": [],
            "public_patent_null": True,
            "patents_note": "None found mapped to USP/DREAMLAND.",
            "next_diligence": "None — closed",
            "cmc_note": "Botanical CBD extract; cannabis CMC/regulatory opaque",
        },
        {
            "nct_id": "NCT04641273",
            "classification": "WALK_AWAY",
            "confidence": "high",
            "title": "BAY1817080 / eliapixant diabetic neuropathic pain",
            "asset_name": "eliapixant / BAY1817080",
            "sponsor": "Bayer",
            "legal_name": "Bayer AG",
            "sponsor_type": "industry",
            "who_can_grant": "Evotec SE (regained all P2X3 assets after Bayer discontinuation)",
            "indication": "other",
            "modality": "small_molecule",
            "hard": ["K_FAILED_PIVOTAL", "K_THESIS_MISMATCH"],
            "soft": [],
            "thesis_mismatch": True,
            "thesis_reason": "Failed PoC neuropathic pain; salvage blocked across indications.",
            "patents": [
                {"number": "WO2016/091776", "focus": "com"},
                {"number": "WO2019/219674", "focus": "mou"},
                {"number": "WO2019/219672", "focus": "mou"},
                {"number": "WO2022253945A1", "focus": "formulation"},
            ],
            "public_patent_null": False,
            "patents_note": "Product IP exists; program discontinued. Salvage blocked by failed PoC.",
            "next_diligence": "None — closed (public Evotec P2X3 map only; no outreach)",
        },
        {
            "nct_id": "NCT04372121",
            "classification": "WALK_AWAY",
            "confidence": "medium",
            "title": "Extension to Study on Efficacy and Safety of Linzagolix (EDELWEISS 5)",
            "asset_name": "linzagolix",
            "sponsor": "Kissei Pharmaceutical Co., Ltd.",
            "sponsor_type": "industry",
            "who_can_grant": "Kissei / Theramex (YSELTY EU) / Bio Genuine (China). US NDA withdrawn.",
            "indication": "Endometriosis",
            "modality": "small_molecule",
            "hard": ["K_VALUE_NOT_CAPTURED"],
            "soft": ["S_LICENSE_MAP_MISSING"],
            "patents": [
                {"number": "WO2007/046392", "focus": "com"},
                {"number": "WO2014/042176", "focus": "com"},
                {"number": "US9,169,266", "focus": "formulation", "title": "crystalline linzagolix choline"},
            ],
            "public_patent_null": False,
            "patents_note": (
                "COM/crystalline family verified. Multi-party Kissei/Theramex/Bio Genuine. "
                "US NDA withdrawn. Pharma Exec killed the linzagolix option thesis — not NEEDS_COUNSEL; "
                "no counsel-option workstream."
            ),
            "next_diligence": "None — closed",
            "cmc_note": "Oral SM; EU MAA CMC (YSELTY). US restart is not a clean 505(b)(2).",
        },
        {
            "nct_id": "NCT03380091",
            "classification": "WALK_AWAY",
            "confidence": "high",
            "title": "Metformin, Vitamin D, and Depression in PCOS (MINDD)",
            "asset_name": "Metformin + Vitamin D",
            "sponsor": "University of California, San Francisco",
            "sponsor_type": "academic",
            "who_can_grant": "UCSF TT",
            "indication": "Polycystic ovary syndrome",
            "modality": "small_molecule",
            "hard": ["K_COM_ELSEWHERE", "K_VALUE_NOT_CAPTURED"],
            "soft": [],
            "patents": [],
            "public_patent_null": True,
            "patents_note": "None found. Generic metformin + vitamin D.",
            "next_diligence": "None — closed",
            "generic": True,
        },
        {
            "nct_id": "NCT03970330",
            "classification": "WALK_AWAY",
            "confidence": "high",
            "title": "Low-Dose Naltrexone in Combination With Standard Treatment in Women With Endometriosis",
            "asset_name": "Naltrexone 4.5 mg LDN",
            "sponsor": "Milton S. Hershey Medical Center",
            "sponsor_type": "academic",
            "who_can_grant": "Penn State / Hershey TT; PI Kristin Riley",
            "indication": "Endometriosis",
            "modality": "small_molecule",
            "hard": ["K_COM_ELSEWHERE", "K_VALUE_NOT_CAPTURED"],
            "soft": [],
            "patents": [],
            "public_patent_null": True,
            "patents_note": "None found. Generic naltrexone; no Hershey exclusive endometriosis MOU patent.",
            "next_diligence": "None — closed",
            "generic": True,
        },
        {
            "nct_id": "NCT00703092",
            "classification": "WALK_AWAY",
            "confidence": "high",
            "title": "Pilot Study: Role of Dietary Fiber in PCOS Anovulation",
            "asset_name": "Fiber-Stat liquid fiber supplement",
            "sponsor": "Virginia Commonwealth University",
            "sponsor_type": "academic",
            "who_can_grant": "VCU TT; collaborator NICHD",
            "indication": "Polycystic ovary syndrome",
            "modality": "other",
            "hard": ["K_VALUE_NOT_CAPTURED", "K_COM_ELSEWHERE"],
            "soft": [],
            "patents": [],
            "public_patent_null": True,
            "patents_note": "None found for VCU/PCOS. Adjacent US8178150 not VCU-mapped exclusive.",
            "next_diligence": "None — closed",
            "cmc_note": "Consumer supplement manufacturing; not pharma CMC",
        },
        {
            "nct_id": "NCT01631981",
            "classification": "WALK_AWAY",
            "confidence": "high",
            "title": "PGL2001 Proof of Concept Study in Symptomatic Endometriosis",
            "asset_name": "PGL2001 / PregLem",
            "sponsor": "PregLem SA",
            "sponsor_type": "industry",
            "who_can_grant": "PregLem / Gedeon Richter successor path unclear — abandoned application",
            "indication": "Endometriosis",
            "modality": "small_molecule",
            "hard": ["K_COM_ELSEWHERE", "K_VALUE_NOT_CAPTURED"],
            "soft": [],
            "patents": [{"number": "US20150065470A1", "focus": "com", "status": "unknown", "title": "Abandoned"}],
            "public_patent_null": False,
            "patents_note": "US20150065470A1 Abandoned. PregLem PGL2001 — value not captured.",
            "next_diligence": "None — closed",
        },
        {
            "nct_id": "NCT03352076",
            "classification": "WALK_AWAY",
            "confidence": "medium",
            "title": "Study to Determine Intraperitoneal, Tissue, Serum Concentrations of VML-0501",
            "asset_name": "VML-0501",
            "sponsor": "Viramal Limited",
            "sponsor_type": "industry",
            "who_can_grant": "Viramal — no citable public patent number after Asset IP pass",
            "indication": "Endometriosis",
            "modality": "small_molecule",
            "hard": ["K_COM_ELSEWHERE", "K_NO_IP_EMPTY_DOCKET"],
            "soft": ["S_PRIVATE_IP_ONLY"],
            "patents": [],
            "public_patent_null": True,
            "patents_note": (
                "Public patent-number pass null. S_PRIVATE_IP_ONLY hardened under Pharma Exec "
                "CONTINGENT-requires-citable-number bar + K_COM_ELSEWHERE (API). Not CONTINGENT."
            ),
            "next_diligence": "None — closed (public-only watchlist note only)",
        },
        {
            "nct_id": "NCT05370521",
            "classification": "WALK_AWAY",
            "confidence": "high",
            "title": "A Study of Safety and Efficacy of Tildacerfont in Females With PCOS",
            "asset_name": "tildacerfont",
            "sponsor": "Spruce Biosciences",
            "sponsor_type": "industry",
            "who_can_grant": "Spruce / Lilly CRF1 path — failed pivotal value not captured",
            "indication": "Polycystic ovary syndrome",
            "modality": "small_molecule",
            "hard": ["K_FAILED_PIVOTAL", "K_VALUE_NOT_CAPTURED"],
            "soft": [],
            "patents": [
                {"number": "WO2008036579", "focus": "com"},
                {"number": "US11708372", "focus": "com"},
            ],
            "public_patent_null": False,
            "patents_note": "Spruce/Lilly tildacerfont families; program value not captured after failed pivotal.",
            "next_diligence": "None — closed",
        },
        {
            "nct_id": "NCT03201601",
            "classification": "WALK_AWAY",
            "confidence": "high",
            "title": "Evaluation of the Mixture Myoinositol:D-chiro-inositol 3.6:1 in Women With PCOS",
            "asset_name": "Caronositol",
            "sponsor": "Biosearch S.A.",
            "sponsor_type": "industry",
            "who_can_grant": "Biosearch — marketed Caronositol; value not captured for option",
            "indication": "Polycystic ovary syndrome",
            "modality": "other",
            "hard": ["K_COM_ELSEWHERE", "K_VALUE_NOT_CAPTURED"],
            "soft": [],
            "patents": [
                {"number": "WO2019101368A1", "focus": "com"},
                {"number": "US11484540B2", "focus": "com"},
            ],
            "public_patent_null": False,
            "patents_note": "Marketed Caronositol. Commercial elsewhere.",
            "next_diligence": "None — closed",
        },
        {
            "nct_id": "NCT03340324",
            "classification": "WALK_AWAY",
            "confidence": "high",
            "title": "Open Label Immunotherapy of Endometriosis",
            "asset_name": "Immunitor immunotherapy",
            "sponsor": "Immunitor LLC",
            "sponsor_type": "industry",
            "who_can_grant": "Immunitor LLC — empty docket / regulatory capture destroy",
            "indication": "Endometriosis",
            "modality": "other",
            "hard": ["K_REG_CAPTURE_DESTROY", "K_NO_IP_EMPTY_DOCKET", "K_VALUE_NOT_CAPTURED"],
            "soft": [],
            "patents": [],
            "public_patent_null": True,
            "patents_note": "No public Immunitor endometriosis docket.",
            "next_diligence": "None — closed",
        },
        {
            "nct_id": "NCT00212277",
            "classification": "WALK_AWAY",
            "confidence": "high",
            "title": "Efficacy and Safety, Long-term Study of Low-dose Oral Contraceptive Pill",
            "asset_name": "Lunabell JP",
            "sponsor": "Nobelpharma",
            "sponsor_type": "industry",
            "who_can_grant": "Nobelpharma — marketed Lunabell JP; not ours",
            "indication": "Endometriosis",
            "modality": "small_molecule",
            "hard": ["K_COM_ELSEWHERE", "K_VALUE_NOT_CAPTURED"],
            "soft": [],
            "patents": [],
            "public_patent_null": True,
            "patents_note": "Marketed Lunabell JP. Commercial elsewhere.",
            "next_diligence": "None — closed",
        },
        {
            "nct_id": "NCT00865488",
            "classification": "WALK_AWAY",
            "confidence": "high",
            "title": "Evaluation of Adhexil Safety and Efficacy in Prevention and/or Reduction of Adhesions",
            "asset_name": "Adhexil",
            "sponsor": "OMRIX Biopharmaceuticals",
            "sponsor_type": "industry",
            "who_can_grant": "OMRIX / J&J — no reachable counterparty for Adhexil option",
            "indication": "Endometriosis",
            "modality": "other",
            "hard": ["K_VALUE_NOT_CAPTURED", "K_NO_COUNTERPARTY"],
            "soft": [],
            "patents": [],
            "public_patent_null": True,
            "patents_note": "OMRIX/J&J Adhexil — no public exclusive docket mapped to this NCT.",
            "next_diligence": "None — closed",
        },
        {
            "nct_id": "NCT00758953",
            "classification": "WALK_AWAY",
            "confidence": "high",
            "title": "Pain Associated With Endometriosis",
            "asset_name": "Lumara endometriosis program",
            "sponsor": "Lumara Health, Inc.",
            "sponsor_type": "industry",
            "who_can_grant": "Lumara gone — no counterparty",
            "indication": "Endometriosis",
            "modality": "small_molecule",
            "hard": ["K_NO_COUNTERPARTY", "K_COM_ELSEWHERE", "K_VALUE_NOT_CAPTURED"],
            "soft": [],
            "patents": [],
            "public_patent_null": True,
            "patents_note": "Lumara Health gone. No reachable grantor.",
            "next_diligence": "None — closed",
        },
        {
            "nct_id": "NCT03481842",
            "classification": "WALK_AWAY",
            "confidence": "high",
            "title": "Safety, Tolerability and Efficacy of Vaginal Suppositories for Treatment of the Endometriosis",
            "asset_name": "BioGene ELTA (axitinib/afatinib/linifanib combo)",
            "sponsor": "BioGene Pharmaceutical Ltd.",
            "sponsor_type": "industry",
            "who_can_grant": "Basel entity not found public; no counterparty",
            "indication": "Endometriosis",
            "modality": "small_molecule",
            "hard": ["K_NO_COUNTERPARTY", "K_NO_IP_EMPTY_DOCKET", "K_COM_ELSEWHERE", "K_VALUE_NOT_CAPTURED"],
            "soft": [],
            "patents": [],
            "public_patent_null": True,
            "patents_note": "Patents none found. API COM axitinib/afatinib/linifanib originators. N=0 withdrawn.",
            "next_diligence": "None — closed",
            "locked_prior": True,
        },
        {
            "nct_id": "NCT04174911",
            "classification": "WALK_AWAY",
            "confidence": "medium",
            "title": "A Study to Evaluate the Safety and Efficacy of BOL-DP-o-08 in Patients With Endometriosis Syndrome.",
            "asset_name": "BOL-DP-o-08",
            "sponsor": "Breath of Life International Pharma Ltd",
            "sponsor_type": "industry",
            "who_can_grant": "BOL — no endometriosis-specific patent; adjacent pMDI/Yissum only",
            "indication": "Endometriosis",
            "modality": "other",
            "hard": ["K_NO_IP_EMPTY_DOCKET", "K_VALUE_NOT_CAPTURED"],
            "soft": ["S_PRIVATE_IP_ONLY", "S_LICENSE_MAP_MISSING"],
            "patents": [
                {"number": "AU2024230822A1", "adjacent": True, "title": "pMDI BOL+Kindeva"},
                {"number": "WO2024182699", "adjacent": True, "title": "adjacent pMDI"},
                {"number": "WO2017072762", "adjacent": True, "title": "adjacent Yissum licensee only"},
            ],
            "public_patent_null": False,
            "adjacent_only": True,
            "patents_note": (
                "No endometriosis-specific patent/app number. Adjacent AU2024230822A1 / "
                "WO2024182699 / WO2017072762 (BOL+Kindeva pMDI / Yissum) do not satisfy the "
                "CONTINGENT citable-endo-number bar. Soft S_PRIVATE_IP_ONLY + S_LICENSE_MAP_MISSING "
                "hardened to WALK_AWAY. Do not reopen as PASS/CONTINGENT."
            ),
            "next_diligence": "None — closed",
            "locked_prior": True,
        },
    ]


def map_desk_to_rights(desk: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    nct = desk["nct_id"]
    classification = desk["classification"]
    confidence = _conf(desk.get("confidence"))
    pid = resolve_programme_id(nct, root=root)
    hard = [c for c in (desk.get("hard") or []) if c in HARD_KILL_CODES or str(c).startswith("K_")]
    soft = [c for c in (desk.get("soft") or []) if c in SOFT_CODES or str(c).startswith("S_")]
    triggered = bool(hard) if desk.get("triggered") is None else bool(desk.get("triggered"))
    if classification == "WALK_AWAY":
        triggered = True
        verdict = "FAIL"
        recommendation = "walk_away"
    else:
        verdict = "HOLD"
        recommendation = "contingent"
        triggered = bool(hard)
    families = _families(desk.get("patents"))
    docket_empty = bool(desk.get("public_patent_null")) or not families
    if desk.get("adjacent_only"):
        docket_empty = True
    thesis = bool(desk.get("thesis_mismatch") or "K_THESIS_MISMATCH" in hard)
    generic = bool(desk.get("generic"))
    holder = desk.get("legal_name") or desk.get("sponsor")
    note = (
        f"desk_classification={classification}. Asset IP public-only close. "
        f"{desk.get('patents_note') or ''} ownable=false. NOT OPTIONABLE. "
        f"next_diligence={desk.get('next_diligence') or 'None — closed'}."
    ).strip()
    record: dict[str, Any] = {
        "schema_version": "wave-1b.rights-stub.v1",
        "nct_id": nct,
        "programme_id": pid,
        "confidence": confidence,
        "desk_classification": classification,
        "shortlist_ownable": False,
        "optionable_candidate": False,
        "identity": {
            "nct_id": nct,
            "programme_id": pid,
            "eu_ct": None,
            "eudract": None,
            "asset_name": desk.get("asset_name"),
            "taxonomy": {
                "indication": desk.get("indication"),
                "target": None,
                "modality": desk.get("modality"),
                "empty": not any([desk.get("indication"), desk.get("modality")]),
            },
            "thesis_mismatch": thesis,
            "thesis_mismatch_reason": desk.get("thesis_reason"),
        },
        "counterparty": {
            "present": "K_NO_COUNTERPARTY" not in hard,
            "holder_name": holder,
            "holder_status": "unknown" if "K_NO_COUNTERPARTY" in hard else "resolved",
            "sponsor_entity": {
                "name": desk.get("sponsor"),
                "legal_name": desk.get("legal_name"),
                "resolution_status": "unknown" if "K_NO_COUNTERPARTY" in hard else "resolved",
                "jurisdiction": None,
                "opencorporates_id": None,
                "company_number": None,
                "source": "unstructured_registry",
            },
        },
        "ind_regulatory": {
            "ind_number": None,
            "ind_holder": None,
            "status": "unknown",
            "pathway": "unknown",
            "cmc": {
                "api_source_identified": "unknown",
                "formulation_described": "unknown",
                "impurity_profile_available": "unknown",
                "stability_data_available": "unknown",
                "manufacturing_site_known": "unknown",
                "spec_available": "unknown",
                "ctd_module_3_available": "unknown",
                "comparability_risk": "unknown",
                "notes": desk.get("cmc_note") or "",
                "confidence": confidence,
            },
            "pathway_505b2": {
                "pathway": "unknown",
                "rld_ref": None,
                "listed_drug_name": None,
                "listed_drug_ref": None,
                "exclusivity_windows": [],
                "orange_book_url": None,
                "orange_book_hook": "orange_book",
                "confidence": confidence,
            },
        },
        "ip": {
            "right_class": "unknown",
            "assignment": {"status": "gap" if docket_empty else "recorded", "assignee": holder, "chain_of_title": []},
            "patent_families": families,
            "orange_book": {
                "rld_ref": None,
                "listed_drug_ref": None,
                "exclusivity_windows": [],
                "url": None,
                "hook": "orange_book",
                "confidence": confidence,
            },
            "listed_drug_ref": None,
            "docket_empty": docket_empty,
        },
        "fto_lite": {
            "status": "unknown",
            "blocking_refs": [],
            "note": desk.get("patents_note") or "",
            "confidence": confidence,
        },
        "coi": {"status": "unclear", "flags": [], "note": "Public-only desk. No outreach."},
        "ownership": {
            "status": "resolved",
            "holder": holder,
            "ownable": False,
            "confidence": confidence,
            "recommendation": recommendation,
            "note": note,
        },
        "kill": {
            "triggered": triggered,
            "codes": list(dict.fromkeys([*hard, *soft])),
            "hard": hard,
            "soft": soft,
            "notes": desk.get("patents_note") or "",
        },
        "process": {
            "outreach": "none",
            "updated_by": UPDATED_BY,
            "updated_at": UPDATED_AT,
            "note": f"updated_by {UPDATED_BY} {UPDATED_AT}",
        },
        "commercial_shape": {
            "sex_dose_differentiation": None,
            "sex_diff_labeling": None,
            "generic_available": True if generic else None,
            "pricing_power": "none" if generic or classification == "WALK_AWAY" else "unknown",
        },
        "commercial_gate": {
            "verdict": verdict,
            "reason_codes": list(dict.fromkeys([*hard, *soft, NOT_OPTIONABLE_CODE])),
            "notes": f"desk_classification={classification}. Never PASS. Empty≠ownable. {desk.get('who_can_grant') or ''}",
        },
        "modules": {
            "asset_ip_desk": {
                "module": "asset_ip_desk",
                "status": "filled",
                "confidence": confidence,
                "desk_classification": classification,
                "updated_by": UPDATED_BY,
                "updated_at": UPDATED_AT,
                "blind_md": "LIVE",
                "next_diligence_step": desk.get("next_diligence") or "None — closed",
                "optionable_candidate": False,
                "public_patent_null": bool(desk.get("public_patent_null")),
                "adjacent_only": bool(desk.get("adjacent_only")),
                "provisional_contingent": False,
                "locked_prior": bool(desk.get("locked_prior")),
                "who_can_grant_rights": desk.get("who_can_grant"),
                "source": "asset_ip_public_only",
            }
        },
        "updated_at": utc_now(),
        "notes": note,
    }
    record = apply_contingent_patent_bar(record)
    validated = RightsRecord.model_validate(record).model_dump()
    return validated


def write_desk_fills(*, root: Path | None = None, nct_ids: list[str] | None = None) -> list[Path]:
    want = set(nct_ids) if nct_ids else set(DESK_WRITEBACK_NCTS)
    written: list[Path] = []
    for desk in desk_fills():
        if desk["nct_id"] not in want:
            continue
        record = map_desk_to_rights(desk, root=root)
        path = write_rights(record, root=root or RIGHTS_DIR)
        written.append(path)
        print(
            f"[rights.writeback] {desk['nct_id']} {record.get('desk_classification')} "
            f"ownable={record['ownership']['ownable']} outreach={record['process']['outreach']}"
        )
    return written


def _study_for(nct: str) -> dict[str, Any] | None:
    path = RAW_CTG_DIR / f"{nct}.json"
    if path.exists():
        return load_json(path)
    return None


def attach_rights_fields(asset: dict[str, Any], rights: dict[str, Any]) -> None:
    nct = asset["nct_id"]
    study = _study_for(nct)
    names = [i.get("name") for i in (asset.get("interventions") or []) if i.get("name")]
    ints = nested(study or {}, "protocolSection", "armsInterventionsModule", "interventions") or []
    for item in ints:
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
    pre = evaluate_pre_pass(study=study, rights=rights, intervention_names=names)
    own = ownability_query(rights)
    own["optionable"] = False
    own["shortlist_ownable"] = False
    own["surface"] = pre.get("surface") or rights.get("desk_classification") or NOT_OPTIONABLE
    own["md_status"] = "LIVE"
    own["desk_classification"] = rights.get("desk_classification")
    asset["rights"] = rights
    asset["ownability"] = own
    asset["pre_pass"] = pre
    asset["optionable"] = False
    asset["shortlist_ownable"] = False
    asset["gate_surface"] = own["surface"]
    asset["desk_classification"] = rights.get("desk_classification")
    asset["cmc"] = cmc_of(rights)
    asset["pathway_505b2"] = pathway_505b2_of(rights)
    enrich = asset.setdefault("enrichment", {})
    enrich["rights"] = {
        "schema_version": rights.get("schema_version"),
        "nct_id": nct,
        "programme_id": rights.get("programme_id") or asset.get("programme_id"),
        "confidence": rights.get("confidence"),
        "desk_classification": rights.get("desk_classification"),
        "path": f"data/derived/rights/{nct}.json",
    }
    asset.setdefault("sources", {})["rights_json"] = f"data/derived/rights/{nct}.json"


def patch_dashboard_snapshot(path: Path | None = None) -> dict[str, Any]:
    """Re-bind filled rights onto the unpaid corpus snapshot without a full re-extract."""
    dest = path or DASHBOARD_SNAPSHOT
    snap = load_json(dest)
    n_opt = 0
    n_contingent = 0
    n_walk = 0
    for asset in snap.get("assets") or []:
        nct = asset.get("nct_id")
        rec = load_rights(nct_id=nct)
        if rec and rec.get("desk_classification"):
            attach_rights_fields(asset, rec)
        if asset.get("optionable") or asset.get("shortlist_ownable"):
            n_opt += 1
        desk = asset.get("desk_classification") or (asset.get("rights") or {}).get("desk_classification")
        if desk == "CONTINGENT":
            n_contingent += 1
        if desk == "WALK_AWAY":
            n_walk += 1
    counts = snap.setdefault("counts", {})
    counts["n_optionable_candidate"] = n_opt
    counts["n_shortlist_ownable"] = sum(1 for a in snap.get("assets") or [] if a.get("shortlist_ownable"))
    counts["n_desk_walk_away"] = n_walk
    counts["n_desk_contingent"] = n_contingent
    counts["rights_writeback"] = "wave1b.asset_ip.public_only.v1"
    dump_json(dest, snap)
    print(
        f"[rights.writeback] snapshot n_assets={counts.get('n_assets')} "
        f"optionable={n_opt} walk_away={n_walk} contingent={n_contingent}"
    )
    return snap


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Write Asset IP public-only rights fills")
    parser.add_argument("--nct", action="append", dest="nct_ids")
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--patch-snapshot", action="store_true")
    args = parser.parse_args(argv)
    write_desk_fills(root=args.root, nct_ids=args.nct_ids)
    if args.patch_snapshot:
        patch_dashboard_snapshot()


if __name__ == "__main__":
    main()
