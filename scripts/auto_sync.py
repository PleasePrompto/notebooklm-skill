#!/usr/bin/env python3
"""
NotebookLM Auto-Sync: End-to-End Automation
Syncs local files to Google Drive and automatically adds them to NotebookLM notebooks

Usage:
    python auto_sync.py --config sync-config.json
    python auto_sync.py --local ~/docs --drive "MyFolder" --notebook-url "https://..."
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))


class NotebookLMAutoSync:
    """End-to-end automation for NotebookLM document synchronization"""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.config = self._load_config() if config_path else {}
        self.scripts_dir = Path(__file__).parent
        self.data_dir = self.scripts_dir.parent / "data"
        self.sync_state_file = self.data_dir / "sync_state.json"
        self.sync_state = self._load_sync_state()

    def _load_config(self) -> Dict:
        """Load sync configuration"""
        config_file = Path(self.config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(config_file, 'r') as f:
            return json.load(f)

    def _load_sync_state(self) -> Dict:
        """Load sync state to track what's been synced"""
        if self.sync_state_file.exists():
            with open(self.sync_state_file, 'r') as f:
                return json.load(f)
        return {"synced_files": {}, "last_sync": None}

    def _save_sync_state(self):
        """Save sync state"""
        self.sync_state["last_sync"] = datetime.now().isoformat()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with open(self.sync_state_file, 'w') as f:
            json.dump(self.sync_state, f, indent=2, ensure_ascii=False)

    def _get_local_files(self, local_path: str) -> List[Dict]:
        """Get list of local files to sync"""
        path = Path(local_path).expanduser()
        if not path.exists():
            print(f"  ⚠️ Path not found: {local_path}")
            return []

        extensions = self.config.get("settings", {}).get(
            "supported_extensions", [".md", ".pdf", ".txt", ".docx"]
        )
        exclude = self.config.get("settings", {}).get(
            "exclude_patterns", ["node_modules", ".git", ".obsidian", ".DS_Store"]
        )

        files = []
        for f in path.iterdir():
            if f.is_file():
                # Check extension
                if f.suffix.lower() not in extensions:
                    continue
                # Check exclude patterns
                if any(ex in f.name for ex in exclude):
                    continue

                files.append({
                    "name": f.name,
                    "path": str(f),
                    "size": f.stat().st_size,
                    "modified": f.stat().st_mtime
                })

        return files

    def _sync_to_drive(self, local_path: str, drive_folder: str) -> Dict:
        """Sync local files to Google Drive using Node.js script"""
        print(f"\n📤 Syncing to Google Drive: {local_path} → {drive_folder}")

        node_script = self.scripts_dir / "sync-to-drive.js"
        if not node_script.exists():
            raise FileNotFoundError(f"sync-to-drive.js not found at {node_script}")

        # Run the Node.js sync script
        result = subprocess.run(
            ["node", str(node_script), "--local", local_path, "--drive", drive_folder],
            capture_output=True,
            text=True,
            cwd=str(self.scripts_dir)
        )

        if result.returncode != 0:
            print(f"  ❌ Drive sync failed: {result.stderr}")
            return {"status": "error", "error": result.stderr}

        print(result.stdout)
        return {"status": "success", "output": result.stdout}

    def _add_to_notebook(self, notebook_url: str, drive_folder: str, new_files: List[str] = None) -> Dict:
        """Add files from Drive to NotebookLM notebook"""
        if not notebook_url:
            print("  ⏭️ No notebook URL configured, skipping NotebookLM integration")
            return {"status": "skipped", "reason": "no_notebook_url"}

        print(f"\n📚 Adding sources to NotebookLM...")

        # Import and use the add_sources module
        from add_sources import SourceAdder

        try:
            with SourceAdder(headless=True) as adder:
                result = adder.add_sources_from_drive(
                    notebook_url=notebook_url,
                    drive_folder=drive_folder,
                    file_names=new_files
                )
            return result
        except Exception as e:
            print(f"  ❌ NotebookLM integration failed: {e}")
            return {"status": "error", "error": str(e)}

    def sync_mapping(self, mapping: Dict) -> Dict:
        """Sync a single mapping configuration"""
        name = mapping.get("name", "Unknown")
        local_path = mapping.get("local_path", "").replace("~", os.environ["HOME"])
        drive_folder = mapping.get("drive_folder", "")
        notebook_url = mapping.get("notebook_url", "")
        enabled = mapping.get("enabled", True)

        if not enabled:
            return {"status": "disabled", "name": name}

        print(f"\n{'='*60}")
        print(f"📂 Processing: {name}")
        print(f"{'='*60}")

        # Get local files
        local_files = self._get_local_files(local_path)
        if not local_files:
            print(f"  📭 No files to sync in {local_path}")
            return {"status": "no_files", "name": name}

        print(f"  📄 Found {len(local_files)} local files")

        # Check for new/modified files
        folder_state = self.sync_state["synced_files"].get(drive_folder, {})
        new_files = []
        for f in local_files:
            prev_modified = folder_state.get(f["name"], {}).get("modified", 0)
            if f["modified"] > prev_modified:
                new_files.append(f["name"])

        if not new_files:
            print(f"  ✅ All files already synced")
            return {"status": "up_to_date", "name": name}

        print(f"  🆕 {len(new_files)} new/modified files: {', '.join(new_files[:5])}...")

        # Step 1: Sync to Google Drive
        drive_result = self._sync_to_drive(local_path, drive_folder)
        if drive_result.get("status") != "success":
            return {"status": "drive_sync_failed", "name": name, "error": drive_result.get("error")}

        # Step 2: Add to NotebookLM (if configured)
        notebook_result = self._add_to_notebook(notebook_url, drive_folder, new_files)

        # Update sync state
        if drive_folder not in self.sync_state["synced_files"]:
            self.sync_state["synced_files"][drive_folder] = {}

        for f in local_files:
            self.sync_state["synced_files"][drive_folder][f["name"]] = {
                "modified": f["modified"],
                "size": f["size"],
                "synced_at": datetime.now().isoformat()
            }

        self._save_sync_state()

        return {
            "status": "success",
            "name": name,
            "files_synced": len(new_files),
            "drive_result": drive_result,
            "notebook_result": notebook_result
        }

    def run_all(self) -> Dict:
        """Run sync for all enabled mappings"""
        if not self.config:
            raise ValueError("No configuration loaded")

        mappings = self.config.get("sync_mappings", [])
        results = []

        print("\n🚀 NotebookLM Auto-Sync Starting...")
        print(f"📋 Processing {len(mappings)} mappings")

        for mapping in mappings:
            result = self.sync_mapping(mapping)
            results.append(result)

        # Summary
        success_count = sum(1 for r in results if r.get("status") == "success")
        print(f"\n{'='*60}")
        print(f"📊 Sync Complete: {success_count}/{len(results)} successful")
        print(f"{'='*60}")

        return {
            "status": "complete",
            "total": len(results),
            "successful": success_count,
            "results": results
        }

    def run_single(self, local_path: str, drive_folder: str, notebook_url: str = None) -> Dict:
        """Run sync for a single path (command-line mode)"""
        mapping = {
            "name": Path(local_path).name,
            "local_path": local_path,
            "drive_folder": drive_folder,
            "notebook_url": notebook_url or "",
            "enabled": True
        }
        return self.sync_mapping(mapping)


