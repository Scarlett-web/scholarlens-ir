"""Deduplicate paper JSONL by the bytes of its source PDF, without changing inputs."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import date as calendar_date

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def source_pdf(record: dict, pdf_root: Path) -> Path:
    """Resolve a project-relative pdf_path and verify it identifies the source PDF."""
    relative = Path(record["pdf_path"])
    if relative.is_absolute():
        raise ValueError(f"absolute pdf_path: {record['source_file']}")
    pdf = (PROJECT_ROOT / relative).resolve()
    root = pdf_root.resolve()
    if not pdf.is_relative_to(root) or not pdf.is_file() or pdf.name != record["source_file"]:
        raise ValueError(f"source PDF cannot be verified: {record['source_file']}")
    return pdf


def file_hash(path: Path) -> str:
    """Return SHA-256 for a PDF, reading in bounded chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quality(record: dict) -> tuple[int, int, int, int, str]:
    """Rank duplicate records deterministically by usable metadata and body length."""
    fields = ("title", "authors", "date", "year", "affiliation", "address", "pages", "abstract", "fulltext")
    return (
        record.get("parse_status") != "error",
        sum(bool(record.get(field)) for field in fields),
        -len(record.get("errors", [])),
        len(record.get("fulltext", "")),
        record.get("source_file", ""),
    )


def pdf_page_count(path: Path) -> int:
    """Read the physical page count reported by pdfinfo; fail on ambiguous output."""
    result = subprocess.run(
        ["pdfinfo", str(path)], capture_output=True, text=True, errors="replace", check=True
    )
    match = re.search(r"^Pages:\s*(\d+)\s*$", result.stdout, re.MULTILINE)
    if match is None or int(match.group(1)) < 1:
        raise ValueError(f"no valid Pages value for {path.name}")
    return int(match.group(1))


def fill_pages(jsonl_path: Path, pdf_root: Path) -> None:
    """Update only pages in the existing JSONL, atomically after all PDFs succeed."""
    records = []
    counts = {}
    failures = []
    filled = 0
    with jsonl_path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            record = json.loads(line)
            if record["pages"] is None:
                pdf = source_pdf(record, pdf_root)
                if pdf not in counts:
                    try:
                        counts[pdf] = pdf_page_count(pdf)
                    except (subprocess.CalledProcessError, ValueError) as exc:
                        counts[pdf] = None
                        failures.append({"source_file": record["source_file"], "reason": type(exc).__name__})
                if counts[pdf] is not None:
                    record["pages"] = {"first": None, "last": None, "count": counts[pdf]}
                    record["errors"] = [error for error in record["errors"] if error != "missing: pages"]
                    if record["parse_status"] == "partial" and not record["errors"]:
                        record["parse_status"] = "success"
                    filled += 1
                elif "pdf_page_count_unreadable" not in record["errors"]:
                    record["errors"].append("pdf_page_count_unreadable")
            records.append(record)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=jsonl_path.parent, prefix="pages_", suffix=".tmp", delete=False) as output:
            temp_name = Path(output.name)
            for record in records:
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
        temp_name.replace(jsonl_path)
    finally:
        if temp_name is not None and temp_name.exists():
            temp_name.unlink()
    print(json.dumps({"records": len(records), "pages_filled": filled, "unreadable": failures, "output": str(jsonl_path)}, ensure_ascii=False))


def remove_source(jsonl_path: Path, source_file: str) -> None:
    """Remove exactly one matching source_file from an existing JSONL atomically."""
    records = [json.loads(line) for line in jsonl_path.open(encoding="utf-8")]
    kept = [record for record in records if record.get("source_file") != source_file]
    if len(records) - len(kept) != 1:
        raise ValueError(f"expected exactly one record for {source_file}; found {len(records) - len(kept)}")
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=jsonl_path.parent, prefix="remove_", suffix=".tmp", delete=False) as output:
            temp_name = Path(output.name)
            for record in kept:
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
        temp_name.replace(jsonl_path)
    finally:
        if temp_name is not None and temp_name.exists():
            temp_name.unlink()
    print(json.dumps({"removed_source_file": source_file, "remaining_records": len(kept)}, ensure_ascii=False))


