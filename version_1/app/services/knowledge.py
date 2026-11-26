"""Allowlisted, versioned reference material indexed for every project.

These are concise internal summaries for retrieval, not copies of RBI material
and not legal advice. Source applicability must be confirmed by an authorised
compliance reviewer for the relevant regulated entity and product.
"""
from __future__ import annotations

from app.services.documents import chunk_text


RBI_KNOWLEDGE_SOURCES = (
    {
        "id": "KB-RBI-KYC-2024",
        "name": "Approved RBI knowledge — KYC Directions",
        "authority": "Reserve Bank of India",
        "jurisdiction": "India",
        "effective_date": "2016-02-25",
        "version": "Updated 2024-11-06",
        "source_url": "https://www.rbi.org.in/commonman/Upload/English/Notification/PDFs/MD18KYCF6E92C82E1E1419D87323E3869BC9F13.pdf",
        "text": (
            "Approved reference summary: Reserve Bank of India Know Your Customer (KYC) Directions, 2016, "
            "updated 6 November 2024. For applicable regulated entities, assess customer due diligence, identity "
            "verification, KYC record handling, Central KYC Records Registry obligations where applicable, and review "
            "or audit evidence. Confirm regulated-entity scope, product applicability, retention obligations, and the "
            "current direction with authorised compliance or legal reviewers before baselining requirements."
        ),
    },
    {
        "id": "KB-RBI-ITG-2023",
        "name": "Approved RBI knowledge — IT Governance Directions",
        "authority": "Reserve Bank of India",
        "jurisdiction": "India",
        "effective_date": "2024-04-01",
        "version": "Directions issued 2023-11-07",
        "source_url": "https://systemhealth.rbi.org.in/Scripts/BS_ViewMasDirections.aspx_id%3D12562%283%29.html",
        "text": (
            "Approved reference summary: RBI Information Technology Governance, Risk, Controls and Assurance Practices "
            "Directions, 2023, effective 1 April 2024. For applicable regulated entities, analyse IT governance, risk "
            "management, assurance, access controls, audit evidence, incident management, business continuity and disaster "
            "recovery. Confirm the entity's scope and materiality classification with authorised compliance and security owners."
        ),
    },
    {
        "id": "KB-RBI-DPSC-2021",
        "name": "Approved RBI knowledge — Digital Payment Security Controls",
        "authority": "Reserve Bank of India",
        "jurisdiction": "India",
        "effective_date": "2021-02-18",
        "version": "Master Direction 2021",
        "source_url": "https://systemhealth.rbi.org.in/Scripts/BS_ViewMasDirections.aspx_id%3D12032%283%29.html",
        "text": (
            "Approved reference summary: RBI Master Direction on Digital Payment Security Controls, 2021. For payment "
            "workflows, assess strong authentication, fraud-risk management, secure application lifecycle, transaction "
            "reconciliation, logging, incident handling and relevant security testing. Confirm whether this direction or a "
            "more specific RBI direction applies to the regulated entity, payment channel, and third parties."
        ),
    },
)


def approved_documents() -> list[dict]:
    """Return immutable project-indexable documents from the source allowlist."""
    documents = []
    for source in RBI_KNOWLEDGE_SOURCES:
        document = {key: value for key, value in source.items() if key != "text"}
        document["chunks"] = [chunk.__dict__ for chunk in chunk_text(source["text"])]
        documents.append(document)
    return documents
