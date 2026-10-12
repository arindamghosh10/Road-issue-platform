-- Runs once, when the vault-db volume is first created.
-- A separate database for automated tests, so `pytest` can never wipe dev data.
CREATE DATABASE roadwatch_vault_test;