def repair_verified_pdf_anomalies(jsonl_path: Path, pdf_root: Path) -> None:
    """Correct only values verified on source PDFs; preserve uncertain values as empty."""
    titles = {
        "ancerresaacrjournalsorgcgireprint60123218.pdf": "Cancer Gene Therapy by Thyroid Hormone-mediated Expression of Toxin Genes",
        "ancerresaacrjournalsorgcgireprint60133504.pdf": "A Direct Linkage between the Phosphoinositide 3-Kinase-AKT Signaling Pathway and the Mammalian Target of Rapamycin in Mitogen-stimulated and Transformed Cells",
        "ancerresaacrjournalsorgcgireprint652311146.pdf": "Antitumor Activity of Human Papillomavirus Type 16 E7-Specific T Cells against Virally Infected Squamous Cell Carcinoma of the Head and Neck",
        "ccpeecsumichedutheseskvmanthesis.pdf": "Streamroller: A Unified Compilation and Synthesis System for Streaming Applications",
        "krexkstateedudspacebitstream20971451NibeditaDas2006B.pdf": "Critical Analysis of Shyambazar Traffic Intersection Area, Kolkata: A Study of Visual Appropriateness",
        "m8pcipptgovplpapersnonlin.pdf": "Experimental and theoretical investigation of large-amplitude oscillations of liquid droplets",
        "ourseswashingtonedudevneuroweek3pdfsFlames04.pdf": "Short- and Long-Range Attraction of Cortical GABAergic Interneurons by Neuregulin-1",
        "publluthse14021757200652LTULIC0652SE.pdf": "Non-contact measurements and modelling of milling machine tool vibrations",
        "publluthse14021757200713LTULIC0713SE.pdf": "Lubrication of Conformal Contacts with Surface Texturing",
        "scholarspacemanoahawaiiedubitstream10125105491uhmms3935r.pdf": "Cultivation of the Oyster Mushroom (Pleurotus sp.) on Wood Substrates in Hawaii",
        "scholarspacemanoahawaiiedubitstream1012568792uhmphd4371r.pdf": "Studies on the Effects of Pharmacological Agents on Endotoxin Induced Pulmonary Injury",
        "tpcstorontoedupubericOImran20Kabir200820MISt20thesis.pdf": "Representation and Reorganization of Web Accessibility Guidelines Using Goal Graphs and Design Patterns",
        "wwcsbrowneduresearchpubsthesesmasters1992cheng.pdf": "Contribution to Incremental Constraint Algorithms",
        "wwcsbrowneduresearchpubsthesesmasters1993mackeith.pdf": "EREQ Query Representation and Cost Model",
        "wwepagovesdlandsciagwapdfusermanual.pdf": "Automated Geospatial Watershed Assessment (AGWA) - A GIS-Based Hydrologic Modeling Tool: Documentation and User Manual",
        "wwinfrastructuregovauroadssafetypublications1993pdfelderlyvisual.pdf": "Elderly Drivers and Visual Impairment",
        "wwmolbiolcellorgcgireprint182605.pdf": "Regulation of Myosin II Dynamics by Phosphorylation and Dephosphorylation of Its Light Chain in Epithelial Cells",
        "wwmolbiolcellorgcgireprint1841507.pdf": "The Myosin IXb Motor Activity Targets the Myosin IXb RhoGAP Domain as Cargo to Sites of Actin Polymerization",
        "wwmonashedumuarcreportsmuarc124.pdf": "The Cost of Injury to Victoria",
        "wwnhmkueduinvertspdfLSCnidariaproofsGRBQ1882777GCH10118188.pdf": "Cnidaria",
        "wwounlDocsOnderzoekPromoties2007ProefschriftDaantjeDerksdefinitieveversie.pdf": "Exploring the Missing Wink: Emoticons in Cyberspace",
        "wwpnlgovmainpublicationsexternaltechnicalreportsPNNL18293.pdf": "First Quarter Hanford Seismic Report for Fiscal Year 2009",
        "wwwituuseresearchpublicationslic20070042007004.pdf": "Tools and methods for evaluation of overlay networks",
        "rchivenumdamorgARCHIVEAIFAIF19524AIF1952410AIF1952410.pdf": "La variété de Picard d’une variété normale",
        "rchivenumdamorgARCHIVEAIFAIF1967172AIF19671723950AIF19671723950.pdf": "Recherches sur la topologie fine et ses applications : théorie du potentiel",
        "rchivenumdamorgARCHIVEAIFAIF1974243AIF19742432670AIF19742432670.pdf": "Classes caractéristiques exotiques et I-connexité des espaces de connexions",
        "rchivenumdamorgARCHIVEAIFAIF1985351AIF198535110AIF198535110.pdf": "D-modules et faisceaux pervers dont le support singulier est un croisement normal",
        "wwfourierujfgrenoblefrdemaillymanuscriptsAIF19853541890.pdf": "Champs magnétiques et inégalités de Morse pour la d″-cohomologie",
        "rchivenumdamorgARCHIVEAIFAIF1972222AIF19722222550AIF19722222550.pdf": "Prolongement analytique en dimension infinie",
        "wwtvacomenvironmentreportsgallatinfea.pdf": "Final Environmental Assessment: Gallatin Fossil Plant Rail Coal Unloading and Blending Facility",
        "wwcensusgovsippworkpaprwp1169011.pdf": "The Seam Effect in Panel Surveys",
        "ntljhcorgcgireprint426783.pdf": "Androgen receptor immunostaining and its tissue distribution in formalin-fixed, paraffin-embedded sections after microwave treatment",
        "wwepagovwaterstmdldocsswampcreekfecaltmdl.pdf": "Fecal Coliforms TMDL for Swamp Creek, WBID 427",
        "wwforschungsdatennetzwerkdepublikationenveroeffentlichungenfdzarbeitspapier26.pdf": "Union Density and Varieties of Coverage: The Anatomy of Union Wage Effects in Germany",
        "wwucalgarycaengowebdocsMT0520232Li2028Tony2920Sheng.pdf": "The Feasibility of Replacing Precise Levelling with GPS for Permafrost Deformation Monitoring",
        "ntlplantcellorgcgireprint15112503.pdf": "An Arabidopsis Callose Synthase, GSL5, Is Required for Wound and Papillary Callose Formation",
        "wwplantcellorgcgireprint15112503.pdf": "An Arabidopsis Callose Synthase, GSL5, Is Required for Wound and Papillary Callose Formation",
    }
    multi_article = {
        "inneapolisfedorgresearchQRQR3112.pdf",
        "wwclcstitechacjpalrWS5th5thALR.pdf",
        "wwitiantuagrhsjredbooks164hysj164010077.pdf",
    }
    plant_years = {
        "ntlplantcellorgcgireprint15112503.pdf": 2003,
        "ntlplantcellorgcgireprint15483.pdf": 1989,
        "ntlplantcellorgcgireprint17727.pdf": 1989,
        "ntlplantcellorgcgireprint2129.pdf": 1990,
        "ntlplantcellorgcgireprint3111239.pdf": 1991,
        "ntlplantcellorgcgireprint6121805.pdf": 1994,
        "ntlplantcellorgcgireprint7121975.pdf": 1995,
        "ntlplantcellorgcgireprint75549.pdf": 1995,
        "ntlplantcellorgcgireprint77809.pdf": 1995,
        "ntlplantcellorgcgireprint781235.pdf": 1995,
        "ntlplantcellorgcgireprint781295.pdf": 1995,
        "wwplantcellorgcgireprint15112503.pdf": 2003,
    }
    date_year = {
        "wwmineralogicalassociationcadevmacdoc697393juin0101.pdf": 2001,
        "wwsierraforestlegacyorgResourcesConservationSierraNevadaWildlifePacificFisherPFBoroski02.pdf": None,
        "wwcensusgovsippworkpaprwp1169011.pdf": 1990,
        "wwmatubesEMISjournalsHOADENM200749157.pdf": 2007,
        "wwcsbrowneduresearchpubsthesesmasters1993mackeith.pdf": 1993,
    }
    author_replacements = {
        "wwcsbrowneduresearchpubsthesesmasters1993mackeith.pdf": ["Andrew Clement Thornton MacKeith"],
        "ebmitedubiologysinskeywwwYork4217.pdf": ["Gregory M. York", "Björn H. Junker", "Joanne Stubbe", "Anthony J. Sinskey"],
        "wwplantphysiolorgcgireprint1051233.pdf": ["Lynn P. Cloney", "Diana R. Bekkaoui", "Gina L. Feist", "William S. Lane", "Sean M. Hemmingsen"],
        "wwplantphysiolorgcgireprint1073905.pdf": ["Sabine Fieuw", "Bernd Müller-Röber", "Susana Gálvez", "Lothar Willmitzer"],
        "wwplantphysiolorgcgireprint11431071.pdf": ["Eva Domínguez-Puigjaner", "Immaculada Llop", "Miquel Vendrell", "Salomé Prat"],
    }
    non_authors = {
        "wwmpiinfmpgdetheobaltbodylanguage.pdf": {"Stanford University"},
        "wwplantphysiolorgcgireprint1051233.pdf": {"Harvard Microchemistry Facility"},
        "wwplantphysiolorgcgireprint1073905.pdf": {"Physiologie Végétale Moléculaire"},
        "wwplantphysiolorgcgireprint11431071.pdf": {"Departamento De Agrobiología", "Departamento De Genética", "Centro De"},
        "wwmarineienrrdonlyresa0ad320cbc0e4af69cea7cddd5fd4f6f0nwherringacousticsurveyreport2008.pdf": {"June 19 -July"},
    }
    footer_patterns = [
        re.compile(r"by guest on\s*[A-Z][a-z]+ \d{1,2}, \d{4}\s+(?:https?://)?[\w.-]+(?:/[^\s]*)?\s+Downloaded from", re.I),
        re.compile(r"www\.plant\.org on [A-Z][a-z]+ \d{1,2}, \d{4} -Published by www\.plantphysiol\.org Downloaded from", re.I),
        re.compile(r"on [A-Z][a-z]+ \d{1,2}, \d{4}\s+(?:https?://)?www\.[\w.-]+(?:/[^\s]*)?\s+Downloaded from", re.I),
        re.compile(r"on [A-Z][a-z]+ \d{1,2}, \d{4}\.\s+©[^\n]{0,100}?cancerres\.aacrjournals\.org Downloaded from", re.I),
        re.compile(r"on [A-Z][a-z]+ \d{1,2}, \d{4} by guest https?://[\w.-]+/ Downloaded from", re.I),
        re.compile(r"https?://nar\.oxfordjournals\.org/ Downloaded from\s+by guest on\s*October 27, 2014", re.I),
        re.compile(r"\n\nDownloaded from(?=\n\nBritish Medical Bulletin)", re.I),
    ]
    reference_spans = {
        "wwepagovopptintraeglpubsmeetingsmtg36b.pdf": (
            "\n\nReferences:\n\nDunlap, M.K.", "Classification AEGL-1 (Nondisabling)"
        ),
        "wwitiantuagrhsjredbooks164hysj164010077.pdf": (
            "REFERENCES Abrahams, A.D. & Miller, A.J.",
            "Distributions multivariates des valeurs extrêmes dans les analyses hydrologiques RESUME",
        ),
    }
    records = [json.loads(line) for line in jsonl_path.open(encoding="utf-8")]
    by_name = {record["source_file"]: record for record in records}
    expected = set(titles) | multi_article | set(plant_years) | set(date_year) | set(author_replacements) | set(non_authors)
    if len(records) != 864 or len(by_name) != len(records) or not expected <= by_name.keys():
        raise ValueError("This historical repair requires the 864-record predecessor, not the verified 859-record JSONL")
    before_ids = [(r["paper_id"], r["source_file"], r["pdf_path"], r["pages"]) for r in records]
    counts: Counter[str] = Counter()
    for record in records:
        name = record["source_file"]
        metadata_target = name in expected or name in {
            "quacommfclaedu20561flsgpTP106.pdf", "wwtvacomenvironmentreportsgallatinfea.pdf",
            "scholarspacemanoahawaiiedubitstream1012568792uhmphd4371r.pdf",
            "ebprofesoresieseedujestradapdfresearchrefereedfedmodelbwu.pdf",
            "jsbsgmjournalsorgcgireprint471132.pdf",
        }
        body_target = any(pattern.search(record["fulltext"]) for pattern in footer_patterns) or name in reference_spans
        if not metadata_target and not body_target:
            continue
        source_pdf(record, pdf_root)
        if name in titles and record["title"] != titles[name]:
            record["title"] = titles[name]
            counts["title"] += 1
        if name in multi_article:
            if record["title"]:
                record["title"] = ""
                counts["title_cleared_collection"] += 1
            if "multi_article_source_no_single_paper_title" not in record["errors"]:
                record["errors"].append("multi_article_source_no_single_paper_title")
        if name in plant_years or name in date_year:
            year = plant_years.get(name, date_year.get(name))
            date = "2003-10-10" if name in {"ntlplantcellorgcgireprint15112503.pdf", "wwplantcellorgcgireprint15112503.pdf"} else ""
            if record["date"] != date or record["year"] != year:
                record["date"], record["year"] = date, year
                counts["date_year"] += 1
        if name in author_replacements and record["authors"] != author_replacements[name]:
            record["authors"] = author_replacements[name]
            counts["authors"] += 1
        if name in non_authors:
            authors = [value for value in record["authors"] if value not in non_authors[name]]
            if authors != record["authors"]:
                record["authors"] = authors
                counts["authors"] += 1
        if name == "scholarspacemanoahawaiiedubitstream1012568792uhmphd4371r.pdf":
            if record["affiliation"]:
                record["affiliation"] = []
                counts["affiliation"] += 1
        elif name == "quacommfclaedu20561flsgpTP106.pdf":
            value = [v for v in record["affiliation"] if not v.startswith("LIST OF ")]
            if value != record["affiliation"]:
                record["affiliation"] = value
                counts["affiliation"] += 1
        elif name == "wwtvacomenvironmentreportsgallatinfea.pdf":
            value = ["Tennessee Valley Authority"]
            if record["affiliation"] != value:
                record["affiliation"] = value
                counts["affiliation"] += 1
            value = ["1101 Market Street, MR 2T, Chattanooga, TN 37402"]
            if record["address"] != value:
                record["address"] = value
                counts["address"] += 1
        if name == "ebprofesoresieseedujestradapdfresearchrefereedfedmodelbwu.pdf":
            value = ["Av. Pearson 21, 08034 Barcelona, Spain"]
            if record["address"] != value:
                record["address"] = value
                counts["address"] += 1
        elif name == "jsbsgmjournalsorgcgireprint471132.pdf":
            value = [v for v in record["address"] if not v.startswith("Karolinska Institutet 1982)")]
            if value != record["address"]:
                record["address"] = value
                counts["address"] += 1
        if body_target:
            body = record["fulltext"]
            if name == "wwitiantuagrhsjredbooks164hysj164010077.pdf":
                first_start = body.find("REFERENCES Acres, H.G. & Co.")
                first_end = body.find("The role of quantitative geomorphology in the hydrologicai response of river networks", first_start)
                if first_start >= 0 and first_end < 0:
                    raise ValueError(f"First reference section boundaries changed: {name}")
                if first_start >= 0:
                    body = body[:first_start] + "\n\n" + body[first_end:]
                    counts["reference_section"] += 1
            if name in reference_spans:
                start_token, end_token = reference_spans[name]
                start = body.find(start_token)
                end = body.find(end_token, start + len(start_token))
                if start >= 0 and end < 0:
                    raise ValueError(f"Reference section boundaries changed: {name}")
                if start >= 0:
                    body = body[:start] + "\n\n" + body[end:]
                    counts["reference_section"] += 1
            prior_footer = body
            for pattern in footer_patterns:
                body = pattern.sub("", body)
            if body != prior_footer:
                counts["footer_records"] += 1
            body = re.sub(r"[ \t]+\n", "\n", body)
            body = re.sub(r"\n{3,}", "\n\n", body)
            record["fulltext"] = body
        for field in ("title", "authors", "date", "year", "affiliation", "address"):
            marker = f"missing: {field}"
            record["errors"] = [e for e in record["errors"] if e != marker]
            if not record[field]:
                record["errors"].append(marker)
        record["errors"] = list(dict.fromkeys(record["errors"]))
        record["parse_status"] = "partial" if record["errors"] else "success"
    assert before_ids == [(r["paper_id"], r["source_file"], r["pdf_path"], r["pages"]) for r in records]
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=jsonl_path.parent, prefix="pdf_repair_", suffix=".tmp", delete=False) as output:
            temp_name = Path(output.name)
            for record in records:
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
        temp_name.replace(jsonl_path)
    finally:
        if temp_name is not None and temp_name.exists():
            temp_name.unlink()
    print(json.dumps({"records": len(records), "updated_fields": counts, "output": str(jsonl_path)}, ensure_ascii=False))


