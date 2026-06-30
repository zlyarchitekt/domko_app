import sys

sys.path.insert(0, r'.venv\Lib\site-packages')
import pytest

sys.exit(pytest.main(["tests/test_footprint.py", "tests/test_bsp.py", "tests/test_layout.py", "-v"]))
