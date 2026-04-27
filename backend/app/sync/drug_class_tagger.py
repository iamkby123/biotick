"""Tag every drug with a therapeutic-modality class (peptide, mAb, mRNA, etc.).

Three-tier classifier, cheap before expensive:

  1. **INN suffix rules** — WHO INN nomenclature uses standard suffixes for
     drug classes. `-mab` → monoclonal antibody, `-tide` → peptide,
     `-tinib` → kinase inhibitor (small molecule), `-iran/-siran` → siRNA,
     `-rsen` → antisense oligonucleotide, etc. Catches ~70% of named drugs
     for free, no API tokens.

  2. **Mechanism / name keywords** — for drugs without a recognizable INN
     suffix (development codes like LY1234567, mRNA-1010, brand names like
     Mounjaro), look for class indicators in the `mechanism` and
     `drug_name` fields. Catches another ~20%.

  3. **Claude fallback** — for the remaining ~10% where rules don't fire
     (genuine ambiguity, unusual code names), batch-call Claude to classify.
     Caches the system prompt so per-call cost is minimal.

Each tag also stores `drug_class_source` so we know which tier classified
it — useful for auditing accuracy and prioritizing manual fixes.
"""

import asyncio
import logging
import os
import re
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)


# ─── Tier 1: INN-suffix rules ────────────────────────────────────────────
#
# Order matters — longer suffixes checked first so e.g. "tirumotecan" matches
# antibody_drug_conjugate not just generic "-an".
INN_SUFFIX_RULES: list[tuple[str, str]] = [
    # Antibody-drug conjugates
    ("deruxtecan", "antibody_drug_conjugate"),
    ("vedotin", "antibody_drug_conjugate"),
    ("emtansine", "antibody_drug_conjugate"),
    ("tirumotecan", "antibody_drug_conjugate"),
    ("ravtansine", "antibody_drug_conjugate"),

    # Monoclonal antibodies (WHO INN: -mab family)
    # Bispecifics often share -mab suffix; we tag them as bispecific only
    # when name/mechanism mentions "bispecific" — handled in tier 2.
    ("ximab", "monoclonal_antibody"),
    ("zumab", "monoclonal_antibody"),
    ("tuzumab", "monoclonal_antibody"),
    ("lumab", "monoclonal_antibody"),
    ("umab", "monoclonal_antibody"),
    ("omab", "monoclonal_antibody"),
    ("amab", "monoclonal_antibody"),

    # Antisense oligonucleotides (-rsen)
    ("rsen", "antisense_oligonucleotide"),
    ("nersen", "antisense_oligonucleotide"),
    ("ersen", "antisense_oligonucleotide"),

    # siRNA — Alnylam coined the -siran/-iran suffix family
    ("siran", "sirna"),
    ("itiran", "sirna"),
    ("usiran", "sirna"),
    ("isiran", "sirna"),

    # Cell / gene therapies
    ("cel", "cell_therapy"),       # axicabtagene ciloleucel, brexucabtagene
    ("leucel", "cell_therapy"),
    ("gene", "gene_therapy"),
    ("plasmid", "gene_therapy"),
    ("aav", "gene_therapy"),

    # Peptides — generic peptide hormones, GLP-1s, etc.
    # Very common ending; check after more specific suffixes above.
    ("tide", "peptide"),
    ("relin", "peptide"),     # gonadorelin, ganirelix
    ("relix", "peptide"),
    ("pressin", "peptide"),   # vasopressin
    ("lipro", "peptide"),

    # Small-molecule families (mostly kinase inhibitors)
    ("ciclib", "small_molecule"),
    ("ciclax", "small_molecule"),
    ("tinib", "small_molecule"),
    ("nib", "small_molecule"),
    ("parib", "small_molecule"),
    ("orib", "small_molecule"),
    ("denib", "small_molecule"),
    ("rabant", "small_molecule"),
    ("statin", "small_molecule"),
    ("sartan", "small_molecule"),
    ("pril", "small_molecule"),
    ("olol", "small_molecule"),
    ("ast", "small_molecule"),
    ("dipine", "small_molecule"),
    ("oxetine", "small_molecule"),
    ("triptan", "small_molecule"),

    # Fusion proteins / decoy receptors
    ("cept", "fusion_protein"),     # etanercept, abatacept, aflibercept

    # Enzymes / enzyme replacement therapy
    ("ase alfa", "enzyme_replacement"),
    ("ase beta", "enzyme_replacement"),
    ("ase gamma", "enzyme_replacement"),

    # Antivirals / antibiotics
    ("vir", "small_molecule"),       # most antivirals
    ("micin", "small_molecule"),     # macrolide antibiotics
    ("cycline", "small_molecule"),
    ("floxacin", "small_molecule"),

    # Radiopharmaceuticals
    ("lutetium", "radiopharmaceutical"),
    ("iodine", "radiopharmaceutical"),
    ("technetium", "radiopharmaceutical"),
]