def repair_followup_pdf_evidence(jsonl_path: Path, pdf_root: Path) -> None:
    """Apply a second set of cover-page verified metadata corrections in place."""
    changes: dict[str, dict] = {
        "wwwituuseresearchpublicationslic20070042007004.pdf": {
            "authors": ["Olof Rensfelt"], "year": 2007,
        },
        "wwwclevelandfedorgourregioncommunitydevelopmenteventsseminars20080425finlitloiblreducedpaper.pdf": {
            "title": "Survey of Financial Education in Ohio's High Schools: Assessment of Teachers, Programs, and Legislative Efforts",
            "authors": ["Cäzilia Loibl"], "year": 2008,
            "affiliation": ["The Ohio State University, Department of Consumer Sciences"],
            "address": ["1787 Neil Avenue, 265 N Campbell Hall, Columbus, Ohio 43210"],
        },
        "wwpnlgovmainpublicationsexternaltechnicalreportsPNNL18293.pdf": {
            "authors": ["A. C. Rohay", "R. E. Clayton", "M. D. Sweeney", "J. L. Devary", "D. C. Hartshorn"],
            "year": 2009, "affiliation": ["Pacific Northwest National Laboratory"],
        },
        "wwmonashedumuarcreportsmuarc124.pdf": {
            "authors": ["Wendy L. Watson", "Joan Ozanne-Smith"], "year": 1997,
            "affiliation": ["Monash University Accident Research Centre"], "address": [],
        },
        "scholarspacemanoahawaiiedubitstream1012568792uhmphd4371r.pdf": {
            "authors": ["Li Yang"], "year": 2003, "affiliation": ["University of Hawai'i"],
        },
        "ofccfsnrcangccabookstorepdfs26570.pdf": {
            "authors": ["J. R. Parkins", "S. Nadeau", "L. Hunt", "J. Sinclair", "M. Reed", "S. Wallace"],
            "year": 2006,
            "affiliation": ["Canadian Forest Service, Northern Forestry Centre", "Canadian Forest Service, Atlantic Forestry Centre", "Ontario Ministry of Natural Resources, Centre for Northern Ecosystem Research", "University of Manitoba, Natural Resources Institute", "University of Saskatchewan, Department of Geography"],
            "address": [],
        },
        "ccpeecsumichedutheseskvmanthesis.pdf": {
            "authors": ["Manjunath V. Kudlur"], "year": 2008,
            "affiliation": ["University of Michigan"],
        },
        "wwucalgarycaengowebdocsMT0520232Li2028Tony2920Sheng.pdf": {
            "authors": ["Li Sheng"], "year": 2005,
            "affiliation": ["University of Calgary, Department of Geomatics Engineering"],
            "address": [],
        },
        "publluthse14021757200652LTULIC0652SE.pdf": {
            "authors": ["Matti Rantatalo"], "year": 2006,
            "affiliation": ["Luleå University of Technology"],
        },
        "publluthse14021757200713LTULIC0713SE.pdf": {
            "authors": ["Samuel Cupillard"], "year": 2007,
            "affiliation": ["Luleå University of Technology"],
        },
        "wwpopcenterorgproblemsPDFsDrugMarkets.pdf": {
            "authors": ["Alex Harocopos", "Mike Hough"],
            "affiliation": [], "address": [],
        },
        "wwsbroscofffrEcchispdf05MacphersonZootaxa.pdf": {
            "authors": ["Enrique Macpherson", "Michel Segonzac"],
            "date": "2005-12-13", "year": 2005,
            "affiliation": ["Centro de Estudios Avanzados de Blanes (CSIC)", "Ifremer, Centre de Brest, DEEP/Laboratoire Environnement Profond"],
            "address": ["C. acc. Cala San Francesc 14, 17300 Blanes, Spain", "BP 70, 29280 Plouzané, France"],
        },
        "wwclcstitechacjpalrWS5th5thALR.pdf": {
            "authors": [], "affiliation": [], "address": [], "abstract": "", "year": 2005,
        },
        "cholarlibvteduthesespublicetd1642121439711031etd.pdf": {
            "authors": ["Weiqun Gu"], "year": 1997,
            "affiliation": ["Virginia Polytechnic Institute and State University"], "address": [],
        },
        "quacommfclaedu25501FloridaBayScallops.pdf": {
            "authors": ["Norman J. Blake", "Charles Adams", "Robert Degner", "Don Sweat"],
            "year": 2000,
            "affiliation": ["University of South Florida", "University of Florida", "Florida Sea Grant"],
        },
        "psocietyorgfileslecture13220908.pdf": {
            "title": "ACC/AHA 2006 Guideline Update on Perioperative Cardiovascular Evaluation for Noncardiac Surgery: Focused Update on Perioperative Beta-Blocker Therapy A Report of the American College of Cardiology/American Heart Association Task Force on Practice Guidelines (Writing Committee to Update the 2002 Guidelines on Perioperative Cardiovascular Evaluation for Noncardiac Surgery) Developed in Collaboration With the American Society of Echocardiography, American Society of Nuclear Cardiology, Heart Rhythm Society, Society of Cardiovascular Anesthesiologists, Society for Cardiovascular Angiography and Interventions, and Society for Vascular Medicine and Biology",
            "authors": ["Lee A. Fleisher", "Joshua A. Beckman", "Kenneth A. Brown", "Hugh Calkins", "Elliott Chaikof", "Kirsten E. Fleischmann", "William K. Freeman", "James B. Froehlich", "Edward K. Kasper", "Judy R. Kersten", "Barbara Riegel", "John F. Robb"],
            "year": 2006,
        },
        "krexkstateedudspacebitstream209714781LanceKlein2009.pdf": {
            "affiliation": ["Kansas State University"], "address": [], "year": 2009,
        },
        "wwcercutexasedujayfvsurveysShankar.pdf": {
            "affiliation": ["University of Maryland"],
        },
        "wwforgovbccahfdlibraryFIA2008FSPM085226.pdf": {
            "affiliation": ["Caribou Ecological Consulting", "Gentian Botanical Research", "Skeena Forestry Consultants"],
            "address": ["Box 3652, Smithers, B.C. V0J 2N0", "4861 Nielsen Road, Smithers, B.C. V0J 2N2", "2041 Moncton Rd., Smithers, B.C. V0J 2N4"],
            "year": 2008,
        },
        "wwxs4allnlhackWORKHackPublications200220IAEG20Durbaninftechp7.pdf": {
            "affiliation": [], "address": [],
        },
        "ritouciedupapers2002GEC2France.pdf": {
            "affiliation": ["University of Paris X", "Center for Research on Information Technology and Organizations, University of California, Irvine"],
            "address": ["200 avenue de la République, F-92001 Nanterre Cedex, France"],
            "year": 2002,
        },
        "wwciforcgiarorgpublicationspdffilesOccPapersOP51.pdf": {
            "affiliation": ["Institute of Tropical Forest Conservation", "CIFOR", "Sekala", "The Nature Conservancy", "World Agroforestry Centre", "Stanford University"],
            "address": [],
        },
        "wwindiaenvironmentportalorginfilesoilpalmsoutheastasia.pdf": {
            "affiliation": ["Institute of Tropical Forest Conservation", "CIFOR", "Sekala", "The Nature Conservancy", "World Agroforestry Centre", "Stanford University"],
            "address": [],
        },
        "ebengroregonstateeduzhangeimagesasymtenfld.pdf": {
            "authors": ["Eugene Zhang", "Harry Yeh", "Zhongzang Lin", "Robert S. Laramee"],
            "address": ["220 Owen Hall, Corvallis, OR 97331-3212", "1148 Kelley Engineering Center, Corvallis, OR 97331", "Wales, UK SA2 8PP"],
            "year": 2009,
        },
        "eotesttamueduuserfiles2272009JAMCdry.pdf": {
            "address": ["College Station, Texas"],
        },
        "wwatmosumdedu7EmassimoMBSN2008b.pdf": {
            "authors": ["Massimo Bollasina", "Sumant Nigam"],
            "address": ["College Park, MD 20742-2425, USA"], "year": 2008,
        },
        "wwcrwrutexasedugisgishydro03Libraryakmansoyrpt983.pdf": {
            "address": ["J.J. Pickle Research Campus, Austin, TX 78712-4497"], "year": 1997,
        },
        "wwlevyorgpubswp308.pdf": {
            "address": ["Santa Barbara"],
        },
        "wwplantphysiolorgcgireprint1112551.pdf": {
            "address": ["Seville, Spain", "Apartado 553, 41080 Seville, Spain", "Université de Paris-Sud, Centre d’Orsay Cedex, France"],
            "year": 1996,
        },
        "wfscnoaagovpublicationsfed00634.pdf": {
            "title": "The State of the California Current, 1997–1998: Transition to El Niño Conditions",
            "authors": ["Ronald J. Lynn", "Tim Baumgartner", "Joaquin Garcia", "Curtis A. Collins", "Thomas L. Hayward", "K. David Hyrenbach", "Arnold W. Mantyla", "Tom Murphree", "Amy Shankle", "Franklin B. Schwing", "Keith M. Sakuma", "Mia J. Tegner"],
            "affiliation": ["Southwest Fisheries Science Center, National Marine Fisheries Service, NOAA", "Centro de Investigación Científica y Educación Superior de Ensenada", "Department of Oceanography, Naval Postgraduate School", "Scripps Institution of Oceanography, University of California, San Diego", "Department of Meteorology, Naval Postgraduate School", "Pacific Fisheries Environmental Laboratory, National Marine Fisheries Service, NOAA"],
            "address": ["P.O. Box 271, La Jolla, California 92038", "Carretera Tijuana-Ensenada, Ensenada, B.C., México", "589 Dyer Road, Monterey, California 93943-5114", "9500 Gilman Drive, La Jolla, California 92093-0227", "9500 Gilman Drive, La Jolla, California 92093-0218", "1352 Lighthouse Avenue, Monterey, California 93950-2097", "3150 Paradise Drive, Tiburon, California 94920", "9500 Gilman Drive, La Jolla, California 92093-0201"],
            "year": 1998,
        },
        "esearchmicrosoftcomenuspeopletyliuletortutorialsigir08.pdf": {
            "authors": ["Tie-Yan Liu"], "affiliation": ["Microsoft Research Asia"],
        },
        "researchmicrosoftcompubs101031SinhaICCV09.pdf": {
            "authors": ["Sudipta N. Sinha", "Drew Steedly", "Richard Szeliski"],
            "affiliation": ["Microsoft Research", "Microsoft"],
        },
        "rogrammingvisioncompapersdiankov08robotbusboy.pdf": {
            "authors": ["Siddhartha Srinivasa", "Dave Ferguson", "Mike Vande Weghe", "Rosen Diankov", "Dmitry Berenson", "Casey Helfrich", "Hauke Strasdat"],
        },
        "wwricmuedupubfilespub4srinivasasiddhartha20081srinivasasiddhartha20081.pdf": {
            "authors": ["Siddhartha Srinivasa", "Dave Ferguson", "Mike Vande Weghe", "Rosen Diankov", "Dmitry Berenson", "Casey Helfrich", "Hauke Strasdat"],
        },
        "wwerightsorgelangtoolscausewaycausewaypaper.pdf": {
            "authors": ["Terry Stanley", "Tyler Close", "Mark S. Miller"],
        },
        "wwfsfeduspnwpubsjournalspnw2007suzuki001.pdf": {
            "authors": ["Nobuya Suzuki", "Deanna H. Olson"], "year": 2007,
        },
        "wwplantphysiolorgcgireprint1032467.pdf": {
            "title": "Cloning of Higher Plant ω-3 Fatty Acid Desaturases",
            "authors": ["Narendra S. Yadav", "Anna Wierzbicki", "Mary Aegerter", "Cheryl S. Caster", "Luís Pérez-Grau", "Anthony J. Kinney", "William D. Hitz", "J. Russell Booth Jr.", "Bruce Schweiger", "Kevin L. Stecca", "Stephen M. Allen", "Marita Blackwell", "Robert S. Reiter", "Thomas J. Carlson", "Sandra H. Russell", "Kenneth A. Feldmann", "John Pierce", "John Browse"],
            "year": 1993,
        },
        "rotocolknuackrpub2008iccipmma.pdf": {
            "title": "Analysis of Handover Latency for Mobile IPv6 and mSCTP",
            "authors": ["Dong Phil Kim", "Seok Joo Koh"],
            "affiliation": ["Department of Computer Science, Kyungpook National University"],
            "address": ["Daegu, Korea"], "year": 2008,
        },
        "reinunicaitcornelisRICERCAPAPERS167.pdf": {
            "authors": ["Cornelis van der Mee", "Paolo Pintus", "Sebastiano Seatzu"], "year": 2008,
        },
        "wwaeropolimiitmasaratiPublicationsfsi2009.pdf": {
            "authors": ["Luca Cavagna", "Pierangelo Masarati", "Giuseppe Quaranta"],
            "affiliation": ["Politecnico di Milano, Dipartimento di Ingegneria Aerospaziale", "FOI (Swedish Defence Research Agency), Aeronautics and Systems Integration"],
            "year": 2009,
        },
        "wwbnlgovisddocuments32348.pdf": {
            "authors": ["C. C. Kuo", "J. R. Chen", "P. J. Chou", "H. P. Chang", "K. T. Hsu", "G. H. Luo", "H. J. Tsai", "D. J. Wang", "M. H. Wang", "A. Chao", "W. T. Weng"],
            "year": 2006,
        },
        "wwplantphysiolorgcgireprint14931529.pdf": {
            "authors": ["Ruchika Budhiraja", "Rebecca Hermkes", "Stefan Müller", "Jürgen Schmidt", "Thomas Colby", "Kishore Panigrahi", "George Coupland", "Andreas Bachmair"],
            "year": 2009,
        },
        "wwjdentaledorgcgireprint705500.pdf": {
            "authors": ["Mohsen Taleghani", "Eric S. Solomon", "William F. Wathen"],
        },
        "wwjneurosciorgcgireprint19114388.pdf": {
            "authors": ["Antonella Antonini", "Michela Fagiolini", "Michael P. Stryker"],
            "date": "1999-06-01", "year": 1999,
        },
        "wworalcancerorgfactspdfradiationtypes.pdf": {
            "authors": ["M. Kara Bucci", "Alison Bevan", "Mack Roach III"], "year": 2005,
        },
        "wwsearchanddiscoverynetdocuments200960045majorndxmajor.pdf": {
            "title": "Modern Carbonate Sediment Facies Heterogeneity at the Development Scale – An Example from Joulters Cays, Bahamas",
            "authors": ["R. P. Major", "D. G. Bebout", "P. M. Harris"],
            "year": 1997,
        },
        "wwspcncepnoaagovpublicationscorfidildd2006.pdf": {
            "authors": ["Stephen F. Corfidi", "Sarah J. Corfidi", "David A. Imy", "Allen L. Logan"],
        },
        "ntlplantcellorgcgireprint15483.pdf": {
            "title": "Sequence Variability of Three Alleles of the Self-Incompatibility Gene of Nicotiana alata",
            "authors": ["Marilyn A. Anderson", "Geoffrey I. McFadden", "Robert Bernatzky", "Angela Atkinson", "Timothy Orpin", "Helen Dedman", "Geoffrey Tregear", "Ross Fernley", "Adrienne E. Clarke"],
        },
        "ntlplantcellorgcgireprint17727.pdf": {
            "authors": ["Virginia M. Ursin", "Judy Yamaguchi", "Sheila McCormick"],
        },
        "ntlplantcellorgcgireprint2129.pdf": {
            "title": "A Brassica Self-Incompatibility Gene Is Expressed in the Stylar Transmitting Tissue of Transgenic Tobacco",
            "authors": ["Helen M. Moore", "June B. Nasrallah"],
        },
        "ntlplantcellorgcgireprint3111239.pdf": {
            "title": "A Scaffold-Associated DNA Region Is Located Downstream of the Pea Plastocyanin Gene",
            "authors": ["Rosalind E. Slatter", "Paul Dupree", "John C. Gray"],
        },
        "ntlplantcellorgcgireprint6121805.pdf": {
            "authors": ["Kazuyuki Hiratsuka", "Xiaodong Wu", "Hideya Fukuzawa", "Nam-Hai Chua"],
        },
        "ntlplantcellorgcgireprint7121975.pdf": {
            "title": "Double Fertilization in Gnetum gnemon: The Relationship between the Cell Cycle and Sexual Reproduction",
            "authors": ["Jeffrey S. Carmichael", "William E. Friedman"],
        },
        "ntlplantcellorgcgireprint75549.pdf": {
            "authors": ["Stephen Cronin", "Jeanmarie Verchot", "Ruth Haldeman-Cahill", "Mary C. Schaad", "James C. Carrington"],
        },
        "ntlplantcellorgcgireprint77809.pdf": {
            "authors": ["Steven Gutteridge", "Anthony A. Gatenby"],
        },
        "ntlplantcellorgcgireprint781235.pdf": {
            "title": "Aberrant Transpositions of Maize Double Ds-Like Elements Usually Involve Ds Ends on Sister Chromatids",
            "authors": ["James J. English", "Kate Harrison", "Jonathan D. G. Jones"],
        },
        "ntlplantcellorgcgireprint781295.pdf": {
            "title": "The Initiation Codon Determines the Efficiency but Not the Site of Translation Initiation in Chlamydomonas Chloroplasts",
            "authors": ["Xuemei Chen", "Karen L. Kindle", "David B. Stern"],
        },
        "wwplantphysiolorgcgireprint14841740.pdf": {
            "authors": ["Roger W. Innes", "Carine Ameline-Torregrosa", "Tom Ashfield", "Ethalinda Cannon", "Steven B. Cannon", "Ben Chacko", "Nicolas W. G. Chen", "Arnaud Couloux", "Anita Dalwani", "Roxanne Denny", "Shweta Deshpande", "Ashley N. Egan", "Natasha Glover", "Christian S. Hans", "Stacy Howell", "Dan Ilut", "Scott Jackson", "Hongshing Lai", "Jafar Mammadov", "Sara Martin del Campo", "Michelle Metcalf", "Ashley Nguyen", "Majesta O'Bleness", "Bernard E. Pfeil", "Ram Podicheti", "Milind B. Ratnaparkhe", "Sylvie Samain", "Iryna Sanders", "Béatrice Ségurens", "Mireille Sévignac", "Sue Sherman-Broyles", "Vincent Thareau", "Dominic M. Tucker", "Jason Walling", "Adam Wawrzynski", "Jing Yi", "Jeff J. Doyle", "Valérie Geffroy", "Bruce A. Roe", "M. A. Saghai Maroof", "Nevin D. Young"],
            "year": 2008,
        },
        "wwepagovesdlandsciagwapdfusermanual.pdf": {
            "authors": ["I. S. Burns", "S. Scott", "L. Levick", "M. Hernandez", "D. C. Goodrich"],
            "affiliation": ["USDA-ARS, Southwest Watershed Research Center"],
            "address": ["Tucson, Arizona"],
        },
        "wwejournalunammxatmVol162ATM16204.pdf": {
            "authors": ["J. L. Minetti", "W. M. Vargas", "A. G. Poblete", "L. R. Acuña", "G. Casagrande"],
            "affiliation": ["Laboratorio Climatológico Sudamericano (Fundación Caldenius)", "Departamento de Ciencias de la Atmósfera y los Océanos, Universidad de Buenos Aires", "Instituto de Geografía Aplicada, Universidad Nacional de San Juan", "Instituto Nacional de Tecnología Agropecuaria", "Consejo Nacional de Investigaciones Científicas y Técnicas"],
            "year": 2003,
        },
        "wwepagovwaterstmdldocs35148cranecreekfecal.pdf": {
            "authors": ["Kyeongsik Rhew"],
            "date": "2008-04-07", "year": 2008,
            "affiliation": ["Florida Department of Environmental Protection, Division of Water Resource Management, Bureau of Watershed Management"],
        },
        "wwepagovwaterstmdldocsswampcreekfecaltmdl.pdf": {
            "authors": ["Richard Wieckowicz", "Ben Ralys", "Erin Wilcox"],
            "date": "2008-09-22", "year": 2008,
            "affiliation": ["Florida Department of Environmental Protection, Division of Water Resource Management, Bureau of Watershed Management"],
        },
        "cholarspacemanoahawaiiedubitstream10125118782uhmma3256r.pdf": {
            "authors": ["Diane C. Wilson"], "year": 2005,
        },
        "ebxubiptsebastiaotese.pdf": {
            "authors": ["Sebastião Pais"], "year": 2008,
        },
        "esearchmicrosoftcomenuspeopletyliulearningtoranktutorialwww2008.pdf": {
            "authors": ["Tie-Yan Liu"], "year": 2008,
        },
        "heredoxfordjournalsorgcgireprint913186.pdf": {
            "authors": ["M. Culver", "W. E. Johnson", "J. Pecon-Slattery", "S. J. O'Brien"],
        },
        "hqlibdocwhointbulletin2001issue4794365372.pdf": {
            "authors": ["Jon Harkness", "Susan E. Lederer", "Daniel Wikler"],
        },
        "jsbsgmjournalsorgcgireprint471132.pdf": {
            "authors": ["Margarita Ginard", "Jorge Lalucat", "Burkhard Tümmler", "Ute Römling"],
            "year": 1997,
        },
        "kbosuedudspacebitstream181164291RobertJMessingerHonorsThesis.pdf": {
            "authors": ["Robert James Messinger"], "year": 2006,
        },
        "kbosuedudspacebitstream181164441smelkerhonorsthesis.pdf": {
            "authors": ["Keith Patrick Smelker"], "year": 2006,
        },
        "krexkstateedudspacebitstream20971451NibeditaDas2006B.pdf": {
            "authors": ["Nibedita Das"],
        },
        "mazonevscvirginiaeduthesisDusterhoff2001.pdf": {
            "authors": ["Scott Dusterhoff"], "year": 2001,
        },
        "mcihmcuscmc2006paperscmc2006p99.pdf": {
            "authors": ["Leda Beirute", "Milena Brenes", "Gabriela Cortés", "Sandra García", "Alejandra Meza"],
            "year": 2006,
        },
        "rchivenumdamorgARCHIVEAIFAIF1968181AIF19681812830AIF19681812830.pdf": {
            "authors": ["Peter Loeb", "Bertram Walsh"], "year": 1968,
        },
        "rchivenumdamorgARCHIVEAIFAIF1971212AIF1971212850AIF1971212850.pdf": {
            "authors": ["André Unterberger"], "year": 1971,
        },
        "rchivenumdamorgARCHIVEAIFAIF1972222AIF19722222550AIF19722222550.pdf": {
            "authors": ["André Hirschowitz"], "year": 1972,
        },
        "rchivenumdamorgARCHIVEAIFAIF1976263AIF19762632110AIF19762632110.pdf": {
            "authors": ["Jean Saint Raymond"], "year": 1976,
        },
        "rchivenumdamorgARCHIVEAIFAIF1997472AIF19974724850AIF19974724850.pdf": {
            "authors": ["Jean-Pierre Kahane", "Hervé Queffélec"], "year": 1997,
        },
        "researchwsulibswsuedu8443jspuibitstream23762781cosorio121304.pdf": {
            "authors": ["Claudia E. Osorio"], "year": 2004,
        },
        "rexkstateedudspacebitstream209713581NozomiMatsumiya2009.pdf": {
            "authors": ["Nozomi Matsumiya"], "year": 2009,
        },
        "rexkstateedudspacebitstream20979011JamesYoung2008.pdf": {
            "authors": ["James L. Young Jr."], "year": 2008,
        },
        "scholarspacemanoahawaiiedubitstream10125105491uhmms3935r.pdf": {
            "authors": ["Tracy E. Tisdale"], "year": 2004,
        },
        "scholarspacemanoahawaiiedubitstream1012568662uhmphd4352r.pdf": {
            "authors": ["Daniela Maldini"], "year": 2003,
        },
        "somfacultycaseeduritchkendocumentsBank.pdf": {
            "authors": ["C. N. V. Krishnan", "P. H. Ritchken", "J. B. Thomson"],
        },
        "sppsdpwgscgccacollection2008electionsSE3702007E.pdf": {
            "authors": ["Michael J. Prince"],
        },
        "ultiphaseasuedupaperctr2003a.pdf": {
            "authors": ["M. Herrmann"], "year": 2003,
        },
        "wwafscnoaagovpublicationsafsctmnoaatmafsc45.pdf": {
            "authors": [], "year": 1994,
        },
        "wwccpooduedutezerPAPERS2005AGUGOM.pdf": {
            "authors": ["L.-Y. Oey", "T. Ezer", "H.-C. Lee"], "year": 2005,
        },
        "wwciforcgiarorgpublicationspdffilesOccPapersOP51.pdf": {
            "authors": ["Douglas Sheil", "Anne Casson", "Erik Meijaard", "Meine van Noordwijk", "Joanne Gaskell", "Jacqui Sunderland-Groves", "Karah Wertz", "Markku Kanninen"],
        },
        "wwcsbrowneduresearchpubsthesesmasters1992cheng.pdf": {
            "authors": ["Ming-Li Cheng"],
        },
        "wwcsueducercresearchreportsdocumentsGreatLakesSedimentsContaminationToxicityBeneficialReUse.pdf": {
            "authors": ["Peter Adriaens", "Stuart Batterman", "Joel Blum", "Kim Hayes", "Phil Meyers", "Walter Weber Jr."],
            "year": 2002,
        },
        "wwetsorgMediaResearchpdfRR0113Sheehan.pdf": {
            "authors": ["Kathleen M. Sheehan", "Robert J. Mislevy"], "year": 2001,
        },
        "wwggrhulacukict4dworkingpapersMitra1.pdf": {
            "authors": ["Sugata Mitra"],
        },
        "wwindiaenvironmentportalorginfilesoilpalmsoutheastasia.pdf": {
            "authors": ["Douglas Sheil", "Anne Casson", "Erik Meijaard", "Meine van Noordwijk", "Joanne Gaskell", "Jacqui Sunderland-Groves", "Karah Wertz", "Markku Kanninen"],
        },
        "wwmathtauacildaliafSISC1990vortex.pdf": {
            "authors": ["Dalia Fishelov"], "year": 1990,
        },
        "wwnasagovcentersdrydenpdf88757mainH2521.pdf": {
            "authors": ["David Voracek", "Ed Pendleton", "Eric Reichenbach", "Kenneth Griffin", "Leslie Welch"],
            "year": 2003,
        },
        "wwncsueducrscreportsftppdfcrsctr0821.pdf": {
            "authors": [],
        },
        "wwnlpriaaccn2008papersgjkwgk6.pdf": {
            "authors": ["Weiming Hu", "Xue Zhou", "Min Hu", "Steve Maybank"],
            "year": 2009,
        },
        "wwounlDocsOnderzoekPromoties2007ProefschriftDaantjeDerksdefinitieveversie.pdf": {
            "authors": ["Daantje Derks"],
        },
        "wworegongovODOTTDTPRESdocsReports2008BentCapsReportPart1.pdf": {
            "authors": ["Christopher Higgins", "Ahmet Ekin Senturk", "Carl C. Koester"],
            "year": 2008,
        },
        "wwphaasnetdocumentsVol1.pdf": {
            "authors": ["Andrea Leeson", "Robert E. Hinchee"], "year": 1996,
        },
        "wwplantphysiolorgcgireprint356783.pdf": {
            "title": "On the Theory of Osmotic Water Movement",
            "authors": ["Peter M. Ray"],
        },
        "wwpsiepsuedupublicationsreportspsieePSIE200302Lynchetal.pdf": {
            "authors": ["James A. Lynch", "Kevin S. Horner", "Jeffrey W. Grimm"],
        },
        "wwsagesacukhomehomesrgroveswoodpub3.pdf": {
            "authors": ["Rachel Wood"],
        },
        "wwsilsiedusmithsoniancontributionsBotanypdfhisctb0047.pdf": {
            "authors": ["F. Raymond Fosberg", "Marie-Hélène Sachet"], "year": 1981,
        },
        "xplorationgrcnasagovAdvancedISSResearchInvestigationsFLEXdocumentsFLEXEIRDv4.pdf": {
            "authors": [], "year": 2005,
        },
        "xtensionusuedufilespublicationspublicationpub4078090.pdf": {
            "authors": ["Leah S. Smith", "Terry A. Messmer"], "year": 2008,
        },
        "xtensionusuedufilespublicationspublicationpub8111133.pdf": {
            "authors": ["Rhett L. Boswell", "Nicole S. Frey"], "year": 2007,
        },
        "inneapolisfedorgresearchQRQR3112.pdf": {
            "authors": [], "affiliation": [], "address": [], "abstract": "",
        },
        "isfsfeduspswpublicationsdocumentspswgtr100pswgtr100002.pdf": {
            "authors": [], "year": 1987, "affiliation": [], "address": [], "abstract": "",
        },
        "wwfsfeduspswpublicationsdocumentspswgtr100pswgtr100c.pdf": {
            "authors": [], "year": 1987, "affiliation": [], "address": [], "abstract": "",
        },
        "wwitiantuagrhsjredbooks164hysj164010077.pdf": {
            "authors": [], "year": 1987, "affiliation": [], "address": [], "abstract": "",
        },
    }
    # These dates are explicitly receipt, acceptance, presentation or discussion dates.
    invalid_dates: dict[str, int | None] = {
        "bmborkrjbmbjbmbfiles5B4255D09052509432824525929BMB226.pdf": 2009,
        "eotesttamueduuserfiles2272009JAMCdry.pdf": 2009,
        "indyaoswiscedupaoSetvakRabinWangAtmRes2007.pdf": 2007,
        "lympicatmoscolostateedutlangpubsjtech164021prf.pdf": 2004,
        "prcsoesthawaiieduusersxfustudy1MWRFuWang.pdf": 2004,
        "wwaeromechusydeduau15afmcproceedingspapersAFMC00105.pdf": 2004,
        "wwaomlnoaagovphoddocswangetal2006jcl.pdf": 2006,
        "wwcawcrgovaustaffjmameehlsolarcoldeventlike2008.pdf": 2008,
        "wwcgducareduccrpublicationsmeehltboocean.pdf": 2003,
        "wweemmorkrarticlearticlefilesEMM0390617.pdf": 2007,
        "wwgeogucsbedujoelg280s09studentcontribmcnallyMuzaetal2009interanintras.pdf": 2009,
        "wwitiantuagrhsj43hysj43010067.pdf": 1998,
        "wwmeteopsueduslpapersSonetal08.pdf": 2008,
        "wwpmfsthrzeljkajames.pdf": 2009,
        "wwspcncepnoaagovpublicationscorfidildd2006.pdf": 2006,
        "wwtaratcdiebitstream226227411jssisiVolXXVI211276.pdf": None,
        "wwwritingucsbeduwrconf08PdfArticlesHaswellArticle.pdf": 2005,
    }
    records = [json.loads(line) for line in jsonl_path.open(encoding="utf-8")]
    by_name = {r["source_file"]: r for r in records}
    if len(records) != 864 or len(by_name) != len(records) or not (changes.keys() | invalid_dates.keys()) <= by_name.keys():
        raise ValueError("This historical repair requires the 864-record predecessor, not the verified 859-record JSONL")
    counts: Counter[str] = Counter()
    identities = [(r["paper_id"], r["source_file"], r["pdf_path"], r["pages"]) for r in records]
    for record in records:
        name = record["source_file"]
        update = changes.get(name)
        if update is not None or name in invalid_dates:
            source_pdf(record, pdf_root)
        if update is not None:
            for field, value in update.items():
                if record[field] != value:
                    record[field] = value
                    counts[field] += 1
        if name == "wwsierraforestlegacyorgResourcesConservationSierraNevadaWildlifePacificFisherPFBoroski02.pdf":
            interrupted = (
                "with fieldwork beginning in 1994 (Verner and Fisher Research and the Kings River "
                "Sustainable Forest Ecosystems Project: Current Results and Future Efforts � Sierra National Forest\n\n"
                "Smith, this volume)."
            )
            restored = "with fieldwork beginning in 1994 (Verner and Smith, this volume)."
            if interrupted in record["fulltext"]:
                record["fulltext"] = record["fulltext"].replace(interrupted, restored, 1)
                counts["fulltext"] += 1
            if "�" not in record["fulltext"]:
                record["errors"] = [error for error in record["errors"] if error != "unreadable_characters_in_fulltext"]
        if name in invalid_dates:
            issue_date = {
                "wwaomlnoaagovphoddocswangetal2006jcl.pdf": "2006-06-15",
                "wwcawcrgovaustaffjmameehlsolarcoldeventlike2008.pdf": "2008-06-15",
            }.get(name, "")
            if record["date"] != issue_date or record["year"] != invalid_dates[name]:
                record["date"] = issue_date
                record["year"] = invalid_dates[name]
                counts["invalid_date_corrected"] += 1
        if name in {
            "isfsfeduspswpublicationsdocumentspswgtr100pswgtr100002.pdf",
            "wwfsfeduspswpublicationsdocumentspswgtr100pswgtr100c.pdf",
        } and "multi_article_source_no_single_paper_author" not in record["errors"]:
            record["errors"].append("multi_article_source_no_single_paper_author")
        if name in {
            "inneapolisfedorgresearchQRQR3112.pdf",
            "isfsfeduspswpublicationsdocumentspswgtr100pswgtr100002.pdf",
            "wwclcstitechacjpalrWS5th5thALR.pdf",
            "wwfsfeduspswpublicationsdocumentspswgtr100pswgtr100c.pdf",
            "wwitiantuagrhsjredbooks164hysj164010077.pdf",
        } and "multi_article_fulltext" not in record["errors"]:
            record["errors"].append("multi_article_fulltext")
        for field in ("title", "authors", "date", "year", "affiliation", "address", "abstract", "fulltext"):
            marker = f"missing: {field}"
            record["errors"] = [error for error in record["errors"] if error != marker]
            if not record[field]:
                record["errors"].append(marker)
        record["errors"] = list(dict.fromkeys(record["errors"]))
        record["parse_status"] = "partial" if record["errors"] else "success"
    if identities != [(r["paper_id"], r["source_file"], r["pdf_path"], r["pages"]) for r in records]:
        raise AssertionError("Source identity changed")
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=jsonl_path.parent, prefix="followup_pdf_", suffix=".tmp", delete=False) as output:
            temp_name = Path(output.name)
            for record in records:
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
        temp_name.replace(jsonl_path)
    finally:
        if temp_name is not None and temp_name.exists():
            temp_name.unlink()
    print(json.dumps({"records": len(records), "updated_fields": counts, "output": str(jsonl_path)}, ensure_ascii=False))


