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


_VALID_CLASSES = {
    "monoclonal_antibody", "bispecific_antibody", "antibody_drug_conjugate",
    "peptide", "small_molecule", "mrna", "sirna", "antisense_oligonucleotide",
    "gene_therapy", "cell_therapy", "vaccine", "enzyme_replacement",
    "fusion_protein", "radiopharmaceutical", "biosimilar", "other",
}

_CLAUDE_BATCH_SYSTEM = _CLAUDE_SYSTEM + """

When classifying a NUMBERED LIST of drugs, return ONE class per line in
the same order. Format: "<n>: <class>". Nothing else. Example:

1: small_molecule
2: monoclonal_antibody
3: peptide
"""


async def _classify_batch_with_claude(
    drugs: list[tuple[str, str | None]]
) -> list[str | None]:
    """Classify many drugs in one Claude call. ~10× speedup over the
    per-drug variant. Returns a list of class names (or None for failures)
    aligned with the input list."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key or not drugs:
        return [None] * len(drugs)
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        return [None] * len(drugs)

    client = AsyncAnthropic(api_key=key)

    # Build a numbered prompt
    lines = []
    for i, (name, mech) in enumerate(drugs, start=1):
        line = f"{i}. {name}"
        if mech:
            line += f"  | mechanism: {mech[:120]}"
        lines.append(line)
    user_msg = "Classify each drug. Respond with one line per drug as '<n>: <class>'.\n\n" + "\n".join(lines)

    try:
        msg = await client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=40 * len(drugs),  # ~40 tokens per response line
            system=[{"type": "text", "text": _CLAUDE_BATCH_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_msg}],
        )
    except Exception as e:
        err = str(e)
        if "credit balance is too low" in err:
            raise RuntimeError("CREDITS_EXHAUSTED") from e
        logger.warning(f"Claude batch class failed (size={len(drugs)}): {e}")
        return [None] * len(drugs)

    blocks = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
    raw = "".join(blocks).strip()

    # Parse "<n>: <class>" lines
    out: list[str | None] = [None] * len(drugs)
    for ln in raw.splitlines():
        m = re.match(r"\s*(\d+)\s*[:.\-)]\s*([a-z_]+)\b", ln, re.IGNORECASE)
        if not m:
            continue
        idx = int(m.group(1)) - 1
        cls = m.group(2).strip().lower()
        if 0 <= idx < len(drugs) and cls in _VALID_CLASSES:
            out[idx] = cls
    return out


async def _classify_with_claude(drug_name: str, mechanism: str | None) -> str | None:
    """Single-drug shim for callers that want it. Internally just delegates
    to the batch path with a list of one."""
    results = await _classify_batch_with_claude([(drug_name, mechanism)])
    return results[0]


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

        # Phase 1: walk all rows, apply free Tier 1 + Tier 2 rules. Anything
        # that doesn't match falls into a "needs_claude" queue we process in
        # batches below.
        needs_claude: list[tuple[str, str, str, str | None]] = []  # (drug_id, name, generic, mechanism)

        for row in rows:
            drug_id, drug_name, generic_name, mechanism = row
            cls: str | None = _tag_by_inn_suffix(drug_name, generic_name)
            source: str | None = "inn_suffix" if cls else None
            if not cls:
                cls = _tag_by_keyword(drug_name, mechanism)
                if cls:
                    source = "keyword"

            if cls:
                # Write the class immediately for fast-path drugs.
                try:
                    async with db.begin_nested():
                        await db.execute(
                            text("UPDATE drugs SET drug_class=:c, drug_class_source=:s WHERE drug_id=:id"),
                            {"c": cls, "s": source, "id": drug_id},
                        )
                    tagged += 1
                    by_source[source] = by_source.get(source, 0) + 1
                except Exception as e:
                    logger.warning(f"  fast-path drug={drug_id}: {e}")
            else:
                needs_claude.append((drug_id, drug_name, generic_name or "", mechanism))

        await db.commit()
        logger.info(f"  fast path done: {tagged} tagged, {len(needs_claude)} need Claude")

        # Phase 2: batch the remainder through Claude. Batch size 20 keeps
        # the prompt + response under 1k tokens combined; pace 4s between
        # batches to stay under Tier-1 30k input tokens/min.
        BATCH = 20
        for i in range(0, len(needs_claude), BATCH):
            if claude_quota_exhausted:
                break
            chunk = needs_claude[i : i + BATCH]
            try:
                results = await _classify_batch_with_claude(
                    [(d[1], d[3]) for d in chunk]
                )
            except RuntimeError:
                claude_quota_exhausted = True
                logger.warning("drug_class_tagger: Claude credits exhausted")
                break

            for (drug_id, name, _, _), cls in zip(chunk, results):
                if cls:
                    try:
                        async with db.begin_nested():
                            await db.execute(
                                text("UPDATE drugs SET drug_class=:c, drug_class_source='claude' WHERE drug_id=:id"),
                                {"c": cls, "id": drug_id},
                            )
                        tagged += 1
                        by_source["claude"] = by_source.get("claude", 0) + 1
                    except Exception as e:
                        logger.warning(f"  claude-path drug={drug_id}: {e}")

            await db.commit()
            logger.info(f"  batch {i // BATCH + 1}/{len(needs_claude) // BATCH + 1}: {tagged} total")
            # 4 second pacing between batches
            await asyncio.sleep(4)

        # Anything still un-tagged (Claude returned nothing OR credits ran
        # out) gets a placeholder so we don't re-try them next run.
        leftover = (await db.execute(
            text(
                "SELECT drug_id FROM drugs "
                "WHERE drug_class IS NULL "
                "  AND drug_id = ANY(:ids)"
            ),
            {"ids": [d[0] for d in needs_claude]},
        )).fetchall()
        for (drug_id,) in leftover:
            try:
                async with db.begin_nested():
                    await db.execute(
                        text("UPDATE drugs SET drug_class='other', drug_class_source='skipped' WHERE drug_id=:id"),
                        {"id": drug_id},
                    )
                by_source["skipped"] = by_source.get("skipped", 0) + 1
                tagged += 1
            except Exception:
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