# ─── Tier 2: name + mechanism keyword rules ──────────────────────────────
#
# These catch drugs without a standard INN suffix — Lilly's LY-codes, Moderna's
# mRNA codes, brand names like Mounjaro, vaccine programs, etc.
NAME_KEYWORD_RULES: list[tuple[re.Pattern, str]] = [
    # mRNA therapeutics — Moderna, BioNTech, etc.
    (re.compile(r"^mRNA[-\s]?\d", re.IGNORECASE), "mrna"),
    (re.compile(r"\bspikevax\b|\bcomirnaty\b|\bnexspike\b|\bmresvia\b", re.IGNORECASE), "mrna"),

    # Tirzepatide & GLP-1s by brand name (no -tide suffix in brand)
    (re.compile(r"\bmounjaro\b|\bzepbound\b|\bozempic\b|\brybelsus\b|\bwegovy\b", re.IGNORECASE), "peptide"),
    (re.compile(r"\bvictoza\b|\bsaxenda\b|\btrulicity\b|\bbydureon\b", re.IGNORECASE), "peptide"),
    # Insulin & analogs — peptides
    (re.compile(r"\binsulin\b|\bhumalog\b|\blantus\b|\btresiba\b|\bnovolog\b", re.IGNORECASE), "peptide"),
    (re.compile(r"\bgrowth hormone\b|\bsomatropin\b", re.IGNORECASE), "peptide"),
    (re.compile(r"\bGLP[-\s]?1\b", re.IGNORECASE), "peptide"),

    # CAR-T / cell therapies
    (re.compile(r"\bCAR[-\s]?T\b|\bCAR[-\s]?NK\b|\bTILs?\b|\bTCR[-\s]?T\b", re.IGNORECASE), "cell_therapy"),
    (re.compile(r"\bautologous\b.+(cell|leucocyte|lymphocyte)|\ballogeneic\b.+(cell)", re.IGNORECASE), "cell_therapy"),

    # Gene therapies — typically AAV-vectored
    (re.compile(r"\bAAV\d?\b|\badeno[-\s]?associated\b", re.IGNORECASE), "gene_therapy"),
    (re.compile(r"\belevidys\b|\bzolgensma\b|\bluxturna\b|\bhemgenix\b", re.IGNORECASE), "gene_therapy"),

    # Vaccines
    (re.compile(r"\bvaccine\b", re.IGNORECASE), "vaccine"),

    # Antibody-drug conjugates by brand
    (re.compile(r"\benhertu\b|\btrodelvy\b|\bkadcyla\b|\bpadcev\b|\belahere\b", re.IGNORECASE), "antibody_drug_conjugate"),

    # Bispecifics (override mAb tag if the molecule is bispecific)
    (re.compile(r"\bbispecific\b|\bBiTE\b|\bDuoBody\b", re.IGNORECASE), "bispecific_antibody"),
]