def repair_reviewed_records(jsonl_path: Path) -> None:
    """Apply PDF-verified corrections to the reviewed anomaly set in place."""
    corrections = {
        "tspacelibraryutorontocabitstream1807119711MQ34009.pdf": {
            "title": "Walking skill versus walking experience as a predictor of barrier crossing in toddlers",
        },
        "warceecsiubremendeakopubsAKoPromo.pdf": {
            "title": "Semantic Interaction Design: Composing Knowledge with CPoint",
            "authors": ["Andrea Kohlhase"],
        },
        "wwepagovopptintraeglpubsmeetingsmtg36b.pdf": {"authors": []},
        "wwmarecolgusedigitalAssets12051205097PetriKemppainendissertation.pdf": {
            "authors": ["Petri Kemppainen"],
        },
        "wwncsueducrscreportsftppdfcrsctr0821.pdf": {
            "title": "Fourteenth Industrial Mathematical and Statistical Modeling Workshop for Graduate Students",
            "authors": [],
        },
        "rystalisgsuiucedumapsdatapubisgsquadsapdffilesavabgrept.pdf": {
            "title": "Bedrock Geology of Ava Quadrangle, Jackson and Perry Counties, Illinois",
            "authors": ["F. Brett Denny"],
        },
        "wwforgovbccahfdpubsDocsRrRr24.pdf": {
            "title": "Forest, Edge, and Opening Microclimate at Sicamous Creek",
            "authors": ["D. L. Spittlehouse", "R. S. Adams", "R. D. Winkler"],
        },
        "inneapolisfedorgresearchQRQR3112.pdf": {
            "title": "Quarterly Review, Vol. 31, No. 1",
            "authors": [],
        },
        "eoplesusehalexpublalexandersonvimmerbyberlin.pdf": {
            "title": "New 10Be cosmogenic ages from the Vimmerby moraine confirm the timing of Scandinavian ice sheet deglaciation in southern Sweden",
        },
    }
    garbled = {
        "inneapolisfedorgresearchQRQR3112.pdf",
        "rystalisgsuiucedumapsdatapubisgsquadsapdffilesavabgrept.pdf",
        "sppsdpwgscgccaCollectionR71412004E9.pdf",
        "wwcsjhueduscottpllpapersmicrokernel05.pdf",
        "wwforgovbccahfdpubsDocsRrRr24.pdf",
        "wwsierraforestlegacyorgResourcesConservationSierraNevadaWildlifePacificFisherPFBoroski02.pdf",
    }
    no_abstract = {
        "mgoxfordjournalsorgcgireprint175690.pdf",
        "ntlplantcellorgcgireprint77809.pdf",
        "wwwnrelcolostateeduprojectsbighornbighorn.pdf",
        "wwwritingucsbeduwrconf08PdfArticlesHaswellArticle.pdf",
    }
    records = [json.loads(line) for line in jsonl_path.open(encoding="utf-8")]
    found = {record["source_file"] for record in records}
    expected = set(corrections) | garbled | no_abstract | {"ebbiosciutexaseduryanPublications20062006AmNat1672028.pdf"}
    if not expected <= found:
        raise ValueError(f"reviewed records missing: {sorted(expected - found)}")
    for record in records:
        name = record["source_file"]
        if name in corrections:
            record.update(corrections[name])
        if name == "ebbiosciutexaseduryanPublications20062006AmNat1672028.pdf" and not record["abstract"]:
            paragraphs = record["fulltext"].split("\n\n")
            if not paragraphs[0].lower().startswith("abstract: "):
                raise ValueError("expected abstract paragraph not found")
            record["abstract"] = paragraphs[0][len("abstract: "):]
            record["fulltext"] = "\n\n".join(paragraphs[1:])
        if name in garbled and "unreadable_characters_in_fulltext" not in record["errors"]:
            record["errors"].append("unreadable_characters_in_fulltext")
        if name in no_abstract and "missing: abstract" not in record["errors"]:
            record["errors"].append("missing: abstract")
        for field in ("title", "authors"):
            error = f"missing: {field}"
            if record[field]:
                record["errors"] = [item for item in record["errors"] if item != error]
            elif error not in record["errors"]:
                record["errors"].append(error)
        record["parse_status"] = "partial" if record["errors"] else "success"
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=jsonl_path.parent, prefix="repair_", suffix=".tmp", delete=False) as output:
            temp_name = Path(output.name)
            for record in records:
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
        temp_name.replace(jsonl_path)
    finally:
        if temp_name is not None and temp_name.exists():
            temp_name.unlink()
    print(json.dumps({"records": len(records), "corrected_metadata": len(corrections), "flagged_garbled": len(garbled), "abstract_recovered": 1, "abstract_confirmed_missing": len(no_abstract)}, ensure_ascii=False))