def main():
    parser = argparse.ArgumentParser(
        description='NotebookLM Auto-Sync: Sync local files to Google Drive and NotebookLM'
    )
    parser.add_argument('--config', help='Path to sync configuration file')
    parser.add_argument('--local', help='Local folder path')
    parser.add_argument('--drive', help='Google Drive folder path')
    parser.add_argument('--notebook-url', help='NotebookLM notebook URL')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be synced')

    args = parser.parse_args()

    if args.config:
        # Config-based sync
        syncer = NotebookLMAutoSync(config_path=args.config)
        result = syncer.run_all()
    elif args.local and args.drive:
        # Single folder sync
        syncer = NotebookLMAutoSync()
        result = syncer.run_single(
            local_path=args.local,
            drive_folder=args.drive,
            notebook_url=args.notebook_url
        )
    else:
        parser.print_help()
        print("\n📖 Examples:")
        print("  python auto_sync.py --config ../sync-config.json")
        print("  python auto_sync.py --local ~/docs --drive 'MyFolder' --notebook-url 'https://...'")
        return 1

    print(f"\n📋 Final Result: {json.dumps(result, indent=2, ensure_ascii=False)}")
    return 0 if result.get("status") in ["success", "complete", "up_to_date"] else 1


if __name__ == "__main__":
    sys.exit(main())