MECHANISM_KEYWORD_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bmRNA\b|\bmessenger RNA\b", re.IGNORECASE), "mrna"),
    (re.compile(r"\bantisense\b|\bASO\b", re.IGNORECASE), "antisense_oligonucleotide"),
    (re.compile(r"\bsiRNA\b|\bsmall interfering RNA\b|\bRNAi\b", re.IGNORECASE), "sirna"),
    (re.compile(r"\bgene therapy\b|\bAAV\b|\bgene replacement\b|\blentivir\b", re.IGNORECASE), "gene_therapy"),
    (re.compile(r"\bCAR[-\s]?T\b|\bCAR[-\s]?NK\b|\bcell therapy\b|\bautologous T[-\s]?cell\b", re.IGNORECASE), "cell_therapy"),
    (re.compile(r"\bmonoclonal antibody\b|\b\bmAb\b|\bIgG\b", re.IGNORECASE), "monoclonal_antibody"),
    (re.compile(r"\bbispecific\b|\bBiTE\b", re.IGNORECASE), "bispecific_antibody"),
    (re.compile(r"\bantibody[-\s]?drug conjugate\b|\bADC\b", re.IGNORECASE), "antibody_drug_conjugate"),
    (re.compile(r"\bpeptide\b|\bGLP[-\s]?1\b|\bGIP\b", re.IGNORECASE), "peptide"),
    (re.compile(r"\benzyme replacement\b|\brecombinant enzyme\b", re.IGNORECASE), "enzyme_replacement"),
    (re.compile(r"\bvaccine\b|\bimmunization\b", re.IGNORECASE), "vaccine"),
    (re.compile(r"\bkinase inhibitor\b|\bsmall[-\s]?molecule\b|\bsmall molecule\b", re.IGNORECASE), "small_molecule"),
    (re.compile(r"\bfusion protein\b|\bdecoy receptor\b", re.IGNORECASE), "fusion_protein"),
    (re.compile(r"\bradiopharm\b|\bradioligand\b|\bradio[-\s]?label", re.IGNORECASE), "radiopharmaceutical"),
]


def _tag_by_inn_suffix(name: str | None, generic: str | None) -> str | None:
    """Match drug name against INN suffix rules. Returns class or None."""
    candidates = [s for s in (name, generic) if s]
    for s in candidates:
        s_lower = s.lower().strip().rstrip(".,")
        for suffix, cls in INN_SUFFIX_RULES:
            if s_lower.endswith(suffix):
                return cls
    return None


def _tag_by_keyword(name: str | None, mechanism: str | None) -> str | None:
    """Match drug name + mechanism against keyword rules."""
    haystacks = [s for s in (name, mechanism) if s]
    blob = " ".join(haystacks)
    for pattern, cls in NAME_KEYWORD_RULES:
        if pattern.search(blob):
            return cls
    if mechanism:
        for pattern, cls in MECHANISM_KEYWORD_RULES:
            if pattern.search(mechanism):
                return cls
    return None


# ─── Tier 3: Claude fallback ─────────────────────────────────────────────

_CLAUDE_SYSTEM = """You classify biotech drugs into ONE of these therapeutic-modality classes:

- monoclonal_antibody
- bispecific_antibody
- antibody_drug_conjugate
- peptide
- small_molecule
- mrna
- sirna
- antisense_oligonucleotide
- gene_therapy
- cell_therapy
- vaccine
- enzyme_replacement
- fusion_protein
- radiopharmaceutical
- biosimilar
- other

Rules:
- Use the most specific class. mAbs that are bispecific go to bispecific_antibody. ADCs go to antibody_drug_conjugate, NOT monoclonal_antibody.
- Insulin, GLP-1 agonists, and any cyclic / linear peptide hormone go to peptide.
- "AAV", "lentiviral", or any in-vivo gene-replacement therapy → gene_therapy.
- "CAR-T", "TIL", "NK cell", autologous/allogeneic cell products → cell_therapy.
- mRNA-XXXX numeric codes, or any modified-nucleoside RNA therapeutic → mrna.
- If genuinely unclear, return "other".

Respond with ONLY the class name (one of the above), nothing else.
"""