def recover_missing_fields(input_path: Path, output_path: Path, xml_root: Path, pdf_root: Path, report_path: Path) -> None:
    """Recover only PDF-verifiable metadata; preserve uncertain fields as missing."""
    if input_path.resolve() == output_path.resolve():
        raise ValueError("recovery output must differ from input")
    namespace = {"t": "http://www.tei-c.org/ns/1.0"}
    months = {name.lower(): number for number, name in enumerate(
        ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1
    )}
    verified_authors = {
        "printssotonacuk4250001Siegismund2006.pdf": ["Helen Snaith"],
        "wwmathfinancedeseminarsvedichandouts.pdf": ["Uwe Wystup"],
        "wwpminfethzcheducationthesesstudentdocsAnnettaSchaadAnnettaSchaadMApaper.pdf": ["Annetta Schaad"],
    }
    abstract_in_body = {
        "eagherlabtamuedummeagherhealth20360psyc2036020articlespsyc2036020ch203brownell.pdf",
        "scholarspacemanoahawaiiedubitstream1012516661v54n4417422.pdf",
        "sychologyuchicagoedupeoplefacultycacioppojtcreprintscd09.pdf",
    }
    records = []
    actions = []
    missing_before = {}
    tei_audit: Counter[str] = Counter()
    fields = ("title", "authors", "date", "year", "affiliation", "address", "abstract")
    for line in input_path.open(encoding="utf-8"):
        record = json.loads(line)
        pdf = source_pdf(record, pdf_root)
        xml = xml_root / (Path(record["source_file"]).stem + ".grobid.tei.xml")
        if not pdf.is_file() or not xml.is_file():
            raise ValueError(f"missing source for {record['source_file']}")
        header = ET.parse(xml).getroot().find("t:teiHeader", namespace)
        if header is None:
            records.append(record)
            continue
        missing_before[record["source_file"]] = [field for field in fields if not record[field]]
        for field, path in (
            ("title", ".//t:titleStmt/t:title"),
            ("authors", ".//t:analytic/t:author/t:persName"),
            ("affiliation", ".//t:analytic/t:author/t:affiliation/t:orgName"),
            ("address", ".//t:analytic/t:author/t:affiliation/t:address"),
            ("abstract", ".//t:profileDesc/t:abstract"),
        ):
            if not record[field] and any(" ".join("".join(node.itertext()).split()) for node in header.findall(path, namespace)):
                tei_audit[f"missing_{field}_with_tei_candidate"] += 1
        pdf_text = None

        def first_page() -> str:
            nonlocal pdf_text
            if pdf_text is None:
                result = subprocess.run(["pdftotext", "-f", "1", "-l", "1", str(pdf), "-"], capture_output=True, check=True)
                pdf_text = result.stdout.decode("utf-8", "replace")
            return pdf_text

        changes = {}
        if not record["authors"] and record["source_file"] in verified_authors:
            names = verified_authors[record["source_file"]]
            if all(name.casefold() in " ".join(first_page().split()).casefold() for name in names):
                record["authors"] = names
                changes["authors"] = {"value": names, "evidence": "PDF author metadata and first-page text"}
        if not record["abstract"] and record["source_file"] in abstract_in_body:
            paragraphs = record["fulltext"].split("\n\n")
            if paragraphs and re.match(r"(?i)^abstract\s*[:.\-]", paragraphs[0]):
                record["abstract"] = re.sub(r"(?i)^abstract\s*[:.\-]\s*", "", paragraphs[0], count=1)
                record["fulltext"] = "\n\n".join(paragraphs[1:])
                changes["abstract"] = {"value": record["abstract"], "evidence": "PDF abstract misclassified as first TEI body paragraph"}
        if not record["year"]:
            imprint = header.find("t:fileDesc/t:sourceDesc/t:biblStruct/t:monogr/t:imprint", namespace)
            node = imprint.find("t:date[@type='published']", namespace) if imprint is not None else None
            when = node.get("when", "") if node is not None else ""
            visible = " ".join("".join(node.itertext()).split()) if node is not None else ""
            if re.fullmatch(r"\d{4}(?:-\d{2})?", when):
                tei_audit["missing_year_with_partial_tei_published_date"] += 1
            if re.fullmatch(r"\d{4}(?:-\d{2})?", when) and re.search(r"\b" + re.escape(when[:4]) + r"\b", first_page()):
                record["year"] = int(when[:4])
                changes["year"] = {"value": record["year"], "evidence": "TEI published year and PDF first page"}
            # A full day visible in TEI and PDF can be safely normalized to ISO.
            match = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", visible)
            if match and match.group(2).lower() in months and re.search(r"\b" + re.escape(visible) + r"\b", first_page(), re.I):
                try:
                    parsed = calendar_date(int(match.group(3)), months[match.group(2).lower()], int(match.group(1)))
                except ValueError:
                    pass
                else:
                    record["date"] = parsed.isoformat()
                    record["year"] = parsed.year
                    changes["date"] = {"value": record["date"], "evidence": "full published date in TEI and PDF first page"}
                    changes["year"] = {"value": record["year"], "evidence": "full published date in TEI and PDF first page"}
        if not record["title"]:
            info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, errors="replace", check=True).stdout
            title_match = re.search(r"^Title:\s*(.+)$", info, re.MULTILINE)
            if title_match:
                candidate = " ".join(title_match.group(1).split())
                normalize = lambda value: re.sub(r"[^\w]+", " ", value.casefold()).strip()
                normalized = normalize(candidate)
                if 20 <= len(candidate) <= 250 and len(normalized.split()) >= 4 and normalized in normalize(first_page()):
                    record["title"] = candidate
                    changes["title"] = {"value": candidate, "evidence": "PDF metadata title matches first-page text"}
        for field in ("title", "authors", "date", "year", "abstract"):
            if record[field]:
                record["errors"] = [item for item in record["errors"] if item != f"missing: {field}"]
        record["parse_status"] = "partial" if record["errors"] else "success"
        if changes:
            actions.append({"source_file": record["source_file"], "changes": changes})
        records.append(record)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
    remaining = {field: sum(not record[field] for record in records) for field in fields}
    report = {"input_records": len(records), "output_records": len(records), "changes_by_field": {
        field: sum(field in action["changes"] for action in actions) for field in fields
    }, "remaining_missing": remaining, "tei_missing_field_audit": dict(tei_audit), "actions": actions}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "actions"}, ensure_ascii=False))


