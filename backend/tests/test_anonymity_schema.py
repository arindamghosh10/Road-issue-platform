"""Guards the core/vault split at the schema level (no database needed).

If one of these fails, someone has put personal data into the core DB or linked the two
databases — which is an architecture change that must be discussed first (brief §16).
"""

import re

from app.models.core import CoreBase
from app.models.vault import VaultBase

PII_PATTERN = re.compile(r"phone|aadhaar|aadhar|identity|email_citizen|name_citizen|address|dob")
# Officials are government staff, not citizens; their email/name are expected.
ALLOWED = {("officials", "email"), ("officials", "name")}


def test_core_and_vault_use_separate_metadata():
    assert CoreBase.metadata is not VaultBase.metadata
    assert not set(CoreBase.metadata.tables) & set(VaultBase.metadata.tables)


def test_core_has_no_personal_data_columns():
    offenders = [
        (table.name, column.name)
        for table in CoreBase.metadata.sorted_tables
        for column in table.columns
        if PII_PATTERN.search(column.name) and (table.name, column.name) not in ALLOWED
    ]
    assert offenders == []


def test_core_has_no_foreign_keys_into_vault():
    vault_tables = set(VaultBase.metadata.tables)
    for table in CoreBase.metadata.sorted_tables:
        for fk in table.foreign_keys:
            assert fk.column.table.name not in vault_tables


def test_vault_is_the_only_place_linking_reporter_to_identity():
    link = VaultBase.metadata.tables["reporter_links"]
    assert {"identity_id", "reporter_id"} <= set(link.columns.keys())
