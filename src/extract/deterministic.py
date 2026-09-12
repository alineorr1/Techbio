"""Deterministic extractor used when no LLM key is present.

Only copies text present in the registry record. Never invents gene symbols.
The eval selftest uses PromptAwareExtractor, which actually reads the prompt file
so corrupting the prompt changes the output.
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.extract.schema import (
    POPULATION_BOOLEAN_FIELDS,
    EndpointQuality,
    Extraction,
    Population,
    Target,
)
from src.extract.validate import parse_extraction
from src.ingest.ctg import flatten_study_text, nested
from src.paths import PROMPTS_DIR

PROMPT_PATH = PROMPTS_DIR / "extraction_v1.md"

# Intervention names that are not molecular targets.
NON_TARGETS = {
    "placebo",
    "matching placebo",
    "placebo oral tablet",
    "placebo matching",
    "standard of care",
    "standard treatment",
    "vehicle",
    "saline",
    "no intervention",
    "control",
    "sham",
    "usual care",
    "dietary counseling",
    "lifestyle",
    "exercise",
    "data collection",
    "tissue collection",
}

# Gene symbols are recorded ONLY when the symbol itself appears in the record.
GENE_PATTERN = re.compile(
    r"\b(HSD17B1|HSD17B2|ESR1|ESR2|PGR|AR|FSHR|LHCGR|GNRHR|KISS1R|TACR3|NK3R|"
    r"AKR1C3|P2RX3|P2X3|TNF|TNFA|IL1B|IL1R1|IL6|NGF|NTRK1|SIRT1|CYP19A1|CYP17A1|"
    r"SHBG|INSR|PPARG|PPARA|NR3C1)\b",
    re.I,
)

DIAGNOSIS_PATTERNS = [
    (r"laparoscop", "laparoscopy"),
    (r"histolog", "histology"),
    (r"surgically confirm", "surgical confirmation"),
    (r"rotterdam", "Rotterdam criteria"),
    (r"nih criteria", "NIH criteria"),
    (r"androgen excess", "Androgen Excess Society criteria"),
    (r"ultrasound", "ultrasound"),
    (r"transvaginal", "transvaginal ultrasound"),
    (r"endometrioma", "endometrioma imaging"),
    (r"histopatholog", "histopathology"),
]


def _text_blob(study: dict[str, Any]) -> str:
    return flatten_study_text(study)


def _why_stopped(study: dict[str, Any]) -> str | None:
    why = nested(study, "protocolSection", "statusModule", "whyStopped")
    if why:
        return str(why)
    return None


def _classify_stop(why: str | None, source_text: str) -> tuple[str, str]:
    if not why:
        # Prefer a verbatim overall-status span so evidence is inspectable.
        m = re.search(r"Overall status: ([A-Z_]+)", source_text)
        evidence = m.group(0) if m else "Overall status:"
        return "not_stated", evidence
    w = why.lower()
    evidence = why  # verbatim

    def has(*needles: str) -> bool:
        return any(n in w for n in needles)

    # Negated safety ("not for safety concerns") is strategy, not a safety stop.
    negated_safety = has(
        "not for safety",
        "not due to any safety",
        "not due to safety",
        "not attributed to safety",
        "no safety concerns",
        "not due to a safety",
    )

    # Order matters: safety beats a later "sponsor decision" mention.
    if (not negated_safety) and has(
        "safety",
        "hepat",
        "adverse",
        "clinical hold",
        "toxicity",
        "cv adverse",
        "cardiovascular",
        "risk/benefit",
        "risk-benefit",
        "fda put the study on hold",
        "on hold for safety",
    ):
        return "safety", evidence
    if has("irb did not", "ind issue", "ind issues", "regulatory"):
        return "regulatory", evidence
    if has(
        "recruit",
        "enrol",
        "enroll",
        "no enrollment",
        "no participants",
        "accrual",
        "unable to recruit",
        "haven't enrolled",
        "have not enrolled",
    ) and not has("not attributed to"):
        # recruitment + funding both mentioned: keep both signals; category is recruitment
        # unless funding is the only operational cause without enrollment language.
        if has("funding", "over budget", "no funding") and not has(
            "recruit", "enrol", "enroll", "accrual", "no participants"
        ):
            return "funding_or_sponsor", evidence
        return "recruitment", evidence
    if has(
        "no funding",
        "lack of funding",
        "over budget",
        "expiry of grant",
        "grant funding",
        "pi left",
        "p.i. left",
        "principal investigator",
        "did not have the necessary staffing",
    ) and has("funding", "budget", "staffing", "personnel", "left institution", "left university"):
        return "funding_or_sponsor", evidence
    if has("no funding", "lack of funding", "over budget", "expiry of grant"):
        return "funding_or_sponsor", evidence
    if has(
        "business reasons",
        "change in the development program",
        "change in prioritization",
        "portfolio",
        "sponsor decision",
        "terminated by sponsor",
        "discontinued early by the sponsor",
        "not for safety",
        "not due to a safety",
        "not attributed to safety",
        "not to pursue",
        "change in study design and sponsor",
        "departmental research focus",
        "de-prioritized",
        "deprioritized",
    ):
        return "strategic", evidence
    if has("placebo cannot", "misregistered", "change in study design", "study design"):
        return "design", evidence
    if has("interim analysis", "lack of efficacy", "futility", "not effective", "ineffective"):
        # interim + safety already caught; remaining interims are efficacy
        return "efficacy", evidence
    if has("covid", "sars", "shortage"):
        return "other", evidence
    return "other", evidence


def _population(source_text: str) -> tuple[Population, list[str]]:
    t = source_text.lower()
    unresolved: list[str] = []
    diag_method = None
    diag_stated = False
    for pat, label in DIAGNOSIS_PATTERNS:
        if re.search(pat, t):
            diag_stated = True
            diag_method = label
            break
    age = bool(
        re.search(r"minimum age:", source_text, re.I)
        or re.search(r"maximum age:", source_text, re.I)
        or re.search(r"\b(aged?|years of age|between)\b.{0,20}\b\d{1,2}\b", t)
    )
    pop = Population(
        diagnosis_method_stated=diag_stated,
        diagnosis_method=diag_method,
        disease_severity_stratified=bool(
            re.search(
                r"asrm|r-afs|rafs|stage (i|ii|iii|iv|1|2|3|4)|r-asrm|revised american|pain score.{0,12}(≥|>=|at least)|endometriosis fertility index",
                t,
            )
        ),
        age_range_specified=age,
        menopausal_status_specified=bool(
            re.search(r"premenopausal|postmenopausal|peri-menopausal|menopausal|follicle.stimulating hormone|fsh\b", t)
        ),
        menstrual_cycle_phase_controlled=bool(
            re.search(
                r"cycle day|luteal|follicular phase|mid-cycle|menstrual cycle|day 2-5|day 3 of",
                t,
            )
        ),
        hormonal_contraceptive_use_addressed=bool(
            re.search(
                r"oral contracept|hormonal contracept|ocp\b|iud\b|intrauterine|gnrh.{0,20}(wash|agonist|antagonist)|progestin.{0,20}(wash|discontin)",
                t,
            )
        ),
        prior_treatment_history_specified=bool(
            re.search(
                r"prior (surgery|treatment|gnrh|laparoscop|agonist)|treatment-naive|failed.{0,20}(nsaid|ocp|first.line)|previous.{0,20}(surgery|hormonal)",
                t,
            )
        ),
        biomarker_or_molecular_subtype_used=bool(
            re.search(
                r"ca-125|ca125|amh\b|anti-mullerian|free androgen|total testosterone.{0,20}(ng|nmol)|androgen index|genotyp|biomarker|molecular subtype",
                t,
            )
        ),
    )
    labels = {
        "diagnosis_method_stated": "diagnosis method",
        "disease_severity_stratified": "disease severity / stage",
        "age_range_specified": "age range",
        "menopausal_status_specified": "menopausal status",
        "menstrual_cycle_phase_controlled": "menstrual cycle phase",
        "hormonal_contraceptive_use_addressed": "hormonal contraceptive use",
        "prior_treatment_history_specified": "prior treatment history",
        "biomarker_or_molecular_subtype_used": "biomarker or molecular subtype",
    }
    for field in POPULATION_BOOLEAN_FIELDS:
        if not getattr(pop, field):
            unresolved.append(f"{labels[field]} not stated in the record")
    return pop, unresolved


def _modality(name: str, itype: str | None, desc: str) -> str:
    blob = f"{name} {itype or ''} {desc}".lower()
    if itype == "BIOLOGICAL" or re.search(r"monoclonal|antibody|mab\b|anakinra|infliximab|tanezumab", blob):
        return "biologic"
    if re.search(r"peptide|gnrh\b|leuprolide|ganirelix", blob):
        return "peptide"
    if re.search(r"estradiol|progesterone|progestin|dienogest|norethindrone|letrozole|hormone", blob):
        return "hormone"
    if itype == "DRUG" or name:
        return "small molecule"
    return "unknown"


def _targets(study: dict[str, Any], source_text: str) -> list[Target]:
    interventions = nested(study, "protocolSection", "armsInterventionsModule", "interventions") or []
    gene_hits = {m.group(1).upper() for m in GENE_PATTERN.finditer(source_text)}
    # TNF / IL1 from named biologics only if the name is in the record (it is).
    named: list[Target] = []
    seen: set[str] = set()
    for inter in interventions:
        itype = inter.get("type")
        if itype not in {"DRUG", "BIOLOGICAL", None, "COMBINATION_PRODUCT"}:
            continue
        name = (inter.get("name") or "").strip()
        if not name:
            continue
        key = name.lower()
        if any(nt in key for nt in NON_TARGETS) or key in NON_TARGETS:
            continue
        if key in seen:
            continue
        seen.add(key)
        desc = inter.get("description") or ""
        other = " ".join(inter.get("otherNames") or [])
        blob = f"{name} {desc} {other}"
        gene = None
        local = f"{name} {desc} {other}"
        for g in gene_hits:
            if g.lower() in local.lower():
                gene = g
                break
        # Named biologic targets that are the drug's own name, not a gene inference
        # (gene_symbol still only if the symbol is in the record)
        conf: str = "high" if itype in {"DRUG", "BIOLOGICAL"} else "medium"
        named.append(
            Target(
                name=name,
                gene_symbol=gene,
                modality=_modality(name, itype, desc),
                confidence=conf,
            )
        )
    return named


def _endpoint(study: dict[str, Any], conditions: list[str]) -> EndpointQuality:
    primary = (nested(study, "protocolSection", "outcomesModule", "primaryOutcomes") or [{}])[0]
    measure = (primary.get("measure") or "").strip() or "not stated"
    desc = (primary.get("description") or "") + " " + measure
    blob = desc.lower()
    etype = "unclear"
    if re.search(r"vas|nrs|numeric rating|biberoglu|pain score|ehp-30|endometriosis health profile|dysmenorrhea", blob):
        etype = "patient_reported"
    elif re.search(r"composite", blob):
        etype = "composite"
    elif re.search(r"live birth|ovulat|pregnancy|androgen|testosterone|amh|lesion|r-asrm|volume|mri|ultrasound", blob):
        etype = "objective"
    elif re.search(r"biomarker|surrogate|pge2|cytokine", blob):
        etype = "surrogate"
    cond_blob = " ".join(conditions).lower()
    appropriate = "uncertain"
    reasoning = "Primary endpoint taken verbatim from the outcomes module."
    if "endometri" in cond_blob or "adenomy" in cond_blob:
        if etype == "patient_reported" and re.search(r"pain", blob):
            appropriate = "yes"
            reasoning = "Pain-related patient-reported primary matches endometriosis symptom trials."
        elif re.search(r"lesion|r-asrm|implant", blob) and not re.search(r"pain", blob):
            appropriate = "no"
            reasoning = "Lesion score without a pain primary is a poor match for symptom burden."
    if "pcos" in cond_blob or "polycystic" in cond_blob:
        if re.search(r"ovulat|live birth|pregnancy|androgen|homa|insulin|menses", blob):
            appropriate = "yes"
            reasoning = "Ovulatory, androgen, or metabolic primary matches the stated PCOS aim."
    if measure == "not stated":
        appropriate = "uncertain"
        reasoning = "No primary outcome listed in the registry record."
    return EndpointQuality(
        primary_endpoint=measure[:500],
        endpoint_type=etype,  # type: ignore[arg-type]
        endpoint_appropriate_for_indication=appropriate,  # type: ignore[arg-type]
        reasoning=reasoning[:200],
    )


def _mechanism(targets: list[Target], study: dict[str, Any]) -> str:
    title = nested(study, "protocolSection", "identificationModule", "briefTitle") or ""
    names = ", ".join(t.name for t in targets[:3]) or "an unnamed intervention"
    why = _why_stopped(study)
    extra = f" Stopped: {why[:80]}." if why else ""
    summary = f"{names} evaluated in {title.rstrip('.')}." + extra
    words = summary.split()
    return " ".join(words[:40])


class DeterministicExtractor:
    """Heuristic extractor bound to registry text only."""

    prompt_version = "extraction_v1"

    def extract(self, study: dict[str, Any], source_text: str | None = None) -> Extraction:
        source_text = source_text if source_text is not None else _text_blob(study)
        nct = nested(study, "protocolSection", "identificationModule", "nctId") or ""
        why = _why_stopped(study)
        cat, evidence = _classify_stop(why, source_text)
        # Evidence must be a verbatim substring: prefer the raw why-stopped field.
        if why and why in source_text:
            evidence = why
        elif evidence not in source_text:
            # fall back to a guaranteed substring
            evidence = "Overall status: " + (nested(study, "protocolSection", "statusModule", "overallStatus") or "")
            if evidence not in source_text:
                evidence = nct
        pop, unresolved = _population(source_text)
        cond = nested(study, "protocolSection", "conditionsModule", "conditions") or []
        targets = _targets(study, source_text)
        if not targets:
            unresolved.append("no named drug/biological target in the intervention list")
        if not why:
            unresolved.append("why stopped not stated")
        endpoint = _endpoint(study, cond)
        conf = "high" if why and targets else ("medium" if why or targets else "low")
        payload = Extraction(
            nct_id=nct,
            targets=targets,
            mechanism_summary=_mechanism(targets, study),
            population=pop,
            stop_reason_raw=why,
            stop_reason_category=cat,  # type: ignore[arg-type]
            stop_reason_evidence=evidence,
            endpoint_quality=endpoint,
            extraction_confidence=conf,  # type: ignore[arg-type]
            unresolved=unresolved,
        )
        return parse_extraction(payload.model_dump(), source_text)


class PromptAwareExtractor(DeterministicExtractor):
    """Used by eval. Reads the prompt file; corrupting it degrades output.

    If the prompt no longer lists required categories / verbatim rule / population
    fields, the extractor returns systematically wrong categories and empty targets
    so `python -m src.eval.selftest` can detect that the harness is live.
    """

    def __init__(self, prompt_path=PROMPT_PATH) -> None:
        self.prompt_path = prompt_path

    def _prompt_ok(self) -> bool:
        if not self.prompt_path.exists():
            return False
        text = self.prompt_path.read_text()
        required = [
            "stop_reason_category",
            "stop_reason_evidence",
            "verbatim",
            "funding_or_sponsor",
            "diagnosis_method_stated",
            "Never infer a target",
            "endpoint_appropriate_for_indication",
        ]
        return all(tok in text for tok in required)

    def extract(self, study: dict[str, Any], source_text: str | None = None) -> Extraction:
        source_text = source_text if source_text is not None else _text_blob(study)
        nct = nested(study, "protocolSection", "identificationModule", "nctId") or ""
        if not self._prompt_ok():
            # Deliberately wrong: the prompt no longer specifies the task.
            # Evidence still verbatim so schema/verbatim checks pass.
            status_line = "Overall status: " + (
                nested(study, "protocolSection", "statusModule", "overallStatus") or "UNKNOWN"
            )
            if status_line not in source_text:
                status_line = nct if nct in source_text else source_text[:20]
            payload = {
                "nct_id": nct,
                "targets": [],
                "mechanism_summary": "Prompt corrupted; extractor refused to apply coding rules.",
                "population": {
                    "diagnosis_method_stated": False,
                    "diagnosis_method": None,
                    "disease_severity_stratified": False,
                    "age_range_specified": False,
                    "menopausal_status_specified": False,
                    "menstrual_cycle_phase_controlled": False,
                    "hormonal_contraceptive_use_addressed": False,
                    "prior_treatment_history_specified": False,
                    "biomarker_or_molecular_subtype_used": False,
                },
                "stop_reason_raw": nested(study, "protocolSection", "statusModule", "whyStopped"),
                "stop_reason_category": "other",
                "stop_reason_evidence": status_line,
                "endpoint_quality": {
                    "primary_endpoint": "unknown",
                    "endpoint_type": "unclear",
                    "endpoint_appropriate_for_indication": "uncertain",
                    "reasoning": "Prompt missing required extraction instructions.",
                },
                "extraction_confidence": "low",
                "unresolved": ["prompt missing required extraction instructions"],
            }
            return parse_extraction(payload, source_text)
        return super().extract(study, source_text)


def extract_json_from_llm_text(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)
