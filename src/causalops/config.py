from pathlib import Path
import os

def workspace_root()->Path:
    """Explicit user workspace; launchers set this before importing the UI."""
    return Path(os.environ.get('CAUSALOPS_HOME',str(Path.cwd()/'causalops-workspace'))).expanduser().resolve()