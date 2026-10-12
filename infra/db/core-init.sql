-- Runs once, when the core-db volume is first created.
-- A separate database for automated tests, so `pytest` can never wipe dev data.
CREATE DATABASE roadwatch_core_test;