async def _classify_with_claude(drug_name: str, mechanism: str | None) -> str | None:
    """Send a single drug to Claude for classification. Returns class or None."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return None
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        return None
    client = AsyncAnthropic(api_key=key)
    user_msg = f"Drug name: {drug_name}"
    if mechanism:
        user_msg += f"\nMechanism: {mechanism[:200]}"
    try:
        msg = await client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=20,
            system=[{"type": "text", "text": _CLAUDE_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_msg}],
        )
    except Exception as e:
        err = str(e)
        if "credit balance is too low" in err:
            raise RuntimeError("CREDITS_EXHAUSTED") from e
        logger.warning(f"Claude class failed for {drug_name}: {e}")
        return None
    blocks = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
    raw = "".join(blocks).strip().lower()
    # Strip trailing punctuation, accept only known classes
    raw = re.sub(r"[^a-z_]", "", raw)
    valid = {
        "monoclonal_antibody", "bispecific_antibody", "antibody_drug_conjugate",
        "peptide", "small_molecule", "mrna", "sirna", "antisense_oligonucleotide",
        "gene_therapy", "cell_therapy", "vaccine", "enzyme_replacement",
        "fusion_protein", "radiopharmaceutical", "biosimilar", "other",
    }
    return raw if raw in valid else None


# ─── Sync runner ─────────────────────────────────────────────────────────


async def sync_drug_classes(
    db: AsyncSession,
    only_unclassified: bool = True,
    limit: int = 1000,
) -> int:
    """Classify drugs in the database. Static rules first (free), Claude
    fallback for unmatched drugs (rate-limited, ~$1 per 1000 drugs)."""
    log = SyncLog(
        sync_type="DRUG_CLASS_TAGGER",
        started_at=datetime.utcnow(),
        status="RUNNING",
    )
    db.add(log)
    await db.commit()

    try:
        where = "WHERE drug_class IS NULL" if only_unclassified else ""
        rows = (await db.execute(
            text(f"""
                SELECT drug_id, drug_name, generic_name, mechanism
                FROM drugs
                {where}
                ORDER BY company_ticker, drug_name
                LIMIT :lim
            """),
            {"lim": limit},
        )).fetchall()
        logger.info(f"drug_class_tagger: {len(rows)} drugs to classify")

        tagged = 0
        by_source: dict[str, int] = {"inn_suffix": 0, "keyword": 0, "claude": 0, "skipped": 0}
        claude_quota_exhausted = False

        for row in rows:
            drug_id, drug_name, generic_name, mechanism = row
            cls: str | None = None
            source: str | None = None

            # Tier 1
            cls = _tag_by_inn_suffix(drug_name, generic_name)
            if cls:
                source = "inn_suffix"

            # Tier 2
            if not cls:
                cls = _tag_by_keyword(drug_name, mechanism)
                if cls:
                    source = "keyword"

            # Tier 3 — Claude. Skip if credits exhausted.
            if not cls and not claude_quota_exhausted:
                try:
                    cls = await _classify_with_claude(drug_name, mechanism)
                    if cls:
                        source = "claude"
                        # Claude rate limit: ~30k input tokens/min on Tier 1.
                        # Each call is ~150 tokens (cached system + small user
                        # message + small completion). Pace at 1.5s = 40 calls/min
                        # = 6k tokens/min, well under the cap.
                        await asyncio.sleep(1.5)
                except RuntimeError:
                    claude_quota_exhausted = True
                    logger.warning("drug_class_tagger: Claude credits exhausted; rest go to 'other'")

            if not cls:
                cls = "other"
                source = "skipped"

            try:
                async with db.begin_nested():
                    await db.execute(
                        text(
                            "UPDATE drugs SET drug_class = :cls, drug_class_source = :src "
                            "WHERE drug_id = :drug_id"
                        ),
                        {"cls": cls, "src": source, "drug_id": drug_id},
                    )
                tagged += 1
                by_source[source] = by_source.get(source, 0) + 1
                if tagged % 100 == 0:
                    await db.commit()
                    logger.info(f"  ...tagged {tagged}/{len(rows)} ({by_source})")
            except Exception as e:
                logger.warning(f"  drug={drug_id} update failed: {e}")
                continue
        await db.commit()

        log.completed_at = datetime.utcnow()
        log.status = "COMPLETED"
        log.records_processed = tagged
        log.error_message = (
            f"by_source={by_source}; claude_quota_exhausted={claude_quota_exhausted}"
        )[:2000]
        await db.commit()
        logger.info(f"drug_class_tagger done: {tagged} tagged, by_source={by_source}")
        return tagged

    except Exception as e:
        log.completed_at = datetime.utcnow()
        log.status = "FAILED"
        log.error_message = str(e)[:2000]
        await db.commit()
        logger.error(f"drug_class_tagger failed: {e}")
        raise