def supplement_confirmed(input_path: Path, output_path: Path, pdf_root: Path, evidence_path: Path, report_path: Path) -> None:
    """Add individually verified PDF metadata to a JSONL, optionally in place."""
    in_place = input_path.resolve() == output_path.resolve()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    published = {item["source_file"]: item["pdf_text"] for item in evidence["confirmed_pdf_evidence"]["publication_dates"]}
    titles = {
        "aoscoloradoedudcnSWINGworkshopsSWS1Kelley.pdf": "Two aspects of moisture origin relevant to analysis of isotope modeling",
        "cpsumneduassetspdf17baretheoryquantummeas20copy.pdf": "The Bare Theory Has No Clothes",
        "ebxubiptsebastiaotese.pdf": "Classification of Opinionated Texts by Analogy",
        "heredoxfordjournalsorgcgireprint913186.pdf": "Genomic Ancestry of the American Puma (Puma concolor)",
        "hesislibrarycaltechedu20521heidelthesis.pdf": "Targeted, Systemic Non-Viral Delivery of Small Interfering RNA In Vivo",
        "kbosuedudspacebitstream181164291RobertJMessingerHonorsThesis.pdf": "Microfluidics: Mathematical Modeling and Empirical Analysis of the Burst Frequencies of a Novel Fishbone Capillary Valve and the Development of an Algorithm to Calculate its Theoretical Hold Time",
        "kbosuedudspacebitstream181164441smelkerhonorsthesis.pdf": "Generating Uniform Sub-micron Solid Particles for Laser-based Flow Diagnostics",
        "krexkstateedudspacebitstream209711353EricMoore2009.pdf": "The Weak Link in the Language Teaching System and What to Do About It",
        "mazonevscvirginiaeduthesisDusterhoff2001.pdf": "Controls on Near-Surface Soil Moisture Dynamics within a Tidal Marsh-Forested Upland Coastal Environment",
        "oarwichitaedudspacebitstream100576761t06133.pdf": "Response of Adhesively Bonded Composite Joints to Low Velocity Impact",
        "ofccfsnrcangccabookstorepdfs26570.pdf": "Public Participation in Forest Management: Results from a National Survey of Advisory Committees",
        "researchwsulibswsuedu8443jspuibitstream23762781cosorio121304.pdf": "Development of Transgenic Barley Expressing Human Type I Collagen",
        "rexkstateedudspacebitstream209713581NozomiMatsumiya2009.pdf": "Optimization of Disulfide Mapping Using Mass Spectrometry",
        "rexkstateedudspacebitstream20979011JamesYoung2008.pdf": "United States Air Force Defense Suppression Doctrine, 1968-1972",
        "upcommonsupcedupfcbitstream2099165981Master20Thesis20Final.pdf": "Modeling the Molecular Communication Nanonetworks",
        "wweconiastateeduresearchwebpaperspaper1716.pdf": "Stochastic Dynamic Northern Corn Rootworm Population Model",
        "wwggrhulacukict4dworkingpapersMitra1.pdf": "The hole in the wall",
        "wwnlpriaaccn2008papersgjkwgk6.pdf": "Occlusion Reasoning for Tracking Multiple People",
        "wwefkautmmythesisimages4MASTER20062JSBPPart1ONGBOONTHAIMA041170d06ttt.pdf": "Personal Digital Assistants as a Mobile Inspection System at Construction Site",
        "cholarspacemanoahawaiiedubitstream10125118782uhmma3256r.pdf": "Reliability and Validity Evidence for the Dual-Disorder Treatment Fidelity Scale",
        "emocguedutwcgmj2602260206.pdf": "Penile Tumescence Assessment Used for a Diagnosis of Paraphilia: A Pedophilia Case Report",
        "scholarspacemanoahawaiiedubitstream1012568662uhmphd4352r.pdf": "Abundance and Distribution Patterns of Hawaiian Odontocetes: Focus on O'ahu",
        "sppsdpwgscgccacollection2008electionsSE3702007E.pdf": "The Electoral Participation of Persons with Special Needs",
        "wb4unleduDissKotcherlakotaSK.pdf": "A Test of Strategies for Enhanced Learing of Descriptive Chemistry",
        "ww2silorgsilesr2002silesr2002041.pdf": "Sociolinguistic Survey of the Safaliba Language Area",
        "wwcfaarizonaeduherpTurner20200720438.pdf": "Amphibians and Reptiles of Sonoita Creek State Natural Area, Arizona",
        "wwcisupennedugraddocumentszhaoliming.pdf": "Constructing Good Quality Motion Graphs for Realistic Human Animation",
        "wwcmdhbgovtnzAboutCMDHBPlanningHealthStatusAsianHealthAsianHealthNeedsAssessment.pdf": "Health Needs Assessment for Asian People in Counties Manukau",
        "wwcolorlabnocontentdownload21981216266fileDamienLeflochMasterthesis.pdf": "Real-Time People Counting system using Video Camera",
        "wwcsbrowneduresearchpubsthesesmasters1991boyer.pdf": "An Operating System Development Environment",
        "wwcsubccalabsimagerth2006GluckMScThesisGluckMScThesis.pdf": "An Investigation of the Effects of Matching Attentional Draw with Utility in Computer-Based Interruption",
        "wweconiastateeduresearchwebpaperspaper1716.pdf": "Stochastic Dynamic Northern Corn Rootworm Population Model",
        "wwetsorgMediaResearchpdfRR0113Sheehan.pdf": "An Inquiry into the Nature of the Sentence-Completion Task: Implications for Item Generation",
        "wwgeomtueduramanpapers2Rahn.pdf": "Cultural Assessment of Reforestation Practices in Rural Eastern Paraguay",
        "wwifhdeILCdonethesesthesisrd.pdf": "Investigation of a Crystal Calorimeter Technology with longitudinal Segmentation",
        "wwlancsacukusersphilosophyawaymaveonlineresourcesfrances20robinson.pdf": "The Relevance of Chaos to Environmental Ethics",
        "wwmolbiolcellorgcgireprintE06100895v1.pdf": "The localization of INCENP at the cleavage furrow is dependent on Kif12 and involves interactions of the N-terminus of INCENP with the actin cytoskeleton",
        "wworegongovODOTTDTPRESdocsReports2008BentCapsReportPart1.pdf": "Evaluation of Bent Caps in Reinforced Concrete Deck Girder Bridges, Part 1",
        "wwpotomacriverorgpotomacdwsppMeetingsJul222009WeidnerReport.pdf": "Potomac Watershed Priority Lands Strategy: Conserving lands to benefit drinking water quality",
        "wwpsiepsuedupublicationsreportspsieePSIE200302Lynchetal.pdf": "Mercury Deposition in Pennsylvania: Status Report",
        "wwsagesacukhomehomesrgroveswoodpub3.pdf": "Palaeoecology of a Post-Extinction Reef: Famennian (Late Devonian) of the Canning Basin, North-Western Australia",
        "wwsaissemthprize2007luo2007.pdf": "Incremental learning for Adaptive Visual Place Recognition in Dynamic Indoor Environments",
        "wwtalkbankorgmediaPDFJOCPDF3Lebaron2020Jones.pdf": "Closing Up Closings: Showing the Relevance of the Social and Material Surround to the Completion of Interaction",
        "wwwmisesorgjournalsraepdfrae824.pdf": "Ethics, Efficiency, Coasian Property Rights, and Psychic Income: A Reply to Demsetz",
        "xtensionusuedufilespublicationspublicationpub4078090.pdf": "Greater Sage-Grouse Ecology and Response to Natural Gas Development in Northeastern Utah",
        "xtensionusuedufilespublicationspublicationpub8111133.pdf": "The Effects of Mechanical Disking on Shrub Steppe Ecosystems and Greater Sage Grouse Use in Pine Valley, Utah",
        "hqlibdocwhointbulletin2001issue4794365372.pdf": "Laying ethical foundations for clinical research",
        "jsbsgmjournalsorgcgireprint471132.pdf": "Genome Organization of Pseudomonas stutzeri and Resulting Taxonomic and Evolutionary Considerations",
        "mcihmcuscmc2006paperscmc2006p99.pdf": "La construcción de mapas conceptuales en edad preescolar",
        "rchivenumdamorgARCHIVEAIFAIF1971212AIF1971212850AIF1971212850.pdf": "Résolution d'équations aux dérivées partielles dans des espaces de distributions d'ordre de régularité variable",
        "rchivenumdamorgARCHIVEAIFAIF1976261AIF1976261810AIF1976261810.pdf": "Propagation des singularités analytiques pour les solutions des équations aux dérivées partielles",
        "rchivenumdamorgARCHIVEAIFAIF1997472AIF19974724850AIF19974724850.pdf": "Ordre, convergence et sommabilité de produits de séries de Dirichlet",
        "reinunicaitcornelisRICERCAPAPERS167.pdf": "Mathematical principles in photonic crystals",
        "scholarspacemanoahawaiiedubitstream1012570212uhmms3818r.pdf": "Hormone Analyses of Black-Footed Albatross (Phoebastria nigripes) at Midway Atoll NWR and Tern Island, Hawaiian Islands NWR",
        "wwccpooduedutezerPAPERS2005AGUGOM.pdf": "Loop Current, Rings and Related Circulation in the Gulf of Mexico: A Review of Numerical Models and Future Challenges",
        "wwepagovwaterstmdldocs35148cranecreekfecal.pdf": "Fecal Coliform TMDL for Crane Creek, WBIDs 3085 and 3085A",
        "wwerjersjournalscomcgireprint123612.pdf": "Neutrophils induce damage to respiratory epithelial cells infected with respiratory syncytial virus",
        "wwindiaenvironmentportalorginfilesoilpalmsoutheastasia.pdf": "The impacts and opportunities of oil palm in Southeast Asia: What do we know and what do we need to know?",
        "wwmathtauacildaliafSISC1990vortex.pdf": "Vortex Methods for Slightly Viscous Three-Dimensional Flow",
        "wwnzesorgnznzjenewissuesNZJEcol33297.pdf": "Distribution, pup production and mortality of New Zealand sea lion (Phocarctos hookeri) on Campbell Island / Motu Ihupuku, 2008",
        "wwoecdorgdataoecd395240554221.pdf": "Optimising Learning: Implications of Learning Sciences Research",
        "wwsilsiedusmithsoniancontributionsBotanypdfhisctb0047.pdf": "Polynesian Plant Studies 6-18",
        "wwsjrwmdcomtechnicalreportspdfsSPSJ2002SP3.pdf": "Snail Kite Nesting Activity in the Blue Cypress Marshes During the 2000 and 2001 Breeding Seasons",
        "wwwclevelandfedorgourregioncommunitydevelopmenteventsseminars20080425finlitloiblreducedpaper.pdf": "Survey of Financial Education in Ohio's High Schools: Assessment of Teachers, Programs, and Legislative Efforts",
        "xplorationgrcnasagovAdvancedISSResearchInvestigationsFLEXdocumentsFLEXEIRDv4.pdf": "Droplet Flame Extinguishment in Microgravity (FLEX)",
        "wwetsorgMediaResearchpdfRR8616Kingston.pdf": "Alternative Methods of Equating the GRE General Test",
        "wwfaupceswebsfafluidsmarquespdfCSRFaMoIr96.pdf": "Bed-flow instability of the longshore current",
    }
    authors = {
        "aoscoloradoedudcnSWINGworkshopsSWS1Kelley.pdf": ["Maxwell Kelley"],
        "cpsumneduassetspdf17baretheoryquantummeas20copy.pdf": ["Jeffrey Bub", "Rob Clifton", "Bradley Monton"],
        "hesislibrarycaltechedu20521heidelthesis.pdf": ["Jeremy David Heidel"],
        "upcommonsupcedupfcbitstream2099165981Master20Thesis20Final.pdf": ["Neus Roca Lacasa"],
        "wweconiastateeduresearchwebpaperspaper1716.pdf": ["Paul D. Mitchell", "Walter Riedell"],
        "wwefkautmmythesisimages4MASTER20062JSBPPart1ONGBOONTHAIMA041170d06ttt.pdf": ["Ong Boon Thai"],
        "emocguedutwcgmj2602260206.pdf": ["Ker-Li Hsueh", "Ching-Kuan Wu", "Chi-Fa Hung", "Chun-Chien Hsu", "Jung-Kwang Wen"],
        "wb4unleduDissKotcherlakotaSK.pdf": ["Suhasini Kotcherlakota"],
        "ww2silorgsilesr2002silesr2002041.pdf": ["Angela Kluge", "Deborah H. Hatfield"],
        "wwcfaarizonaeduherpTurner20200720438.pdf": ["Dale S. Turner"],
        "wwcisupennedugraddocumentszhaoliming.pdf": ["Liming Zhao"],
        "wwcmdhbgovtnzAboutCMDHBPlanningHealthStatusAsianHealthAsianHealthNeedsAssessment.pdf": ["Geeta Gala"],
        "wwcolorlabnocontentdownload21981216266fileDamienLeflochMasterthesis.pdf": ["Damien Lefloch"],
        "wwcsbrowneduresearchpubsthesesmasters1991boyer.pdf": ["Robert Boyer"],
        "wwgeomtueduramanpapers2Rahn.pdf": ["Kristen E. Rahn"],
        "wwifhdeILCdonethesesthesisrd.pdf": ["Ralph Dollan"],
        "wwlancsacukusersphilosophyawaymaveonlineresourcesfrances20robinson.pdf": ["Frances M C Robinson"],
        "wwpotomacriverorgpotomacdwsppMeetingsJul222009WeidnerReport.pdf": ["Emily Weidner"],
        "wwsaissemthprize2007luo2007.pdf": ["Jie Luo"],
        "wwwmisesorgjournalsraepdfrae824.pdf": ["Walter Block"],
        "wwccpooduedutezerPAPERS2005AGUGOM.pdf": ["L.-Y. Oey", "T. Ezer", "H.-C. Lee"],
        "wwoecdorgdataoecd395240554221.pdf": ["R. Keith Sawyer"],
        "wwsjrwmdcomtechnicalreportspdfsSPSJ2002SP3.pdf": ["Zachariah C. Welch", "Wiley M. Kitchens"],
        "rchivenumdamorgARCHIVEAIFAIF1976261AIF1976261810AIF1976261810.pdf": ["Jean-Michel Bony", "Pierre Schapira"],
        "scholarspacemanoahawaiiedubitstream1012570212uhmms3818r.pdf": ["Kater Alisha Bourdon"],
        "wwetsorgMediaResearchpdfRR8616Kingston.pdf": ["Neal M. Kingston", "Paul W. Holland"],
    }
    scanned = "wwefkautmmythesisimages4MASTER20062JSBPPart1ONGBOONTHAIMA041170d06ttt.pdf"
    visually_verified = {
        scanned,
        "rchivenumdamorgARCHIVEAIFAIF1976261AIF1976261810AIF1976261810.pdf",
        "scholarspacemanoahawaiiedubitstream1012570212uhmms3818r.pdf",
        "wwetsorgMediaResearchpdfRR8616Kingston.pdf",
        "wwfaupceswebsfafluidsmarquespdfCSRFaMoIr96.pdf",
    }
    title_corrections = {
        "rchivenumdamorgARCHIVEAIFAIF1976261AIF1976261810AIF1976261810.pdf": (
            "Propagation des singularités analytiques pour les solutions d'équations aux dérivées partielles",
            "Propagation des singularités analytiques pour les solutions des équations aux dérivées partielles",
        ),
    }
    abstract_sources = {
        "ewsoaorglibrarymonographs50thanniversarysocietyofactuaries50thanniversary1999januarymav99107.pdf",
        "krexkstateedudspacebitstream20971451NibeditaDas2006B.pdf",
        "wwccpooduedutezerPAPERS2005AGUGOM.pdf",
        "wwifhdeILCdonethesesthesisrd.pdf",
        "wwlevyorgpubswp149.pdf",
        "wwmpifgdepumpifgdpdp014.pdf",
        "wwpsiepsuedupublicationsreportspsieePSIE200302Lynchetal.pdf",
    }
    months = {name.lower(): number for number, name in enumerate((
        "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"
    ), 1)}
    records = [json.loads(line) for line in input_path.open(encoding="utf-8")]
    changed = []
    for record in records:
        name = record["source_file"]
        actions = {}
        pdf_text = None

        def first_two_pages() -> str:
            nonlocal pdf_text
            if pdf_text is None:
                pdf = source_pdf(record, pdf_root)
                result = subprocess.run(["pdftotext", "-f", "1", "-l", "2", str(pdf), "-"], capture_output=True, check=True)
                pdf_text = " ".join(result.stdout.decode("utf-8", "replace").split())
            return pdf_text

        def normalized(value: str) -> str:
            return re.sub(r"[^\w]+", " ", value.casefold()).strip()

        if name in title_corrections and record["title"] == title_corrections[name][0]:
            record["title"] = title_corrections[name][1]
            actions["title"] = {"value": record["title"], "evidence": "PDF first-page image manually viewed; corrected preposition"}
        if not record["title"] and name in titles:
            value = titles[name]
            if name in visually_verified or normalized(value) in normalized(first_two_pages()):
                record["title"] = value
                actions["title"] = {"value": value, "evidence": "PDF first-page image manually viewed" if name in visually_verified else "PDF first two pages"}
        if not record["authors"] and name in authors:
            values = authors[name]
            if name in visually_verified or all(normalized(value) in normalized(first_two_pages()) for value in values):
                record["authors"] = values
                actions["authors"] = {"value": values, "evidence": "PDF first-page image manually viewed" if name in visually_verified else "PDF first two pages"}
        if name == scanned:
            if not record["affiliation"]:
                record["affiliation"] = ["Universiti Teknologi Malaysia"]
                actions["affiliation"] = {"value": record["affiliation"], "evidence": "scanned PDF first-page image"}
            if not record["address"]:
                record["address"] = ["No. 18, Solok Semilang, Seberang Jaya, 13700 Prai, Pulau Pinang"]
                actions["address"] = {"value": record["address"], "evidence": "scanned PDF first-page image"}
        if not record["date"] and name in published:
            phrase = published[name]
            match = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})", phrase, re.I)
            if match and phrase.casefold() in first_two_pages().casefold():
                value = calendar_date(int(match.group(3)), months[match.group(1).lower()], int(match.group(2))).isoformat()
                record["date"] = value
                record["year"] = int(value[:4])
                actions["date"] = {"value": value, "evidence": phrase}
                actions["year"] = {"value": record["year"], "evidence": phrase}
        if not record["abstract"] and name in abstract_sources:
            paragraphs = record["fulltext"].split("\n\n")
            heading = next((item for item in evidence["confirmed_pdf_evidence"]["abstract_headings"] if item["source_file"] == name), None)
            if heading and paragraphs and len(paragraphs[0]) >= 100:
                record["abstract"] = paragraphs[0]
                record["fulltext"] = "\n\n".join(paragraphs[1:])
                actions["abstract"] = {"value": record["abstract"], "evidence": "PDF abstract heading and matching first TEI body paragraph"}
        for field in actions:
            record["errors"] = [error for error in record["errors"] if error != f"missing: {field}"]
        record["parse_status"] = "partial" if record["errors"] else "success"
        if actions:
            changed.append({"source_file": name, "changes": actions})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        if in_place:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=output_path.parent, prefix="supplement_", suffix=".tmp", delete=False) as output:
                temporary = Path(output.name)
                for record in records:
                    output.write(json.dumps(record, ensure_ascii=False) + "\n")
            temporary.replace(output_path)
        else:
            with output_path.open("w", encoding="utf-8", newline="\n") as output:
                for record in records:
                    output.write(json.dumps(record, ensure_ascii=False) + "\n")
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    report = {"records": len(records), "changed_records": len(changed), "changes_by_field": {
        field: sum(field in change["changes"] for change in changed)
        for field in ("title", "authors", "date", "year", "affiliation", "address", "abstract")
    }, "changes": changed}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "changes"}, ensure_ascii=False))


