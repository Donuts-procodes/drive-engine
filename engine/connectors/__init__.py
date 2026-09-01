from .base import BaseConnector, SourceType, LinkPreflightResult
import pkgutil
import importlib
from pathlib import Path

# Dynamically discover and import all connectors in this package
# This triggers __init_subclass__ in BaseConnector which registers them.
package_dir = Path(__file__).resolve().parent
for (_, module_name, is_pkg) in pkgutil.iter_modules([str(package_dir)]):
    try:
        if is_pkg:
            # If it's a folder, try to import the package
            importlib.import_module(f".{module_name}", __name__)
            # Also discover files inside that sub-package
            sub_dir = package_dir / module_name
            for (_, sub_mod, sub_is_pkg) in pkgutil.iter_modules([str(sub_dir)]):
                if not sub_is_pkg:
                    importlib.import_module(f".{module_name}.{sub_mod}", __name__)
        else:
            # If it's a file, import it directly
            importlib.import_module(f".{module_name}", __name__)
    except Exception as e:
        print(f"Warning: Failed to load connector plugin '{module_name}': {e}")

def get_connector_for_url(url: str) -> BaseConnector:
    connectors = BaseConnector.get_registered_connectors()
    for cls in connectors:
        connector_instance = cls()
        if connector_instance.matches(url):
            return connector_instance
    
    # Fallback if it doesn't match known patterns but might be an ID.
    from .gdrive.google_drive import GoogleDriveConnector
    return GoogleDriveConnector()

__all__ = ["get_connector_for_url", "BaseConnector", "SourceType", "LinkPreflightResult"]
