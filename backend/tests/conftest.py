import os

# Unit tests run without real secrets; config falls back to dev-only keys in "test".
os.environ.setdefault("APP_ENV", "test")
