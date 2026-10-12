"""`python -m apix ...` is the same as `apix ...`; VS Code's launch configuration uses it."""

import sys

from apix.cli import main

sys.exit(main())
