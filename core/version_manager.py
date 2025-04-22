import os
import json
import hashlib
import logging
from datetime import datetime
import pytz
from typing import Dict, Any, Optional, List, Tuple

# Import our standardized time functions
from utils.time_utils import get_formatted_time, get_current_username

class VersionManager:
    """Manages file versioning and history."""

    def __init__(self, backup_folder="backups", settings_manager=None):
        self.backup_folder = backup_folder
        self.settings_manager = settings_manager
        os.makedirs(backup_folder, exist_ok=True)
        # Store tracked files in the same directory as the script for simplicity, adjust if needed
        self.tracked_files_path = os.path.join(os.getcwd(), "tracked_files.json")
        print(f"VersionManager using tracked files path: {self.tracked_files_path}") # Debug print

    def calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA-256 hash of file contents."""
        try:
            # Use a larger chunk size for potentially better performance on large files
            hasher = hashlib.sha256()
            with open(file_path, 'rb') as file:
                while chunk := file.read(8192): # Read in 8KB chunks
                    hasher.update(chunk)
            return hasher.hexdigest()
        except FileNotFoundError:
             self._log_error(f"File not found when calculating hash: {file_path}")
             raise # Re-raise after logging
        except Exception as e:
            self._log_error(f"Failed to calculate file hash for {file_path}: {str(e)}")
            raise # Re-raise after logging

    def has_file_changed(self, file_path: str, tracked_files: Dict[str, Any]) -> Tuple[bool, str, str]:
        """
        Check if file has changed from its last tracked ACTIVE version.
        Returns (has_changed, current_hash, last_active_hash)
        """
        try:
            current_hash = self.calculate_file_hash(file_path)
            normalized_path = os.path.normpath(file_path)

            if normalized_path not in tracked_files:
                return True, current_hash, "" # No history, so it's "changed" from nothing

            versions = tracked_files[normalized_path].get("versions", {})
            if not versions:
                return True, current_hash, "" # No versions tracked

            # Get only active versions
            active_versions = [
                (hash_id, info) for hash_id, info in versions.items()
                if not info.get("deleted", False)
            ]

            if not active_versions:
                 return True, current_hash, "" # No active versions exist

            # Sort active versions by timestamp (newest first)
            latest_active_version = sorted(
                active_versions,
                key=lambda x: datetime.strptime(x[1]["timestamp"], "%Y-%m-%d %H:%M:%S"),
                reverse=True
            )[0]

            last_active_hash = latest_active_version[0]
            return current_hash != last_active_hash, current_hash, last_active_hash

        except Exception as e:
            self._log_error(f"Failed to check file changes for {file_path}: {str(e)}")
            # Return a default state indicating change check failed but providing current hash
            return True, self.calculate_file_hash(file_path) if os.path.exists(file_path) else "", ""


    def load_tracked_files(self) -> Dict[str, Any]:
        """Load tracked files from JSON."""
        try:
            with open(self.tracked_files_path, "r", encoding='utf-8') as file:
                return json.load(file)
        except FileNotFoundError:
            print(f"Tracked files JSON not found at {self.tracked_files_path}, starting fresh.") # Info message
            return {}
        except json.JSONDecodeError:
            self._log_error(f"Error: tracked_files.json at {self.tracked_files_path} is corrupted. BACKING UP and starting fresh.")
            # Optional: Backup corrupted file
            try:
                corrupted_backup_path = self.tracked_files_path + ".corrupted_" + get_formatted_time(use_utc=True).replace(":", "-")
                os.rename(self.tracked_files_path, corrupted_backup_path)
                print(f"Backed up corrupted file to: {corrupted_backup_path}")
            except Exception as backup_e:
                 self._log_error(f"Failed to backup corrupted tracked_files.json: {backup_e}")
            return {}
        except Exception as e:
             self._log_error(f"Unexpected error loading {self.tracked_files_path}: {e}")
             return {} # Return empty dict on other errors

    def save_tracked_files(self, tracked_files: Dict[str, Any]) -> None:
        """Save tracked files to JSON with proper formatting."""
        try:
            # Use a temporary file and rename for atomicity
            temp_path = self.tracked_files_path + ".tmp"
            with open(temp_path, "w", encoding='utf-8') as file:
                json.dump(tracked_files, file, indent=4, ensure_ascii=False)
            # Atomic rename (replaces the original file)
            os.replace(temp_path, self.tracked_files_path)
        except Exception as e:
            self._log_error(f"Failed to save tracked files to {self.tracked_files_path}: {str(e)}")
            # Attempt to remove temp file if it exists
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception as rm_e:
                     self._log_error(f"Failed to remove temporary save file {temp_path}: {rm_e}")
            raise # Re-raise exception after logging

    def add_version(self, file_path: str, version_hash: str, metadata: Dict[str, Any], commit_message: str = "") -> List[str]:
        """
        Add a new version to the tracked file and enforce backup limits by marking old versions deleted.

        Args:
            file_path: Path to the file.
            version_hash: Hash of the file content for this version.
            metadata: Additional metadata about the version (e.g., size, modification time).
            commit_message: Optional commit message provided by the user.

        Returns:
            List[str]: A list of version hashes that were marked as deleted in the metadata
                       and whose corresponding physical backup files should now be removed.
                       Returns an empty list if no versions needed deletion or on error.
        """
        hashes_to_delete = []
        try:
            current_time_utc = get_formatted_time(use_utc=True) # Consistent UTC time
            username = get_current_username()

            tracked_files = self.load_tracked_files()
            normalized_path = os.path.normpath(file_path)

            # --- Ensure File Entry Exists ---
            if normalized_path not in tracked_files:
                tracked_files[normalized_path] = {
                    "versions": {},
                    "last_updated": current_time_utc # Initialize last_updated
                }
            # Ensure 'versions' key exists even if file entry was already there
            if "versions" not in tracked_files[normalized_path]:
                 tracked_files[normalized_path]["versions"] = {}

            # --- Add or Update Version Info ---
            # Check if this exact hash already exists
            existing_version_info = tracked_files[normalized_path]["versions"].get(version_hash)

            if existing_version_info:
                 # If it exists, update timestamp, username, commit message, and ensure deleted=False
                 existing_version_info["timestamp"] = current_time_utc
                 existing_version_info["username"] = username
                 # Only update commit message if a new one is provided
                 if commit_message:
                      existing_version_info["commit_message"] = commit_message
                 existing_version_info["metadata"] = metadata # Update metadata too
                 existing_version_info["deleted"] = False # Crucially, mark as active again if re-added
                 print(f"[{current_time_utc}] [{username}] Updated existing version {version_hash} for {normalized_path}")
            else:
                 # Add as a completely new version
                 tracked_files[normalized_path]["versions"][version_hash] = {
                    "timestamp": current_time_utc,
                    "metadata": metadata,
                    "username": username,
                    "commit_message": commit_message,
                    "deleted": False # Start as active
                 }
                 print(f"[{current_time_utc}] [{username}] Added new version {version_hash} for {normalized_path}")

            # Update the top-level last_updated timestamp for the file entry
            tracked_files[normalized_path]["last_updated"] = current_time_utc

            # --- Save BEFORE Enforcing Limit ---
            # This ensures the newly added/updated version is considered when checking the limit
            self.save_tracked_files(tracked_files)

            # --- Enforce Limit ---
            # Call _enforce_backup_limit which will load the fresh data, mark excess as deleted,
            # save again, and return the hashes that were marked.
            hashes_to_delete = self._enforce_backup_limit(normalized_path)

            return hashes_to_delete

        except Exception as e:
            self._log_error(f"Failed to add version for {file_path} (hash: {version_hash}): {str(e)}")
            return [] # Return empty list on error

    def _enforce_backup_limit(self, file_path: str) -> List[str]:
        """
        PRIVATE: Enforces the max_backups limit by marking the oldest *active*
        versions as 'deleted: True' in the tracked_files metadata.

        Args:
            file_path: The normalized path to the file whose versions need checking.

        Returns:
            List[str]: A list of version hashes that were newly marked as deleted during this call.
                       Returns an empty list if no changes were needed or on error.
        """
        hashes_marked_deleted = []
        try:
            # --- Get Max Backups Setting ---
            max_backups = 3 # Sensible default
            if self.settings_manager:
                try:
                    # Always get the fresh value from settings manager
                    max_backups_setting = self.settings_manager.settings.get("max_backups", 3)
                    max_backups = int(max_backups_setting)
                    if max_backups <= 0:
                         print(f"Warning: max_backups setting is {max_backups}. Using default of 3.")
                         max_backups = 3 # Ensure it's at least 1, maybe default higher
                except (ValueError, TypeError):
                     print(f"Warning: Invalid max_backups setting ('{max_backups_setting}'). Using default of 3.")
                     max_backups = 3
            else:
                 print("Warning: SettingsManager not available in VersionManager. Using default max_backups=3.")


            current_time_utc = get_formatted_time(use_utc=True)
            username = get_current_username()
            print(f"[{current_time_utc}] [{username}] Enforcing backup limit (max_backups={max_backups}) for {file_path}")

            # --- Load Fresh Data ---
            # Load again to ensure we have the absolute latest state after add_version saved.
            tracked_files = self.load_tracked_files()
            normalized_path = os.path.normpath(file_path) # Should already be normalized, but belt-and-suspenders

            if normalized_path not in tracked_files or "versions" not in tracked_files[normalized_path]:
                print(f"No versions found for {normalized_path} during limit enforcement.")
                return [] # Nothing to enforce

            versions = tracked_files[normalized_path]["versions"]
            if not versions:
                return [] # No versions

            # --- Identify and Sort Active Versions ---
            active_versions = []
            for hash_id, info in versions.items():
                if not info.get("deleted", False):
                     # Ensure timestamp exists and is valid before trying to parse
                     ts_str = info.get("timestamp")
                     if ts_str:
                         try:
                             # Validate timestamp format before adding
                             ts_dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                             active_versions.append((hash_id, info, ts_dt))
                         except ValueError:
                              self._log_error(f"Invalid timestamp format '{ts_str}' for version {hash_id} of {normalized_path}. Skipping in sort.")
                     else:
                          self._log_error(f"Missing timestamp for active version {hash_id} of {normalized_path}. Skipping in sort.")


            if not active_versions:
                 print(f"No *active* versions found for {normalized_path} to enforce limit.")
                 return []


            # Sort by the datetime object (newest first)
            active_versions.sort(key=lambda x: x[2], reverse=True)

            # --- Check Limit and Mark Excess as Deleted ---
            if len(active_versions) <= max_backups:
                print(f"Active versions ({len(active_versions)}) within limit ({max_backups}). No changes needed.")
                return [] # Limit not exceeded

            # Determine which versions to mark as deleted (the oldest ones beyond the limit)
            versions_to_mark_deleted = active_versions[max_backups:]
            modified_metadata = False # Flag to track if we actually change anything

            for version_hash, info, _ in versions_to_mark_deleted:
                # Check if it's *already* marked deleted in the main 'versions' dict (safety check)
                if not versions[version_hash].get("deleted", False):
                    versions[version_hash]["deleted"] = True
                    hashes_marked_deleted.append(version_hash)
                    modified_metadata = True
                    print(f"[{current_time_utc}] [{username}] Marked version {version_hash} as deleted (limit {max_backups})")

            # --- Save ONLY if Changes Were Made ---
            if modified_metadata:
                # Update the main dictionary
                tracked_files[normalized_path]["versions"] = versions
                # Update last_updated timestamp since metadata changed
                tracked_files[normalized_path]["last_updated"] = current_time_utc
                self.save_tracked_files(tracked_files)
                print(f"Saved metadata after marking {len(hashes_marked_deleted)} version(s) as deleted.")
            else:
                 print("No versions needed marking as deleted.")


            return hashes_marked_deleted

        except Exception as e:
            self._log_error(f"Failed to enforce backup limit for {file_path}: {str(e)}")
            return [] # Return empty list on error


    def get_file_metadata(self, file_path: str) -> Dict[str, Any]:
        """Get current file metadata (size, modification time, type)."""
        try:
            # Basic file stats
            stat = os.stat(file_path)
            file_ext = os.path.splitext(file_path)[1].lower()

            # Get modification times in both local and UTC
            mtime_local = datetime.fromtimestamp(stat.st_mtime)
            mtime_utc = datetime.utcfromtimestamp(stat.st_mtime)

            return {
                "size": stat.st_size,
                "modification_time": {
                    "local": mtime_local.strftime("%Y-%m-%d %H:%M:%S %Z"), # Include timezone info if possible
                    "utc": mtime_utc.strftime("%Y-%m-%d %H:%M:%S")
                },
                "file_type": file_ext
                # Consider adding creation time if needed:
                # "creation_time_utc": datetime.utcfromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
            }
        except FileNotFoundError:
             # Don't log error here, calling code should handle non-existent file if needed
             return {}
        except Exception as e:
            self._log_error(f"Failed to get file metadata for {file_path}: {str(e)}")
            return {} # Return empty dict on error

    def get_active_file_versions(self, file_path: str) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Get a list of non-deleted versions for a file, sorted newest first.
        This should be used by the Restore Page UI.
        """
        try:
            tracked_files = self.load_tracked_files()
            normalized_path = os.path.normpath(file_path)

            if normalized_path not in tracked_files:
                return [] # File not tracked

            versions = tracked_files[normalized_path].get("versions", {})
            if not versions:
                return [] # File tracked, but no versions

            # Filter out deleted versions and validate timestamp
            active_versions_with_dt = []
            for hash_id, info in versions.items():
                if not info.get("deleted", False):
                    ts_str = info.get("timestamp")
                    if ts_str:
                        try:
                            ts_dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                            active_versions_with_dt.append((hash_id, info, ts_dt))
                        except ValueError:
                             self._log_error(f"Skipping version {hash_id} for {normalized_path} due to invalid timestamp '{ts_str}' in get_active_file_versions.")
                    else:
                        self._log_error(f"Skipping version {hash_id} for {normalized_path} due to missing timestamp in get_active_file_versions.")


            if not active_versions_with_dt:
                 return [] # No valid, active versions found

            # Sort by the datetime object (newest first)
            active_versions_with_dt.sort(key=lambda x: x[2], reverse=True)

            # Return list of (hash, info dict) tuples
            return [(hash_id, info) for hash_id, info, _ in active_versions_with_dt]

        except Exception as e:
            self._log_error(f"Failed to get active file versions for {file_path}: {str(e)}")
            return [] # Return empty list on error


    def _log_error(self, error_message: str) -> None:
        """Log error messages with UTC timestamp and username."""
        # Define log file path relative to the script or backup folder
        log_dir = os.path.join(os.getcwd(), "logs") # Or self.backup_folder
        try:
            os.makedirs(log_dir, exist_ok=True)
            log_file_path = os.path.join(log_dir, "version_manager_error.log")

            current_time_utc = get_formatted_time(use_utc=True)
            username = get_current_username()

            full_message = f"[{current_time_utc}] [{username}] {error_message}\n"
            print(f"ERROR logged: {error_message}") # Also print error to console

            with open(log_file_path, "a", encoding='utf-8') as log_file:
                log_file.write(full_message)
        except Exception as log_e:
             # If logging fails, print to console as a last resort
             print(f"!!! CRITICAL: Failed to write to error log file: {log_e}")
             print(f"Original error was: {error_message}")