def main() -> None:
    """Write a new JSONL and a manifest of removed duplicate source records."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--pdf-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--fill-pages", type=Path, help="Update pages in this JSONL in place")
    parser.add_argument("--remove-source", help="Remove one source_file from --input in place")
    parser.add_argument("--repair-reviewed", action="store_true", help="Apply reviewed PDF corrections to --input in place")
    parser.add_argument("--repair-pdf-anomalies", action="store_true", help="Apply PDF-evidenced anomaly corrections to --input in place")
    parser.add_argument("--repair-followup-pdf", action="store_true", help="Apply later cover-page verified metadata corrections in place")
    parser.add_argument("--recover-missing", action="store_true", help="Recover verified missing fields into a new JSONL")
    parser.add_argument("--xml-root", type=Path, help="GROBID XML directory for recovery")
    parser.add_argument("--supplement-confirmed", action="store_true", help="Add reviewed PDF values into a new JSONL")
    parser.add_argument("--evidence", type=Path, help="PDF evidence report for confirmed supplementation")
    args = parser.parse_args()
    if args.repair_followup_pdf:
        if not (args.input and args.pdf_root):
            parser.error("--repair-followup-pdf requires --input and --pdf-root")
        repair_followup_pdf_evidence(args.input, args.pdf_root)
        return
    if args.repair_pdf_anomalies:
        if not (args.input and args.pdf_root):
            parser.error("--repair-pdf-anomalies requires --input and --pdf-root")
        repair_verified_pdf_anomalies(args.input, args.pdf_root)
        return
    if args.supplement_confirmed:
        if not (args.input and args.output and args.report and args.pdf_root and args.evidence):
            parser.error("supplementation requires --input, --output, --report, --pdf-root and --evidence")
        supplement_confirmed(args.input, args.output, args.pdf_root, args.evidence, args.report)
        return
    if args.recover_missing:
        if not (args.input and args.output and args.report and args.xml_root and args.pdf_root):
            parser.error("recovery requires --input, --output, --report, --xml-root and --pdf-root")
        recover_missing_fields(args.input, args.output, args.xml_root, args.pdf_root, args.report)
        return
    if args.repair_reviewed:
        if not args.input:
            parser.error("--input is required with --repair-reviewed")
        repair_reviewed_records(args.input)
        return
    if args.remove_source:
        if not args.input:
            parser.error("--input is required with --remove-source")
        remove_source(args.input, args.remove_source)
        return
    if args.fill_pages:
        if not args.pdf_root:
            parser.error("--pdf-root is required with --fill-pages")
        fill_pages(args.fill_pages, args.pdf_root)
        return
    if not (args.input and args.output and args.report and args.pdf_root):
        parser.error("--input, --output, --report and --pdf-root are required for deduplication")
    started = time.perf_counter()
    if args.output.resolve() == args.input.resolve():
        parser.error("output must differ from input")
    records: list[dict] = []
    groups: dict[str, list[int]] = defaultdict(list)
    pdf_hash_cache: dict[Path, str] = {}
    with args.input.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            record = json.loads(line)
            pdf = source_pdf(record, args.pdf_root)
            if pdf not in pdf_hash_cache:
                pdf_hash_cache[pdf] = file_hash(pdf)
            groups[pdf_hash_cache[pdf]].append(len(records))
            records.append(record)

    kept = set()
    duplicate_groups = []
    for digest, indexes in groups.items():
        selected = max(indexes, key=lambda index: quality(records[index]))
        kept.add(selected)
        if len(indexes) > 1:
            duplicate_groups.append({
                "pdf_sha256": digest,
                "kept_source_file": records[selected]["source_file"],
                "kept_paper_id": records[selected]["paper_id"],
                "removed": [
                    {"source_file": records[index]["source_file"], "paper_id": records[index]["paper_id"]}
                    for index in indexes if index != selected
                ],
            })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as output:
        for index, record in enumerate(records):
            if index in kept:
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
    report = {
        "input_records": len(records),
        "output_records": len(kept),
        "duplicate_groups": len(duplicate_groups),
        "removed_duplicate_records": len(records) - len(kept),
        "selection_rule": "most nonempty fields, then fewer errors, then longer body, then source filename",
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "groups": duplicate_groups,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "groups"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
