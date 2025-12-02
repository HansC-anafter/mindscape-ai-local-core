"""
Capability Packager

Tool for creating .mindpack files from capability packages.
Used by developers to package capabilities for distribution.
"""
import zipfile
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class CapabilityPackager:
    """Package capability directories into .mindpack files"""

    def __init__(self, capabilities_dir: Optional[Path] = None):
        """
        Initialize packager

        Args:
            capabilities_dir: Base capabilities directory (default: app/capabilities)
        """
        if capabilities_dir is None:
            app_dir = Path(__file__).parent.parent
            capabilities_dir = app_dir / "capabilities"

        self.capabilities_dir = Path(capabilities_dir)

    def package(
        self,
        capability_code: str,
        output_path: Optional[Path] = None,
        version: Optional[str] = None
    ) -> Path:
        """
        Package a capability into .mindpack file

        Args:
            capability_code: Capability code (directory name)
            output_path: Output file path (default: {capability_code}_{version}.mindpack)
            version: Version override (default: from manifest.yaml)

        Returns:
            Path to created .mindpack file
        """
        capability_dir = self.capabilities_dir / capability_code

        if not capability_dir.exists():
            raise ValueError(f"Capability directory not found: {capability_dir}")

        manifest_path = capability_dir / "manifest.yaml"
        if not manifest_path.exists():
            raise ValueError(f"Manifest not found: {manifest_path}")

        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = yaml.safe_load(f)

        pack_id = manifest.get('id') or manifest.get('code', capability_code)
        pack_version = version or manifest.get('version', '1.0.0')

        if output_path is None:
            output_path = Path(f"{pack_id}_{pack_version}.mindpack")

        output_path = Path(output_path)

        logger.info(f"Packaging {capability_code} (id: {pack_id}, version: {pack_version})")

        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in self._get_files_to_package(capability_dir):
                arcname = f"capability/{file_path.relative_to(capability_dir)}"
                zipf.write(file_path, arcname)
                logger.debug(f"Added: {arcname}")

        logger.info(f"Created package: {output_path}")
        return output_path

    def _get_files_to_package(self, capability_dir: Path) -> List[Path]:
        """
        Get list of files to include in package

        Excludes:
        - __pycache__
        - .pyc files
        - .git
        - .DS_Store
        """
        files = []

        for file_path in capability_dir.rglob('*'):
            if file_path.is_file():
                relative = file_path.relative_to(capability_dir)

                if any(part.startswith('.') or part == '__pycache__' for part in relative.parts):
                    continue

                if file_path.suffix in ['.pyc', '.pyo']:
                    continue

                files.append(file_path)

        return sorted(files)

    def validate_package(self, package_path: Path) -> Dict[str, Any]:
        """
        Validate a .mindpack file

        Returns:
            Dict with validation results
        """
        errors = []
        warnings = []

        if not package_path.exists():
            errors.append(f"Package file not found: {package_path}")
            return {"valid": False, "errors": errors, "warnings": warnings}

        if not package_path.suffix == '.mindpack':
            warnings.append(f"File extension is not .mindpack: {package_path.suffix}")

        try:
            with zipfile.ZipFile(package_path, 'r') as zipf:
                namelist = zipf.namelist()

                if not any('manifest.yaml' in name for name in namelist):
                    errors.append("manifest.yaml not found in package")

                manifest_path = next((n for n in namelist if n.endswith('manifest.yaml')), None)
                if manifest_path:
                    with zipf.open(manifest_path) as f:
                        manifest = yaml.safe_load(f)

                    required_fields = ['id', 'version', 'requires_core']
                    for field in required_fields:
                        if field not in manifest:
                            errors.append(f"Missing required field in manifest: {field}")

                    if 'id' in manifest:
                        pack_id = manifest['id']
                        if not pack_id.startswith('mindscape.') and not pack_id.startswith('user.'):
                            warnings.append(f"Package ID '{pack_id}' should use namespacing (mindscape.* or user.*)")

        except zipfile.BadZipFile:
            errors.append("Invalid ZIP file")
        except Exception as e:
            errors.append(f"Validation error: {str(e)}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }


def package_capability(
    capability_code: str,
    output_path: Optional[Path] = None,
    capabilities_dir: Optional[Path] = None,
    version: Optional[str] = None
) -> Path:
    """
    Convenience function to package a capability

    Args:
        capability_code: Capability code
        output_path: Output file path
        capabilities_dir: Base capabilities directory
        version: Version override

    Returns:
        Path to created .mindpack file
    """
    packager = CapabilityPackager(capabilities_dir)
    return packager.package(capability_code, output_path, version)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python capability_packager.py <capability_code> [output_path] [version]")
        sys.exit(1)

    capability_code = sys.argv[1]
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    version = sys.argv[3] if len(sys.argv) > 3 else None

    try:
        result = package_capability(capability_code, output_path, version=version)
        print(f"✅ Created package: {result}")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