# Example usage (optional, typically removed in production code)
if __name__ == "__main__":
    print("Running VersionManager example...")
    # Dummy SettingsManager for testing
    class DummySettingsManager:
        settings = {"max_backups": 2} # Test with a limit of 2

    vm = VersionManager(settings_manager=DummySettingsManager())

    # Create dummy file
    test_file = "vm_test_file.txt"
    hashes = []
    messages = ["Initial commit", "Second version", "Third update", "Fourth change"]

    for i in range(4):
        with open(test_file, "w") as f:
            f.write(f"Content version {i+1}")
        
        # Simulate getting metadata
        meta = vm.get_file_metadata(test_file)
        file_hash = vm.calculate_file_hash(test_file)
        hashes.append(file_hash)
        
        print(f"\n--- Adding version {i+1} (Hash: {file_hash}) ---")
        # Add version - This now returns hashes to delete
        to_delete = vm.add_version(test_file, file_hash, meta, messages[i])
        print(f"Hashes returned by add_version to be deleted: {to_delete}")
        # In real app, call backup_manager.delete_backup_files(test_file, to_delete) here
        
        # Short pause to ensure timestamps are different
        import time
        time.sleep(1.1)


    print("\n--- Final State ---")
    final_tracked = vm.load_tracked_files()
    print("Tracked Files JSON:")
    print(json.dumps(final_tracked, indent=4))

    print("\n--- Active Versions (Should be newest 2) ---")
    active = vm.get_active_file_versions(test_file)
    for h, info in active:
        print(f"Hash: {h}, Time: {info['timestamp']}, Deleted: {info.get('deleted', False)}")

    # Clean up
    os.remove(test_file)
    # os.remove(vm.tracked_files_path) # Keep JSON for inspection if needed
    print("\nExample finished.")
